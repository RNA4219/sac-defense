from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ghostwall.cli import main
from ghostwall.core import load_key, new_session
from ghostwall.store import Store


class FakeServer:
    def __init__(self, app: object) -> None:
        self.app = app

    def serve_forever(self, poll_interval: float) -> None:
        assert poll_interval > 0

    def server_close(self) -> None:
        pass


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "state.db"
        self.key_file = self.root / "deployment.key"
        self.kill_switch = self.root / "KILL"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(list(args))
        return status, out.getvalue(), err.getvalue()

    def test_operator_lifecycle(self) -> None:
        common = ("--database", str(self.database), "--key-file", str(self.key_file))
        status, output, _ = self.run_cli("init", *common)
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["status"], "initialized")
        registry = self.root / "registry.csv"
        synthetic_email = Store(self.database, load_key(self.key_file)).rows("customers")[0]["email"]
        registry.write_text(f"email\n{synthetic_email}\n", encoding="utf-8")
        status, output, _ = self.run_cli("collision-check", *common, "--registry", str(registry))
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output)["collisions"], 1)
        registry.write_text("email\nnot-a-customer@example.invalid\n", encoding="utf-8")
        self.assertEqual(self.run_cli("collision-check", *common, "--registry", str(registry))[0], 0)
        status, _, error = self.run_cli("init", *common)
        self.assertEqual(status, 2)
        self.assertIn("state.db", error)
        status, output, _ = self.run_cli("summary", *common)
        self.assertEqual(json.loads(output)["events"], 0)
        self.assertEqual(status, 0)
        status, _, _ = self.run_cli("kill", "--kill-switch", str(self.kill_switch), "on")
        self.assertEqual(status, 0)
        self.assertTrue(self.kill_switch.exists())
        status, _, _ = self.run_cli("kill", "--kill-switch", str(self.kill_switch), "off")
        self.assertEqual(status, 0)
        self.assertFalse(self.kill_switch.exists())
        event_path = self.root / "host.json"
        event_path.write_text(json.dumps({"session_cookie": new_session(load_key(self.key_file), "n"), "kind": "network_probe", "severity": 8}), encoding="utf-8")
        status, output, _ = self.run_cli("host-event", *common, "--file", str(event_path))
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["status"], "recorded")
        with closing(sqlite3.connect(self.database)) as db:
            with db:
                db.execute("UPDATE host_signals SET at='2020-01-01T00:00:00+00:00'")
        status, output, _ = self.run_cli("prune", *common, "--days", "30")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["removed"]["host_signals"], 1)
        with patch("ghostwall.cli.Server", FakeServer):
            status, output, _ = self.run_cli(
                "serve", "--mode", "router", *common, "--kill-switch", str(self.kill_switch),
                "--decoy", "http://127.0.0.1:4320", "--upstream", "http://127.0.0.1:8080",
            )
        self.assertEqual(status, 0)
        self.assertIn('"listening"', output)

    def test_rejects_bad_host_signal_and_invalid_retention(self) -> None:
        common = ("--database", str(self.database), "--key-file", str(self.key_file))
        self.run_cli("init", *common)
        event_path = self.root / "host.json"
        event_path.write_text('{"session_cookie":"forged","kind":"network_probe","severity":8}', encoding="utf-8")
        self.assertEqual(self.run_cli("host-event", *common, "--file", str(event_path))[0], 2)
        self.assertEqual(self.run_cli("prune", *common, "--days", "0")[0], 2)


if __name__ == "__main__":
    unittest.main()
