"""HTTP router and isolated decoy service. No model or shell runs on requests."""

from __future__ import annotations

import http.client
import json
import posixpath
import re
import socket
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, parse_qsl, quote, unquote, urlencode, urlsplit

from .core import (
    COOKIE_NAME,
    MAX_BODY,
    Settings,
    cookie_value,
    decoy_token,
    is_decoy_token,
    load_key,
    make_cookie,
    new_session,
    sign_session,
)
from .store import Store

HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailer", "transfer-encoding", "upgrade", "content-length", "host",
}
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def normalized_path(target: str) -> str:
    if not target.startswith("/") or len(target) > 2048 or any(ord(char) < 32 or ord(char) == 127 for char in target):
        raise ValueError("invalid request target")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.fragment or re.search(r"%(?![0-9A-Fa-f]{2})", target):
        raise ValueError("absolute request targets are forbidden")
    path = parsed.path
    for _ in range(3):
        decoded = unquote(path, errors="strict")
        if decoded == path:
            break
        path = decoded
    path = path.replace("\\", "/")
    if "%" in path or any(char in path for char in "\x00?#") or any(ord(char) < 32 or ord(char) == 127 for char in path):
        raise ValueError("invalid path")
    return posixpath.normpath("/" + path.lstrip("/"))


def is_sentinel(path: str) -> bool:
    return path.startswith("/.env") or path.startswith("/.git")


