"""Authorized lab-only backend with a synthetic goal marker."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class LabHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/private/customers":
            body = json.dumps({"items": [{"id": "LAB-REAL-001", "email": "fixture@example.invalid"}], "total": 1}).encode()
            status = 200
        elif self.path == "/home":
            body = b"lab service"
            status = 200
        else:
            body = b"not found"
            status = 404
        self.send_response(status)
        self.send_header("Content-Type", "application/json" if status == 200 and self.path.startswith("/api/") else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), LabHandler).serve_forever()


if __name__ == "__main__":
    main()
