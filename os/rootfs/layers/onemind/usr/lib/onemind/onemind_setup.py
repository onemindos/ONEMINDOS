# SPDX-License-Identifier: Apache-2.0
"""OneMind local setup wizard (docs/leap/core/IMAGES.md §3): the box's first page when no seed
and no /boot/efi/onemind.conf configured it. Served on :8080 (http://onemind.local:8080/) by
onemind-setup.service until the owner picks a role; then it shows the owner token once, exits,
and the gateway takes over the port.

v0 limits: plain HTTP on the LAN and first-come-first-served (the HAOS onboarding model). The
owner passkey flow of brief 30 D-B9.1 replaces the token page in BM2.
"""
from __future__ import annotations

import html
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import onemind_firstboot as fb  # noqa: E402

MAX_BODY = 8192
STYLE = ("body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
         "label{display:block;margin:.6rem 0}input[type=text]{width:100%;padding:.4rem}"
         "code{word-break:break-all;background:#eee;padding:.2rem .4rem}button{padding:.5rem 1rem}")

FORM = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OneMind setup</title><style>{style}</style></head><body>
<h1>Set up this OneMind box</h1>{error}
<form method="post" action="/setup">
<fieldset><legend>Role</legend>
<label><input type="radio" name="role" value="hub" checked> Hub: the box that runs the dashboard and the bus</label>
<label><input type="radio" name="role" value="worker"> Worker: joins a hub and runs workloads</label>
<label><input type="radio" name="role" value="leaf"> Leaf: an edge device that forwards to a hub</label>
</fieldset>
<label>Name <input type="text" name="name" value="OneMind" maxlength="64"></label>
<p>Worker and leaf only (the hub printed both at its first boot):</p>
<label>Hub address <input type="text" name="hub" placeholder="onemind.local"></label>
<label>Join token <input type="text" name="join_token" autocomplete="off"></label>
<button type="submit">Set up</button></form></body></html>"""

DONE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OneMind setup</title><style>{style}</style></head><body>
<h1>Done: this box is a {role}</h1>{token}
<p>The OneMind services are starting. {next}</p></body></html>"""


class Wizard(BaseHTTPRequestHandler):
    server_version = "onemind-setup"
    paths: fb.Paths = fb.Paths("/")
    done = threading.Event()

    def log_message(self, fmt, *args):  # no client addresses in the journal
        pass

    def _send(self, code: int, body: str) -> None:
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] == "/healthz":
            return self._send(200, "setup")
        self._send(200, FORM.format(style=STYLE, error=""))

    def do_POST(self):
        if self.path != "/setup":
            return self._send(404, "not found")
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, "too large")
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
        if fb.load_state(self.paths):
            return self._send(409, "<p>This box is already set up.</p>")
        try:
            cfg = fb.validate({k: form.get(k, "") for k in fb.KEYS})
        except fb.ConfigError as exc:
            err = f'<p role="alert"><strong>{html.escape(str(exc))}</strong></p>'
            return self._send(400, FORM.format(style=STYLE, error=err))
        fb.finish(self.paths, cfg, "wizard")
        tok_path = os.path.join(self.paths.run, "owner-token")
        token, nxt = "", "This page stops answering in a few seconds."
        if cfg["role"] == "hub":
            try:
                with open(tok_path) as f:
                    t = f.read().strip()
                os.unlink(tok_path)              # shown once
                token = ("<p>Your <strong>owner token</strong>. Copy it now: it is shown once and only its "
                         f"sha256 is kept.</p><p><code>{html.escape(t)}</code></p>")
            except OSError:
                token = "<p>The owner token was printed on the box's console.</p>"
            nxt = "Reload this address in a minute for the dashboard."
        self._send(200, DONE.format(style=STYLE, role=cfg["role"], token=token, next=nxt))
        self.done.set()


def main() -> int:
    Wizard.paths = fb.Paths(os.environ.get("ONEMIND_FIRSTBOOT_ROOT", "/"))
    if fb.load_state(Wizard.paths):
        print("onemind-setup: already configured; nothing to do")
        return 0
    port = int(os.environ.get("ONEMIND_SETUP_PORT", "8080"))
    srv = ThreadingHTTPServer((os.environ.get("ONEMIND_SETUP_BIND", "0.0.0.0"), port), Wizard)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"onemind-setup: waiting on :{port}", flush=True)
    Wizard.done.wait()
    srv.shutdown()
    srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
