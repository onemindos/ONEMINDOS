# SPDX-License-Identifier: Apache-2.0
"""OneMind local setup wizard (docs/leap/core/IMAGES.md §3): the box's first page when no seed
and no /boot/efi/onemind.conf configured it. Served on :8080 (http://onemind.local:8080/) by
onemind-setup.service until the owner picks a role; then it shows the owner token once, exits,
and the gateway takes over the port.

Lockdown (P0, image-security review 07): the page on the box itself (loopback, which is what the
box screen asks) is open. A phone or computer on the LAN must type the one-time setup code that the
box screen and console show, so nobody else on the network can claim the box first. Once an owner
exists (state.json) every LAN request is refused and the process exits. Plain HTTP on the LAN is
still v0; the owner passkey flow of brief 30 D-B9.1 replaces the token page in BM2.
"""
from __future__ import annotations

import hmac
import html
import ipaddress
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import onemind_firstboot as fb  # noqa: E402

MAX_BODY = 8192
CODE_FILE = "setup-code"      # in /run/onemind (tmpfs, 0600): the box screen reads it, a reboot clears it
MAX_WRONG = 5                 # wrong codes from the LAN before the code is changed
STYLE = ("body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
         "label{display:block;margin:.6rem 0}input[type=text]{width:100%;padding:.4rem}"
         "code{word-break:break-all;background:#eee;padding:.2rem .4rem}button{padding:.5rem 1rem}")

FORM = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OneMind setup</title><style>{style}</style></head><body>
<h1>Set up this OneMind box</h1>{error}
<form method="post" action="/setup">
{code_field}
<fieldset><legend>Role</legend>
<label><input type="radio" name="role" value="hub" checked> Hub: the box that runs the dashboard and the bus</label>
<label><input type="radio" name="role" value="worker"> Worker: joins a hub and runs workloads</label>
<label><input type="radio" name="role" value="leaf"> Leaf: an edge device that forwards to a hub</label>
</fieldset>
<label>Name <input type="text" name="name" value="OneMind" maxlength="64"></label>
<p>Worker and leaf only. On the hub, run <code>onemind fabric ticket</code> (or Add a device on the
dashboard) and copy the join code. The owner then approves this box on the hub.</p>
<label>Join code <input type="text" name="join_code" autocomplete="off" placeholder="onemind-join:v1?code=..."></label>
<label>Hub IP address (optional: only if this box cannot find the hub by name) <input type="text" name="hub_addr" placeholder="192.0.2.10"></label>
<button type="submit">Set up</button></form></body></html>"""

DONE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OneMind setup</title><style>{style}</style></head><body>
<h1>Done: this box is a {role}</h1>{token}
<p>The OneMind services are starting. {next}</p></body></html>"""


CODE_FIELD = ('<label>Setup code shown on the box screen <input type="text" name="code" inputmode="numeric" '
              'autocomplete="off" maxlength="12" required></label>')


def is_local(addr: str) -> bool:
    """True for a request that came from the box itself (the screen, or ssh -L on a cloud image)."""
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback


class Gate:
    """The one-time setup code. new() makes a fresh 8-digit code and publishes it for the screen."""

    def __init__(self):
        self.lock = threading.Lock()
        self.code = ""
        self.wrong = 0
        self.path = ""

    def new(self, run_dir: str) -> str:
        with self.lock:
            self.code = "".join(secrets.choice("0123456789") for _ in range(8))
            self.wrong = 0
            self.path = os.path.join(run_dir, CODE_FILE)
            os.makedirs(run_dir, mode=0o711, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(self.code + "\n")
            return self.code

    def check(self, given: str, run_dir: str) -> bool:
        with self.lock:
            ok = bool(self.code) and hmac.compare_digest(given.strip().encode(), self.code.encode())
            if not ok:
                self.wrong += 1
                rotate = self.wrong >= MAX_WRONG
            else:
                rotate = False
        if rotate:
            self.new(run_dir)            # a guesser starts again; the screen shows the new code
        return ok

    def clear(self) -> None:
        try:
            os.unlink(self.path)
        except OSError:
            pass


class Wizard(BaseHTTPRequestHandler):
    server_version = "onemind-setup"
    paths: fb.Paths = fb.Paths("/")
    done = threading.Event()
    gate = Gate()

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

    def _local(self) -> bool:
        return is_local(self.client_address[0])

    def _refuse_lan(self) -> bool:
        """Once an owner exists the wizard answers the box itself only. True when it refused."""
        if not self._local() and fb.load_state(self.paths):
            self._send(403, "<p>This box is already set up.</p>")
            return True
        return False

    def do_GET(self):
        if self._refuse_lan():
            return
        if self.path.split("?")[0] == "/healthz":
            # the box screen asks from loopback; the LAN learns nothing from this box before the code
            return self._send(200 if self._local() else 403, "setup" if self._local() else "forbidden")
        self._send(200, FORM.format(style=STYLE, error="", code_field="" if self._local() else CODE_FIELD))

    def do_POST(self):
        if self.path != "/setup":
            return self._send(404, "not found")
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, "too large")
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
        if self._refuse_lan():
            return
        if fb.load_state(self.paths):
            return self._send(409, "<p>This box is already set up.</p>")
        if not self._local() and not self.gate.check(form.get("code", ""), self.paths.run):
            err = '<p role="alert"><strong>Wrong setup code. Read it on the box screen.</strong></p>'
            return self._send(403, FORM.format(style=STYLE, error=err, code_field=CODE_FIELD))
        try:
            cfg = fb.validate({k: form.get(k, "") for k in fb.KEYS})
        except fb.ConfigError as exc:
            err = f'<p role="alert"><strong>{html.escape(str(exc))}</strong></p>'
            return self._send(400, FORM.format(style=STYLE, error=err,
                                               code_field="" if self._local() else CODE_FIELD))
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
        else:
            nxt = ("It now asks the hub to join: approve it on the hub's dashboard (Approvals) after checking "
                   "that the code shown there matches the one on this box's console. This page stops answering "
                   "in a few seconds.")
        self.gate.clear()
        self._send(200, DONE.format(style=STYLE, role=cfg["role"], token=token, next=nxt))
        self.done.set()


def main() -> int:
    Wizard.paths = fb.Paths(os.environ.get("ONEMIND_FIRSTBOOT_ROOT", "/"))
    if fb.load_state(Wizard.paths):
        print("onemind-setup: already configured; nothing to do")
        return 0
    port = int(os.environ.get("ONEMIND_SETUP_PORT", "8080"))
    code = Wizard.gate.new(Wizard.paths.run)
    fb.console(Wizard.paths, f"ONEMIND SETUP CODE: {code} (type it on the setup page from another device)")
    srv = ThreadingHTTPServer((os.environ.get("ONEMIND_SETUP_BIND", "0.0.0.0"), port), Wizard)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"onemind-setup: waiting on :{port}", flush=True)
    Wizard.done.wait()
    Wizard.gate.clear()
    srv.shutdown()
    srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
