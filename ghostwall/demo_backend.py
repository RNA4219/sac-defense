"""A harmless backend for the isolated deployment example."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        data = b"real-demo (no data)\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), DemoHandler).serve_forever()
