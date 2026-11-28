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

The box's own monitor (kiosk, on by default since 2026-11-28) opens this page on loopback, so the person at
the box sets it up there. For a phone or computer instead, the loopback page shows the LAN address, its QR code
and the setup code, the same facts the text screen shows: only the box itself is ever served the code. The
form also asks whether that monitor keeps showing the OneMind desktop after setup (`kiosk`, a hub only).
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
import onemind_screen as screen  # noqa: E402  (the QR encoder the text screen uses)
from onemind_setup_helper import ALPHABET, CODE_LEN  # noqa: E402,F401  (one definition of the code)

MAX_BODY = 8192
HELPER_SOCK = "/run/onemind-setup-helper.sock"   # onemind-setup-helper.socket
MAX_REPLY = 65536
# Every helper connection starts a root process (Accept=yes), so page requests never ask it directly: the
# owner question goes to the helper at most once per STATUS_TTL_S, however many requests the LAN sends.
STATUS_TTL_S = 5.0
MAX_WRONG = 5                 # wrong codes from the LAN (all clients together) before a back-off
LOCK_MIN_S, LOCK_MAX_S = 60.0, 900.0   # back-off: 1 min, doubling to 15 min
STYLE = ("body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
         "label{display:block;margin:.6rem 0}input[type=text]{width:100%;padding:.4rem}"
         "code{word-break:break-all;background:#eee;padding:.2rem .4rem}button{padding:.5rem 1rem}"
         ".phone{border:1px solid #ccc;border-radius:.5rem;padding:.5rem 1rem;margin:1rem 0}"
         ".phone svg{width:9rem;height:9rem;float:right;margin-left:1rem}.phone strong{letter-spacing:.1em}")

FORM = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OneMind setup</title><style>{style}</style></head><body>
<h1>Set up this OneMind box</h1>{error}{phone}
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
{kiosk_field}
<button type="submit">Set up</button></form></body></html>"""

DONE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OneMind setup</title><style>{style}</style></head><body>
<h1>Done: this box is a {role}</h1>{token}
<p>The OneMind services are starting. {next}</p>{cont}</body></html>"""


CODE_FIELD = ('<label>Setup code shown on the box screen <input type="text" name="code" autocapitalize="characters" '
              'autocomplete="off" maxlength="16" required></label>')


KIOSK_FIELD = """<fieldset><legend>This box's own monitor (hub only)</legend>
<label><input type="radio" name="kiosk" value="on" checked> Show the OneMind desktop full screen</label>
<label><input type="radio" name="kiosk" value="off"> Show a text screen with the address only</label>
</fieldset>"""

# On the box's own monitor only: once the gateway answers on this port, the button opens the desktop's sign-in.
# It never leaves by itself, so the owner token above stays on screen until the person has copied it.
CONTINUE = """<p><button type="button" id="go" disabled>Starting OneMind...</button></p>
<script>(function(){var b=document.getElementById("go");function poll(){fetch("/healthz",{cache:"no-store"})
.then(function(r){return r.ok?r.text():"";}).then(function(t){if(t&&t.trim()!=="setup"){b.disabled=false;
b.textContent="Continue to the OneMind desktop";b.onclick=function(){location.replace("/"+location.search);};}else{setTimeout(poll,3000);}})
.catch(function(){setTimeout(poll,3000);});}setTimeout(poll,3000);})();</script>"""


# The owner token on the done page is hidden again once it was copied, or after two minutes, so a monitor left
# on this page (the box's own screen) does not keep showing it. The page stays; nothing navigates away.
MASK = """<p><button type="button" id="copy">Copy the token</button></p>
<script>(function(){var c=document.querySelector("code"),b=document.getElementById("copy");if(!c)return;
function hide(){c.textContent="(hidden: it was shown once)";b.disabled=true;}
b.onclick=function(){var t=c.textContent;(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject())
.then(hide,function(){var r=document.createRange();r.selectNodeContents(c);var s=getSelection();s.removeAllRanges();s.addRange(r);
document.execCommand("copy");hide();});};setTimeout(hide,120000);})();</script>"""


def kiosk_field() -> str:
    """The monitor question, only on an image that can show the desktop (it ships the compositor)."""
    return KIOSK_FIELD if os.path.exists(fb.KIOSK_COMPOSITOR) else ""


