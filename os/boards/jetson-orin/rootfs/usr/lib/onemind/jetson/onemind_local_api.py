# SPDX-License-Identifier: Apache-2.0
"""Jetson stand-in for the local API (G6): answers /health with this boot's ID on 127.0.0.1:7070."""
import http.server


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        with open("/run/onemind-api/health", "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", 7070), H).serve_forever()
