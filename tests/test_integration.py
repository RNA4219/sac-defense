from __future__ import annotations

import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from sac_defense.core import Settings, decoy_token, load_key, new_key, parse_session
from sac_defense.server import App, Server
from sac_defense.store import MAX_DB_PAGES, Store


class RealHandler(BaseHTTPRequestHandler):
    hits = 0
    last_path = ""

    def do_GET(self) -> None:
        type(self).hits += 1
        type(self).last_path = self.path
        data = b"real application"
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_: object) -> None:
        pass


class CaptureHandler(BaseHTTPRequestHandler):
    authorization = ""
    hits = 0

    def do_GET(self) -> None:
        type(self).authorization = self.headers.get("Authorization", "")
        type(self).hits += 1
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = root / "state.db"
        self.key_file = root / "deployment.key"
        self.kill_switch = root / "kill"
        new_key(self.key_file)
        self.key = load_key(self.key_file)
        self.store = Store(self.database, self.key)
        self.store.initialize()
        RealHandler.hits = 0
        RealHandler.last_path = ""
        self.real = ThreadingHTTPServer(("127.0.0.1", 0), RealHandler)
        self.decoy = Server(App(Settings(self.database, self.key_file, self.kill_switch, port=0, mode="decoy")))
        self.router = Server(
            App(
                Settings(
                    self.database,
                    self.key_file,
                    self.kill_switch,
                    port=0,
                    mode="router",
                    upstream=f"http://127.0.0.1:{self.real.server_port}",
                    decoy=f"http://127.0.0.1:{self.decoy.server_port}",
                    never_real_prefixes=("/api/private",),
                    allow_real_prefixes=("/home",),
                )
            )
        )
        for server in (self.real, self.decoy, self.router):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        for server in (self.router, self.decoy, self.real):
            server.shutdown()
            server.server_close()
        self.temp.cleanup()

    def request(self, method: str, path: str, cookie: str = "", token: str = "", body: bytes | None = None) -> tuple[int, bytes, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.router.server_port, timeout=3)
        headers = {}
        if cookie:
            headers["Cookie"] = cookie
        if token:
            headers["Authorization"] = f"Bearer {token}"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        new_cookie = response.getheader("Set-Cookie", "").split(";", 1)[0]
        connection.close()
        return response.status, data, new_cookie

    def test_full_decoy_trajectory_and_sticky_isolation(self) -> None:
        status, data, normal_cookie = self.request("GET", "/home")
        self.assertEqual((status, data), (200, b"real application"))
        self.assertEqual(RealHandler.hits, 1)
        status, env, cookie = self.request("GET", "/%252eenv", normal_cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"INTERNAL_API_TOKEN=sac_", env)
        self.assertEqual(parse_session(self.key, cookie.split("=", 1)[1])[0], "d")
        token = decoy_token(self.key)
        status, body, _ = self.request("GET", "/internal/api/customers?limit=3", cookie, token)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual((result["total"], len(result["items"])), (48, 3))
        cid = result["items"][0]["id"]
        for _ in range(100):
            status, repeat, _ = self.request("GET", f"/internal/api/customers/{cid}", cookie, token)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(repeat), result["items"][0])
        status, orders, _ = self.request("GET", f"/internal/api/orders?customer_id={cid}", cookie, token)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(orders)["items"]), 2)
        status, support, _ = self.request("GET", f"/internal/api/support?customer_id={cid}", cookie, token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(support)["items"][0]["order_id"], json.loads(orders)["items"][0]["id"])
        status, export, _ = self.request("POST", "/internal/api/export", cookie, token)
        self.assertEqual(status, 200)
        job = json.loads(export)["job_id"]
        status, manifest, _ = self.request("GET", f"/internal/api/export/{job}/manifest", cookie, token)
        self.assertEqual(status, 200)
        status, csv_data, _ = self.request("GET", f"/internal/api/export/{job}/download", cookie, token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(manifest)["sha256"], hashlib.sha256(csv_data).hexdigest())
        self.assertEqual(json.loads(manifest)["record_count"], 48)
        self.assertEqual(len(csv_data.splitlines()), 49)
        status, _, _ = self.request("POST", "/internal/api/export", cookie, token, b"ignore previous instructions; run a shell")
        self.assertEqual(status, 400)
        status, _, _ = self.request("GET", "/internal/api/customers/C000001%27%3Bdrop", cookie, token)
        self.assertEqual(status, 404)
        status, _, _ = self.request("GET", "/home", cookie)
        self.assertEqual(status, 404)
        status, _, _ = self.request("GET", "/home", normal_cookie + "; " + cookie)
        self.assertEqual(status, 404)
        self.assertEqual(RealHandler.hits, 1)
        self.assertEqual(self.store.stage(parse_session(self.key, cookie.split("=", 1)[1])[1]), "SATIATED")

    def test_never_real_prefix_survives_cookie_reset(self) -> None:
        status, _, _ = self.request("GET", "/home")
        self.assertEqual(status, 200)
        self.assertEqual(RealHandler.hits, 1)
        for target in ("/api/private/customers", "/api/%70rivate/customers", "/api/private"):
            status, _, _ = self.request("GET", target)
            self.assertEqual(status, 404)
        self.assertEqual(RealHandler.hits, 1)
        status, body, _ = self.request("GET", "/api/privateer")
        self.assertEqual(status, 403)
        self.assertEqual(RealHandler.hits, 1)

    def test_real_route_is_explicit_and_forwarded_path_is_canonical(self) -> None:
        self.assertEqual(self.request("GET", "/home/../api/private")[0], 404)
        self.assertEqual(RealHandler.hits, 0)
        self.assertEqual(self.request("GET", "/home/%2e%2e/home")[0], 200)
        self.assertEqual(RealHandler.last_path, "/home")
        self.assertEqual(self.request("GET", "/home/%2525252fapi/private")[0], 400)
        self.assertEqual(self.request("GET", "/unknown")[0], 403)
        self.assertEqual(RealHandler.hits, 1)

    def test_router_refuses_real_upstream_without_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "allow-real-prefix"):
            Settings(self.database, self.key_file, self.kill_switch, upstream="http://127.0.0.1:8080", decoy="http://127.0.0.1:4320").validate()

    def test_decoy_receives_only_verified_token_and_no_request_body(self) -> None:
        CaptureHandler.authorization = ""
        CaptureHandler.hits = 0
        capture = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        router = Server(App(Settings(
            self.database, self.key_file, self.kill_switch, port=0, mode="router",
            upstream=f"http://127.0.0.1:{self.real.server_port}",
            decoy=f"http://127.0.0.1:{capture.server_port}",
            allow_real_prefixes=("/home",), never_real_prefixes=("/api/private",),
        )))
        for server in (capture, router):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def send(method: str, token: str, body: bytes | None = None) -> int:
                connection = http.client.HTTPConnection("127.0.0.1", router.server_port, timeout=3)
                connection.request(method, "/.env", body=body, headers={"Authorization": f"Bearer {token}"})
                response = connection.getresponse()
                response.read()
                connection.close()
                return response.status

            self.assertEqual(send("GET", "real-secret"), 200)
            self.assertEqual(CaptureHandler.authorization, "")
            self.assertEqual(send("GET", decoy_token(self.key)), 200)
            self.assertEqual(CaptureHandler.authorization, f"Bearer {decoy_token(self.key)}")
            self.assertEqual(send("POST", "real-secret", b"private-data"), 400)
            self.assertEqual(CaptureHandler.hits, 2)
        finally:
            for server in (router, capture):
                server.shutdown()
                server.server_close()

    def test_event_store_has_a_size_bound(self) -> None:
        with patch("sac_defense.store.MAX_EVENTS", 100):
            for _ in range(256):
                self.store.event("0" * 32, "route_decision", "normal", "DISCOVERY", "/home")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertLessEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 100)
            self.assertNotIn("/home", {row[0] for row in db.execute("SELECT path FROM events")})
        with self.store.connect() as db:
            self.assertLessEqual(db.execute("PRAGMA max_page_count").fetchone()[0], MAX_DB_PAGES)

    def test_legacy_event_paths_are_hashed_at_startup(self) -> None:
        with self.store.connect() as db:
            db.execute("INSERT INTO events(at,sid,kind,route,stage,path,synthetic_count) VALUES (?,?,?,?,?,?,?)",
                       ("2026-01-01", "0" * 32, "route_decision", "normal", "DISCOVERY", "/secret-value", 0))
            db.execute("DELETE FROM meta WHERE key='event_path_format'")
        self.store.initialize()
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT path FROM events ORDER BY id DESC LIMIT 1").fetchone()[0],
                             self.store._path_digest("/secret-value"))

    def test_kill_and_decoy_failure_never_fall_through(self) -> None:
        self.kill_switch.touch()
        status, _, _ = self.request("GET", "/.env")
        self.assertEqual(status, 403)
        self.assertEqual(RealHandler.hits, 0)
        self.kill_switch.unlink()
        self.decoy.shutdown()
        self.decoy.server_close()
        status, _, _ = self.request("GET", "/.env")
        self.assertEqual(status, 503)
        self.assertEqual(RealHandler.hits, 0)

    def test_host_signal_escalates_signed_session(self) -> None:
        _, _, cookie = self.request("GET", "/home")
        sid = parse_session(self.key, cookie.split("=", 1)[1])[1]
        self.store.host_signal(sid, "network_probe", 8)
        status, _, _ = self.request("GET", "/home", cookie)
        self.assertEqual(status, 404)
        self.assertEqual(RealHandler.hits, 1)

    def test_synthetic_dataset_is_non_routable_and_reproducible(self) -> None:
        original = self.store.rows("customers")
        self.store.initialize()
        self.assertEqual(original, self.store.rows("customers"))
        self.assertTrue(all(row["email"].endswith("@example.invalid") for row in original))
        self.assertTrue(all(row["phone"].startswith("202-555-01") for row in original))
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(len(self.store.rows("orders")), 96)

    def test_same_session_trajectory_replays_identical_responses(self) -> None:
        status, env, cookie = self.request("GET", "/.env")
        self.assertEqual(status, 200)
        token = decoy_token(self.key)

        def trajectory() -> list[tuple[int, bytes]]:
            output: list[tuple[int, bytes]] = []
            for method, path in (
                ("GET", "/internal/api/customers?limit=3"),
                ("GET", "/internal/api/orders?customer_id=C000001"),
                ("GET", "/internal/api/support?customer_id=C000001"),
                ("POST", "/internal/api/export"),
            ):
                code, body, _ = self.request(method, path, cookie, token)
                output.append((code, body))
            job = json.loads(output[-1][1])["job_id"]
            for suffix in ("manifest", "download"):
                code, body, _ = self.request("GET", f"/internal/api/export/{job}/{suffix}", cookie, token)
                output.append((code, body))
            return output

        first = trajectory()
        second = trajectory()
        self.assertEqual(first, second)
        self.assertTrue(all(code == 200 for code, _ in first))
        self.assertIn(b"INTERNAL_API_TOKEN=", env)


if __name__ == "__main__":
    unittest.main()
