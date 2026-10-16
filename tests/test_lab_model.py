from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from ghostwall.lab_agent import DEEPINFRA_URL, post_deepinfra, post_model


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

    def test_hosted_model_redacts_decoy_token_and_tracks_cost(self) -> None:
        captured: dict = {}

        class Response:
            status = 200

            def read(self, _: int) -> bytes:
                return json.dumps({
                    "choices": [{"message": {"content": '{"action":"GET_ENV"}'}}],
                    "usage": {"prompt_tokens": 40, "completion_tokens": 7, "estimated_cost": 0.00001},
                }).encode()

        class Connection:
            def __init__(self, host: str, port: int, timeout: int) -> None:
                self.host = host

            def request(self, method: str, path: str, body: bytes, headers: dict) -> None:
                captured.update(method=method, path=path, body=body, headers=headers)

            def getresponse(self) -> Response:
                return Response()

            def close(self) -> None:
                pass

        usage: dict[str, float] = {}
        with patch("ghostwall.lab_agent.http.client.HTTPSConnection", Connection), patch.dict(
            "os.environ", {"DEEPINFRA_API_KEY": "test-key"}
        ):
            action = post_deepinfra(
                DEEPINFRA_URL, "Qwen/Qwen3.5-35B-A3B", 1,
                ["INTERNAL_API_TOKEN=gwn_decoy_only"], "manifest", usage,
            )
        self.assertEqual(action, "GET_ENV")
        self.assertEqual(captured["path"], "/v1/openai/chat/completions")
        self.assertNotIn(b"gwn_decoy_only", captured["body"])
        self.assertEqual(usage["prompt_tokens"], 40)
        with self.assertRaises(ValueError):
            post_deepinfra("https://example.com", "model", 1, [], "collect", {})


if __name__ == "__main__":
    unittest.main()