def never_real_path(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


def safe_decoy_target(path: str, query: str) -> str | None:
    """Only synthetic API selectors may cross into the decoy network."""
    if path == "/internal/api/customers":
        allowed = {"page", "limit"}
        valid = lambda key, value: value.isdecimal() and len(value) <= 4
    elif path in {"/internal/api/orders", "/internal/api/support"}:
        allowed = {"customer_id"}
        valid = lambda key, value: re.fullmatch(r"C[0-9]{6}", value) is not None
    else:
        return path
    pairs = parse_qsl(query, keep_blank_values=True)
    if len(pairs) != len({key for key, _ in pairs}) or any(key not in allowed or not valid(key, value) for key, value in pairs):
        return None
    return path + ("?" + urlencode(pairs) if pairs else "")


def strip_session_cookie(raw: str | None) -> str:
    if not raw:
        return ""
    return "; ".join(part.strip() for part in raw.split(";") if part.strip().split("=", 1)[0] != COOKIE_NAME)


class App:
    def __init__(self, settings: Settings) -> None:
        settings.validate()
        if not settings.database.is_file():
            raise FileNotFoundError("initialize the state database before serving")
        self.settings = settings
        self.key = load_key(settings.key_file)
        self.store = Store(settings.database, self.key)
        self.store.initialize()


class Handler(BaseHTTPRequestHandler):
    server_version = "SAC/0.2"
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        # BaseHTTPRequestHandler's default log includes attacker-controlled path/query.
        return

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self._handle()

    def _send(self, status: int, data: bytes, content_type: str = "application/json; charset=utf-8", cookie: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", make_cookie(cookie, self.app.settings.public_https))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, status: int, value: dict[str, Any], cookie: str = "") -> None:
        self._send(status, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(), cookie=cookie)

    def _handle(self) -> None:
        try:
            if self.command not in ALLOWED_METHODS:
                self._json(405, {"error": "method_not_allowed"})
                return
            try:
                path = normalized_path(self.path)
            except ValueError:
                self._json(400, {"error": "invalid_request_target"})
                self.close_connection = True
                return
            if self.headers.get("Transfer-Encoding"):
                self._json(400, {"error": "chunked_body_not_supported"})
                self.close_connection = True
                return
            if any(len(self.headers.get_all(name, [])) > 1 for name in ("Content-Length", "Host", "Authorization", "Cookie")):
                self._json(400, {"error": "ambiguous_headers"})
                self.close_connection = True
                return
            raw_length = self.headers.get("Content-Length", "0")
            if not raw_length.isdecimal() or int(raw_length) > MAX_BODY:
                self._json(413, {"error": "request_too_large"})
                self.close_connection = True
                return
            body = self.rfile.read(int(raw_length))
            if path == "/_sac/health":
                self._json(200, {"status": "ok"})
            elif self.app.settings.mode == "router":
                self._router(path, body)
            else:
                self._decoy(path, body)
        except (BrokenPipeError, ConnectionResetError):
            return
        except (OSError, ValueError, sqlite3.DatabaseError, http.client.HTTPException):
            # Any service or evidence failure closes the route; suspicious traffic never
            # falls through to the production upstream.
            self._json(503, {"error": "service_unavailable"})

    def _router(self, path: str, body: bytes) -> None:
        app = self.app
        session = cookie_value(app.key, self.headers.get("Cookie"))
        has_token = is_decoy_token(app.key, self.headers.get("Authorization"))
        risky = (is_sentinel(path) or path == "/internal/api" or path.startswith("/internal/api/")
                 or has_token or never_real_path(path, app.settings.never_real_prefixes))
        if session and (session[0] == "d" or app.store.risk(session[1]) >= 7):
            risky = True
        route = "decoy" if risky else ("normal" if never_real_path(path, app.settings.allow_real_prefixes) else "block")
        if session and session[0] == "d" and not risky:
            raise AssertionError("decoy session cannot downgrade")
        if not session:
            signed = new_session(app.key, "d" if risky else "n")
            session = cookie_value(app.key, f"{COOKIE_NAME}={signed}")
        elif route == "decoy" and session[0] != "d":
            signed = sign_session(app.key, "d", session[1])
            session = cookie_value(app.key, f"{COOKIE_NAME}={signed}")
        else:
            signed = ""
        assert session is not None
        sid = session[1]
        if risky:
            signed = sign_session(app.key, "d", sid)
        if risky and app.settings.kill_switch.exists():
            app.store.event(sid, "route_decision", "block", app.store.stage(sid), path)
            self._json(403, {"error": "unavailable"}, signed)
            return
        app.store.event(sid, "route_decision", route, app.store.stage(sid), path)
        if route == "block":
            self._json(403, {"error": "path_not_allowed"}, signed)
            return
        if risky and body:
            self._json(400, {"error": "body_not_supported"}, signed)
            return
        origin = app.settings.decoy if risky else app.settings.upstream
        if not origin:
            self._json(503, {"error": "upstream_unavailable"}, signed)
            return
        query = urlsplit(self.path).query
        target = safe_decoy_target(path, query) if risky else quote(path, safe="/-._~") + ("?" + query if query else "")
        if target is None:
            self._json(400, {"error": "invalid_decoy_query"}, signed)
            return
        self._proxy(origin, target, body, signed, route == "decoy", has_token)

    def _proxy(self, origin: str, target: str, body: bytes, signed: str, to_decoy: bool, has_token: bool) -> None:
        parsed = urlsplit(origin)
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, parsed.port, timeout=3)
        headers: dict[str, str] = {}
        connection_tokens = {token.strip().lower() for token in self.headers.get("Connection", "").split(",")}
        for name, value in self.headers.items():
            lower = name.lower()
            if lower in HOP_HEADERS or lower in connection_tokens or lower.startswith(("x-sac-", "x-ghostwall-", "x-forwarded-")) or lower in {"forwarded", "x-real-ip"}:
                continue
            if to_decoy and lower not in {"accept", "content-type"}:
                continue
            if lower == "cookie":
                value = strip_session_cookie(value)
                if not value:
                    continue
            headers[name] = value
        if to_decoy:
            # The router sends only its selected signed session, never app cookies.
            headers["Cookie"] = f"{COOKIE_NAME}={signed}"
            if has_token:
                headers["Authorization"] = f"Bearer {decoy_token(self.app.key)}"
        connection.request(self.command, target, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read(MAX_BODY + 1)
        if len(data) > MAX_BODY:
            raise ValueError("upstream response too large")
        self.send_response(response.status)
        response_connection_tokens = {token.strip().lower() for token in (response.getheader("Connection") or "").split(",")}
        for name, value in response.getheaders():
            lower = name.lower()
            if lower in HOP_HEADERS or lower in response_connection_tokens or lower.startswith(("x-sac-", "x-ghostwall-")):
                continue
            if lower == "set-cookie" and to_decoy and value.startswith(f"{COOKIE_NAME}="):
                continue
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if signed:
            self.send_header("Set-Cookie", make_cookie(signed, self.app.settings.public_https))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)
        connection.close()

    def _decoy(self, path: str, body: bytes) -> None:
        app = self.app
        session = cookie_value(app.key, self.headers.get("Cookie"))
        signed = ""
        if not session or session[0] != "d":
            signed = new_session(app.key, "d")
            session = cookie_value(app.key, f"{COOKIE_NAME}={signed}")
        assert session is not None
        sid = session[1]
        if app.settings.kill_switch.exists():
            app.store.event(sid, "kill_switch", "block", app.store.stage(sid), path)
            self._json(403, {"error": "unavailable"}, signed)
            return
        if path == "/.env" and self.command == "GET":
            text = f"INTERNAL_API_BASE=/internal/api\nINTERNAL_API_TOKEN={decoy_token(app.key)}\nEXPORT_ENABLED=true\n"
            app.store.event(sid, "sentinel", "decoy", app.store.stage(sid), path)
            self._send(200, text.encode(), "text/plain; charset=utf-8", signed)
            return
        if not path.startswith("/internal/api/"):
            self._json(404, {"error": "not_found"}, signed)
            return
        if not is_decoy_token(app.key, self.headers.get("Authorization")):
            self._json(401, {"error": "unauthorized"}, signed)
            return
        app.store.stage(sid, "BAIT_ACCEPTED")
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if path == "/internal/api/customers" and self.command == "GET":
            try:
                page = int(query.get("page", ["1"])[0])
                limit = int(query.get("limit", ["10"])[0])
            except ValueError:
                page, limit = 0, 0
            if not 1 <= page <= 1000 or not 1 <= limit <= 100:
                self._json(400, {"error": "invalid_pagination"}, signed)
                return
            rows = app.store.rows("customers")
            start = (page - 1) * limit
            items = rows[start : start + limit]
            stage = app.store.stage(sid, "DATA_DISCOVERY")
            app.store.event(sid, "synthetic_read", "decoy", stage, path, len(items))
            self._json(200, {"items": items, "total": len(rows), "page": page, "limit": limit}, signed)
            return
        match = re.fullmatch(r"/internal/api/customers/(C[0-9]{6})", path)
        if match and self.command == "GET":
            customer = app.store.customer(match[1])
            if customer is None:
                self._json(404, {"error": "not_found"}, signed)
                return
            stage = app.store.stage(sid, "DATA_DISCOVERY")
            app.store.event(sid, "synthetic_read", "decoy", stage, path, 1)
            self._json(200, customer, signed)
            return
        if path in {"/internal/api/orders", "/internal/api/support"} and self.command == "GET":
            cid = query.get("customer_id", [None])[0]
            if cid is not None and not re.fullmatch(r"C[0-9]{6}", cid):
                self._json(400, {"error": "invalid_customer_id"}, signed)
                return
            table = path.rsplit("/", 1)[1]
            rows = app.store.rows(table, cid)
            stage = app.store.stage(sid, "CONFIDENCE_BUILDING")
            app.store.event(sid, "synthetic_read", "decoy", stage, path, len(rows))
            self._json(200, {"items": rows, "total": len(rows)}, signed)
            return
        if path == "/internal/api/export" and self.command == "POST":
            if body:
                self._json(400, {"error": "body_not_supported"}, signed)
                return
            job = app.store.export(sid)
            stage = app.store.stage(sid, "FALSE_SUCCESS")
            app.store.event(sid, "export_completed", "decoy", stage, path, job["record_count"])
            self._json(200, job, signed)
            return
        match = re.fullmatch(r"/internal/api/export/([0-9a-f]{24})(?:/(manifest|download))?", path)
        if match and self.command == "GET":
            manifest = app.store.manifest(sid, match[1])
            if manifest is None:
                self._json(404, {"error": "not_found"}, signed)
                return
            if match[2] == "download":
                app.store.event(sid, "export_download", "decoy", app.store.stage(sid), path, manifest["record_count"])
                self._send(200, app.store.export_csv(), "text/csv; charset=utf-8", signed)
            elif match[2] == "manifest":
                stage = app.store.stage(sid, "SATIATED")
                app.store.event(sid, "manifest_read", "decoy", stage, path)
                self._json(200, manifest, signed)
            else:
                self._json(200, {"job_id": match[1], "status": "completed", "record_count": manifest["record_count"]}, signed)
            return
        self._json(404, {"error": "not_found"}, signed)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, app: App) -> None:
        self._slots = threading.BoundedSemaphore(64)
        super().__init__((app.settings.bind, app.settings.port), Handler)
        self.app = app

    def get_request(self) -> tuple[socket.socket, Any]:
        client, address = super().get_request()
        client.settimeout(5)
        return client, address

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()
