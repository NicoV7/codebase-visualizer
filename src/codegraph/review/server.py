"""Loopback review server: serves the city and persists got-it marks.

Threat model: single-user localhost tool. Binds 127.0.0.1 only, no auth.
Hardening against web pages attacking localhost: Host-header allowlist
(DNS rebinding) and a required custom header on writes (forces a CORS
preflight; the server sends no CORS headers, so cross-origin pages cannot
write). Another local process writing the ledger is inside the same trust
boundary as the .codegraph/ files themselves.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from codegraph.service import CodeGraphService

_ALLOWED_HOSTS = ("localhost", "127.0.0.1")


class ReviewServer:
    def __init__(self, service: CodeGraphService, html: str, port: int = 0):
        self.service = service
        self.html = html.encode()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # quiet: the CLI prints the URL once
                pass

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0]
                return host in _ALLOWED_HOSTS

            def _send(self, code: int, body: bytes, ctype: str):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, payload: dict):
                self._send(code, json.dumps(payload).encode(), "application/json")

            def do_GET(self):
                if not self._host_ok():
                    return self._json(421, {"error": "bad host"})
                if self.path == "/" or self.path.startswith("/?") or self.path.startswith("/#"):
                    return self._send(200, outer.html, "text/html; charset=utf-8")
                if self.path == "/api/understanding":
                    return self._json(200, outer.service.comprehension())
                self._json(404, {"error": "not found"})

            def do_POST(self):
                if not self._host_ok():
                    return self._json(421, {"error": "bad host"})
                if self.path != "/api/understanding":
                    return self._json(404, {"error": "not found"})
                if self.headers.get("X-Codegraph") != "1":
                    return self._json(403, {"error": "missing X-Codegraph header"})
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(length) or b"{}")
                    outer.service.mark_understood(body["symbol_id"], body.get("state", "walked"))
                except (KeyError, ValueError, json.JSONDecodeError) as exc:
                    return self._json(400, {"error": str(exc)})
                self._json(200, outer.service.comprehension())

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def serve_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        return thread

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