def lan_address() -> str | None:
    """The box's LAN address, without netlink (the wizard's sandbox allows only AF_INET, AF_INET6 and AF_UNIX):
    the source address the kernel picks for a route out. A UDP connect sends nothing. None with no route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))           # TEST-NET-1: never answered, only routed
            addr = s.getsockname()[0]
    except OSError:
        return None
    return None if addr.startswith(("127.", "0.")) else addr


def qr_svg(text: str) -> str:
    """The QR code of `text` as an inline SVG (dark modules on white, two-module quiet zone)."""
    m = screen.qr_matrix(text)
    n = len(m) + 4
    cells = "".join(f'<rect x="{c + 2}" y="{r + 2}" width="1" height="1"/>'
                    for r, row in enumerate(m) for c, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" role="img" aria-label="QR code of the '
            f'setup address" shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<g fill="#000">{cells}</g></svg>')


def phone_panel(code: str, addr: str | None, host: str) -> str:
    """What the box's own monitor shows so a phone can do the setup instead: the address, its QR code and the
    one-time code. Served to loopback only (the caller checks), like the text screen that shows the same."""
    url = f"http://{addr}:{fb_port()}/" if addr else f"http://{host}.local:{fb_port()}/"
    qr = qr_svg(url)
    code_line = (f"<p>Setup code (the page asks for it): <strong>{html.escape(code)}</strong></p>" if code else "")
    return (f'<div class="phone">{qr}<p>Setting up from a phone or computer instead? On the same network, open '
            f'<code>{html.escape(url)}</code> or scan the code.</p>{code_line}</div>')


def fb_port() -> int:
    return int(os.environ.get("ONEMIND_SETUP_PORT", "8080"))


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
    `call` replaces the socket transport (the tests run the helper's handle() in-process).

    configured() keeps the helper's answer: "set up" never changes back (a box gets an owner once), and
    "not set up yet" (or no answer) is asked again at most once per STATUS_TTL_S. A flood of LAN requests
    therefore costs the helper a bounded number of connections and never trips the socket's limits."""

    def __init__(self, path: str = HELPER_SOCK, call=None, clock=time.monotonic):
        self.path = path
        self._call = call or self._socket_call
        self.clock = clock
        self._lock = threading.Lock()
        self._owner = False                      # sticky: the box has an owner
        self._asking = False                     # one status question at a time
        self._next = 0.0                         # no new status question before this time
        self._err: HelperError | None = HelperError("unavailable", "the setup helper has not answered yet")

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
            kind = str(resp.get("kind", "unavailable"))
            if kind == "configured":
                self._set_owner()
            raise HelperError(kind, str(resp.get("error", "the setup helper failed")))
        return resp

    def _set_owner(self) -> None:
        with self._lock:
            self._owner = True

    def configured(self) -> bool:
        """Whether the box has an owner. Raises HelperError while the helper's last answer is missing, so the
        caller fails closed. At most one question per STATUS_TTL_S; meanwhile the last answer stands."""
        with self._lock:
            if self._owner:
                return True
            if self._asking or self.clock() < self._next:
                if self._err is not None:
                    raise self._err
                return False
            self._asking = True
            self._next = self.clock() + STATUS_TTL_S
        owner, err = False, None
        try:
            owner = self.call("status").get("configured") is True
        except HelperError as exc:
            err = exc
        with self._lock:
            self._asking = False
            self._owner = self._owner or owner
            self._err = None if self._owner else err
            if self._owner:
                return True
        if err is not None:
            raise err
        return False

    def publish_code(self, code: str) -> None:
        self.call("publish-code", code=code)

    def apply(self, cfg: dict) -> dict:
        res = self.call("apply", config=cfg)
        self._set_owner()                        # the box has its owner now: no more status questions
        return res


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

    def _form(self, error: str) -> str:
        """The form for this client: the box itself gets the phone panel and no code field; the LAN gets the
        code field and never the code."""
        local = self._local()
        phone = phone_panel(self.gate.code, lan_address(), socket.gethostname()) if local else ""
        return FORM.format(style=STYLE, error=error, phone=phone, code_field="" if local else CODE_FIELD,
                           kiosk_field=kiosk_field())

    def do_GET(self):
        if self._refuse_lan():
            return
        if self.path.split("?")[0] == "/healthz":
            # the box screen asks from loopback; the LAN learns nothing from this box before the code
            return self._send(200 if self._local() else 403, "setup" if self._local() else "forbidden")
        self._send(200, self._form(""))

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
            return self._send(429 if wait else 403, self._form(err))
        try:
            cfg = fb.validate({k: form.get(k, "") for k in fb.KEYS})
        except fb.ConfigError as exc:
            err = f'<p role="alert"><strong>{html.escape(str(exc))}</strong></p>'
            return self._send(400, self._form(err))
        try:
            res = self.helper.apply(cfg)
        except HelperError as exc:
            if exc.kind == "configured":
                return self._send(409, "<p>This box is already set up.</p>")
            if exc.kind == "invalid":
                err = f'<p role="alert"><strong>{html.escape(str(exc))}</strong></p>'
                return self._send(400, self._form(err))
            return self._send(503, "<p>The setup helper could not apply this. Try again, or set up on the box screen.</p>")
        token, nxt = "", "This page stops answering in a few seconds."
        if cfg["role"] == "hub":
            t = res.get("token")
            if isinstance(t, str) and t:          # the helper hands it over once and deletes its copy
                token = ("<p>Your <strong>owner token</strong>. Copy it now: it is shown once and only its "
                         f"sha256 is kept.</p><p><code>{html.escape(t)}</code></p>" + MASK)
            else:
                token = "<p>The owner token was printed on the box's console.</p>"
            nxt = "Reload this address in a minute for the dashboard."
        else:
            nxt = ("It now asks the hub to join: approve it on the hub's dashboard (Approvals) after checking "
                   "that the code shown there matches the one on this box's console. This page stops answering "
                   "in a few seconds.")
        cont = CONTINUE if cfg["role"] == "hub" and self._local() else ""
        self._send(200, DONE.format(style=STYLE, role=cfg["role"], token=token, next=nxt, cont=cont))
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
