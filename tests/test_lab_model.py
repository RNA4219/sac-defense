from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ghostwall.lab_agent import post_model


class ModelHandler(BaseHTTPRequestHandler):
    action = "GET_ENV"

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        assert request["messages"][0]["role"] == "system"
        assert request["chat_template_kwargs"]["enable_thinking"] is False
        data = json.dumps({"choices": [{"message": {"content": json.dumps({"action": self.action})}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_: object) -> None:
        pass


class ModelProtocolTests(unittest.TestCase):
    def test_openai_compatible_response_is_restricted_to_actions(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            self.assertEqual(post_model(origin, "fixture-model", 1, ["No requests"]), "GET_ENV")
            ModelHandler.action = "UNSAFE_COMMAND"
            with self.assertRaisesRegex(ValueError, "invalid action"):
                post_model(origin, "fixture-model", 1, ["No requests"])
        finally:
            ModelHandler.action = "GET_ENV"
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
