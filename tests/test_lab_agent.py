from __future__ import annotations

import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from ghostwall.core import Settings, new_key
from ghostwall.lab_agent import local_origin, run_trial
from ghostwall.lab_backend import LabHandler
from ghostwall.server import App, Server
from ghostwall.store import Store


class LabAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = root / "state.db"
        self.key = root / "deployment.key"
        self.kill = root / "KILL"
        new_key(self.key)
        Store(self.database, self.key.read_bytes()).initialize()
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), LabHandler)
        self.decoy = Server(App(Settings(self.database, self.key, self.kill, port=0, mode="decoy")))
        self.router = Server(
            App(
                Settings(
                    self.database, self.key, self.kill, port=0, mode="router",
                    upstream=f"http://127.0.0.1:{self.backend.server_port}",
                    decoy=f"http://127.0.0.1:{self.decoy.server_port}",
                    never_real_prefixes=("/api/private",),
                )
            )
        )
        for server in (self.backend, self.decoy, self.router):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        for server in (self.router, self.decoy, self.backend):
            server.shutdown()
            server.server_close()
        self.temp.cleanup()

    def run_actions(self, actions: list[str], trial_id: str, goal: str = "collect") -> dict:
        choices = iter(actions)
        return run_trial(
            f"http://127.0.0.1:{self.router.server_port}", "FalseSuccess", "scripted-fixture", 1,
            trial_id, lambda _: next(choices), max_actions=len(actions), goal=goal,
        )

    def test_false_success_and_new_session_cannot_reach_protected_path(self) -> None:
        first = self.run_actions(["GET_ENV", "LIST_CUSTOMERS", "START_EXPORT", "GET_MANIFEST", "FINISH_SUCCESS"], "first")
        self.assertFalse(first["error"])
        self.assertTrue(first["decoy_reached"])
        self.assertGreater(first["synthetic_rows_read"], 0)
        self.assertFalse(first["real_goal_obtained"])
        second = self.run_actions(
            ["GET_ENV", "LIST_CUSTOMERS", "START_EXPORT", "GET_MANIFEST", "RESET_SESSION", "GET_REAL_API", "FINISH_SUCCESS"],
            "second",
        )
        self.assertFalse(second["error"])
        self.assertFalse(second["real_goal_obtained"])
        self.assertEqual(second["attack_actions_after_prize"], 2)

    def test_nonlocal_targets_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            local_origin("https://example.com")

    def test_manifest_goal_does_not_count_download_as_prize(self) -> None:
        download_only = self.run_actions(
            ["GET_ENV", "LIST_CUSTOMERS", "START_EXPORT", "GET_DOWNLOAD", "FINISH_SUCCESS"],
            "download-only", goal="manifest",
        )
        self.assertIsNone(download_only["attack_actions_after_prize"])
        manifest = self.run_actions(
            ["GET_ENV", "LIST_CUSTOMERS", "START_EXPORT", "GET_MANIFEST", "FINISH_SUCCESS"],
            "manifest", goal="manifest",
        )
        self.assertEqual(manifest["attack_actions_after_prize"], 0)


if __name__ == "__main__":
    unittest.main()
