# SPDX-License-Identifier: Apache-2.0
"""OneMind local setup wizard (docs/leap/core/IMAGES.md §3): the box's first page when no seed
and no /boot/efi/onemind.conf configured it. Served on :8080 (http://onemind.local:8080/) by
onemind-setup.service until the owner picks a role; then it shows the owner token once, exits,
and the gateway takes over the port.

Privileges (#578): this web part runs as an unprivileged dynamic user with no capabilities. It shows the
form, checks the setup code and the form, and asks the root helper (onemind_setup_helper.py, over
/run/onemind-setup-helper.sock) to publish the code for the box screen and to apply the form. The helper
checks every field again and refuses everything once the box has an owner.

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
import json
import os
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import onemind_firstboot as fb  # noqa: E402
from onemind_setup_helper import ALPHABET, CODE_LEN  # noqa: E402,F401  (one definition of the code)

MAX_BODY = 8192
HELPER_SOCK = "/run/onemind-setup-helper.sock"   # onemind-setup-helper.socket
MAX_REPLY = 65536
MAX_WRONG = 5                 # wrong codes from the LAN (all clients together) before a back-off
LOCK_MIN_S, LOCK_MAX_S = 60.0, 900.0   # back-off: 1 min, doubling to 15 min
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


CODE_FIELD = ('<label>Setup code shown on the box screen <input type="text" name="code" autocapitalize="characters" '
              'autocomplete="off" maxlength="16" required></label>')


def is_local(addr: str) -> bool:
    """True for a request that came from the box itself (the screen, or ssh -L on a cloud image)."""
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback


class HelperError(RuntimeError):
    """The root helper refused (kind: bad-request, invalid, configured, forbidden) or is not there (unavailable)."""

    def __init__(self, kind: str, msg: str):
        super().__init__(msg)
        self.kind = kind


class Helper:
    """Client of the root helper: one JSON line out, one back, one connection per request.
    `call` replaces the socket transport (the tests run the helper's handle() in-process)."""

    def __init__(self, path: str = HELPER_SOCK, call=None):
        self.path = path
        self._call = call or self._socket_call

    def _socket_call(self, req: dict) -> dict:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(120)                         # applying a hub makes its CA and keys
                s.connect(self.path)
                s.sendall(json.dumps(req).encode() + b"\n")
                s.shutdown(socket.SHUT_WR)
                buf = b""
                while len(buf) <= MAX_REPLY:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
            return json.loads(buf.decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise HelperError("unavailable", f"the setup helper did not answer ({exc.__class__.__name__})") from None

    def call(self, op: str, **fields) -> dict:
        resp = self._call({"op": op, **fields})
        if not isinstance(resp, dict) or resp.get("ok") is not True:
            resp = resp if isinstance(resp, dict) else {}
            raise HelperError(str(resp.get("kind", "unavailable")), str(resp.get("error", "the setup helper failed")))
        return resp

    def configured(self) -> bool:
        return self.call("status").get("configured") is True

    def publish_code(self, code: str) -> None:
        self.call("publish-code", code=code)

    def apply(self, cfg: dict) -> dict:
        return self.call("apply", config=cfg)


class Gate:
    """The one-time setup code, with a global back-off.

    new() makes a fresh CODE_LEN-character code (no look-alike letters, 32 symbols = 50 bits) and
    publishes it for the screen (through the root helper: this process cannot write /run/onemind). The code is NOT changed by wrong tries: changing it gives a guesser
    a fresh target and locks the real owner out. Instead, after MAX_WRONG wrong tries from the LAN
    (counted across all clients) every LAN try is refused for a back-off that doubles up to
    LOCK_MAX_S, so a loop of guesses gets about MAX_WRONG tries per LOCK_MAX_S. The box screen
    (loopback) needs no code, so a locked-out owner still sets up from the box itself.
    """

    def __init__(self, clock=time.monotonic):
        self.lock = threading.Lock()
        self.clock = clock
        self.code = ""
        self.wrong = 0
        self.lock_s = 0.0
        self.until = 0.0

    def new(self, publish) -> str:
        """A fresh code, handed to publish(code) for the box screen before it is accepted."""
        with self.lock:
            code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
            publish(code)
            self.code = code
            self.wrong = 0
            self.lock_s = 0.0
            self.until = 0.0
            return self.code

    def locked(self) -> float:
        """Seconds left of the back-off (0 when tries are allowed)."""
        with self.lock:
            return max(0.0, self.until - self.clock())

    def check(self, given: str) -> bool:
        """True for the right code. While locked out, every try is refused, even the right code."""
        with self.lock:
            now = self.clock()
            if now < self.until:
                return False
            norm = given.strip().upper().replace("-", "").replace(" ", "")
            if self.code and hmac.compare_digest(norm.encode(), self.code.encode()):
                return True
            self.wrong += 1
            if self.wrong >= MAX_WRONG:
                self.wrong = 0
                self.lock_s = min(max(self.lock_s * 2, LOCK_MIN_S), LOCK_MAX_S)
                self.until = now + self.lock_s
            return False


class Wizard(BaseHTTPRequestHandler):
    server_version = "onemind-setup"
    helper: Helper = Helper()
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

    def _configured(self) -> bool | None:
        """Whether the box has an owner; None when the helper cannot tell."""
        try:
            return self.helper.configured()
        except HelperError:
            return None

    def _refuse_lan(self) -> bool:
        """Once an owner exists the wizard answers the box itself only. True when it refused.
        Without an answer from the helper the LAN is refused too (fail closed)."""
        if not self._local() and self._configured() is not False:
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
        configured = self._configured()
        if configured is None:
            return self._send(503, "<p>The setup helper is not answering. Try again in a moment.</p>")
        if configured:
            return self._send(409, "<p>This box is already set up.</p>")
        if not self._local() and not self.gate.check(form.get("code", "")):
            wait = self.gate.locked()
            msg = (f"Too many wrong codes. Wait {int(wait) + 1} seconds, or set up on the box screen."
                   if wait else "Wrong setup code. Read it on the box screen.")
            err = f'<p role="alert"><strong>{msg}</strong></p>'
            return self._send(429 if wait else 403, FORM.format(style=STYLE, error=err, code_field=CODE_FIELD))
        try:
            cfg = fb.validate({k: form.get(k, "") for k in fb.KEYS})
        except fb.ConfigError as exc:
            err = f'<p role="alert"><strong>{html.escape(str(exc))}</strong></p>'
            return self._send(400, FORM.format(style=STYLE, error=err,
                                               code_field="" if self._local() else CODE_FIELD))
        try:
            res = self.helper.apply(cfg)
        except HelperError as exc:
            if exc.kind == "configured":
                return self._send(409, "<p>This box is already set up.</p>")
            if exc.kind == "invalid":
                err = f'<p role="alert"><strong>{html.escape(str(exc))}</strong></p>'
                return self._send(400, FORM.format(style=STYLE, error=err,
                                                   code_field="" if self._local() else CODE_FIELD))
            return self._send(503, "<p>The setup helper could not apply this. Try again, or set up on the box screen.</p>")
        token, nxt = "", "This page stops answering in a few seconds."
        if cfg["role"] == "hub":
            t = res.get("token")
            if isinstance(t, str) and t:          # the helper hands it over once and deletes its copy
                token = ("<p>Your <strong>owner token</strong>. Copy it now: it is shown once and only its "
                         f"sha256 is kept.</p><p><code>{html.escape(t)}</code></p>")
            else:
                token = "<p>The owner token was printed on the box's console.</p>"
            nxt = "Reload this address in a minute for the dashboard."
        else:
            nxt = ("It now asks the hub to join: approve it on the hub's dashboard (Approvals) after checking "
                   "that the code shown there matches the one on this box's console. This page stops answering "
                   "in a few seconds.")
        self._send(200, DONE.format(style=STYLE, role=cfg["role"], token=token, next=nxt))
        self.done.set()


def main() -> int:
    Wizard.helper = Helper(os.environ.get("ONEMIND_SETUP_HELPER", HELPER_SOCK))
    try:
        if Wizard.helper.configured():
            print("onemind-setup: already configured; nothing to do")
            return 0
        # the helper writes it to /run/onemind/setup-code for the box screen and prints it on the console
        Wizard.gate.new(Wizard.helper.publish_code)
    except HelperError as exc:
        print(f"onemind-setup: {exc}", file=sys.stderr, flush=True)
        return 1                                   # Restart=on-failure tries again
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
