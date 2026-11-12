# SPDX-License-Identifier: Apache-2.0
"""Fake delivery endpoints for the notify tests: an HTTP receiver (ntfy, webhook, push service)
and a minimal SMTP server. Both listen on 127.0.0.1 with an ephemeral port."""

from __future__ import annotations

import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeHttp:
    """Records every POST; answers `status` (settable)."""

    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(n)
                outer.requests.append({"path": self.path, "headers": dict(self.headers.items()), "body": body})
                self.send_response(outer.status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeSmtp:
    """Enough SMTP (RFC 5321) for smtplib without TLS: EHLO, MAIL, RCPT, DATA, QUIT."""

    def __init__(self):
        self.messages: list[dict] = []
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                w = lambda line: (self.wfile.write(line.encode() + b"\r\n"), self.wfile.flush())  # noqa: E731
                w("220 fake ESMTP")
                env: dict = {"rcpt": []}
                while True:
                    raw = self.rfile.readline()
                    if not raw:
                        return
                    cmd = raw.decode(errors="replace").strip()
                    up = cmd.upper()
                    if up.startswith(("EHLO", "HELO")):
                        w("250-fake")
                        w("250 SIZE 1000000")
                    elif up.startswith("MAIL FROM"):
                        env["from"] = cmd[10:]
                        w("250 ok")
                    elif up.startswith("RCPT TO"):
                        env["rcpt"].append(cmd[8:])
                        w("250 ok")
                    elif up == "DATA":
                        w("354 go")
                        lines = []
                        while True:
                            line = self.rfile.readline().decode(errors="replace")
                            if line.rstrip("\r\n") == ".":
                                break
                            lines.append(line)
                        env["data"] = "".join(lines)
                        outer.messages.append(env)
                        env = {"rcpt": []}
                        w("250 queued")
                    elif up == "QUIT":
                        w("221 bye")
                        return
                    else:
                        w("250 ok")

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
