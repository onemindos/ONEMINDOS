# SPDX-License-Identifier: Apache-2.0
"""Remote access over Tor (NET-TOR-01, D-014): the owner page and the device keys.

Python standard library only. Two commands:

  tor_access.py init   (init container) write the torrc and the onion folder, then exit
  tor_access.py serve  (the owner page) show the .onion address, add and remove devices

How it stays closed:
- Tor client authorization (onion services v3): only a device whose key is in
  authorized_clients/ can even fetch the onion descriptor. The folder always holds one lock key
  whose private half is thrown away, so with zero devices nobody can connect. Tor publishes an
  onion service with no keys to everyone, so the lock is what keeps an empty list closed.
- A device's private key is shown once and never stored: only its public half is on disk.
- `SocksPort 0`: Tor here is never an outbound proxy for apps, agents or AI. No ORPort, never a
  relay or an exit. The onion service forwards to the OneMind dashboard only, where the normal
  sign-in applies.
- The page answers only the owner (X-OneMind-Role from the gateway's app proxy) and refuses a
  POST whose Origin is not this app's own host.
"""

from __future__ import annotations

import base64
import html
import ipaddress
import os
import re
import secrets
import socket
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("TOR_DATA", "/var/lib/tor"))
TORRC = Path(os.environ.get("TORRC", "/etc/onemind-tor/torrc"))
PORT = int(os.environ.get("PORT", "8080"))
# Where the onion service forwards: the box's OneMind dashboard, as ip:port. The gateway hands it
# to the app (ConfigMap onemind-gateway-path); without it the app does not start.
TARGET_ENV = "ONEMIND_DASHBOARD_TARGET"
LOCK = "onemind-lock"
MAX_DEVICES = 16
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,31}$")
ONION_RE = re.compile(r"^[a-z2-7]{56}\.onion$")


def onion_dir(data: Path = DATA) -> Path:
    return data / "onion"


def clients_dir(data: Path = DATA) -> Path:
    return onion_dir(data) / "authorized_clients"


# ---- X25519 (RFC 7748 section 5), for Tor client authorization keys ----------------------------

_P = 2**255 - 19


def x25519(k: bytes, u: bytes) -> bytes:
    """The X25519 function: scalar k times point u, both 32 bytes little-endian."""
    if len(k) != 32 or len(u) != 32:
        raise ValueError("X25519 takes 32-byte inputs")
    kb = bytearray(k)
    kb[0] &= 248
    kb[31] &= 127
    kb[31] |= 64
    scalar = int.from_bytes(kb, "little")
    x1 = int.from_bytes(u, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in reversed(range(255)):
        bit = (scalar >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a, b = (x2 + z2) % _P, (x2 - z2) % _P
        aa, bb = a * a % _P, b * b % _P
        e = (aa - bb) % _P
        c, d = (x3 + z3) % _P, (x3 - z3) % _P
        da, cb = d * a % _P, c * b % _P
        x3, z3 = (da + cb) ** 2 % _P, x1 * (da - cb) ** 2 % _P
        x2, z2 = aa * bb % _P, e * (aa + 121665 * e) % _P
    if swap:
        x2, x3, z2, z3 = x3, x2, z3, z2
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, "little")


def b32(raw: bytes) -> str:
    return base64.b32encode(raw).decode().rstrip("=")


def new_client_key() -> tuple[str, str]:
    """(public, private) in Tor's base32 form. Tor clamps the private key itself."""
    private = secrets.token_bytes(32)
    public = x25519(private, (9).to_bytes(32, "little"))
    return b32(public), b32(private)


# ---- the onion folder ---------------------------------------------------------------------------

def slug(name: str) -> str:
    return re.sub(r"[ _]+", "-", name.strip().lower())


def write_private(path: Path, text: str) -> None:
    """Write a file the way Tor wants it (owner only), atomically."""
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def ensure_lock(data: Path = DATA) -> None:
    """Make the onion folder and keep the lock key in it, so an empty device list stays closed."""
    for d in (onion_dir(data), clients_dir(data)):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        d.chmod(0o700)
    lock = clients_dir(data) / f"{LOCK}.auth"
    if not lock.is_file():
        public, _ = new_client_key()  # the private half is dropped here: nobody holds it
        write_private(lock, f"descriptor:x25519:{public}\n")


def devices(data: Path = DATA) -> list[str]:
    d = clients_dir(data)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.auth") if p.stem != LOCK)


def onion_address(data: Path = DATA) -> str | None:
    try:
        text = (onion_dir(data) / "hostname").read_text().strip()
    except OSError:
        return None
    return text if ONION_RE.fullmatch(text) else None


def add_device(name: str, data: Path = DATA) -> tuple[str, str]:
    """Authorize a new device. Returns (slug, the private key line for Tor Browser or Orbot)."""
    if not NAME_RE.fullmatch(name or ""):
        raise ValueError("Use 1 to 32 letters, digits, spaces, - or _.")
    s = slug(name)
    if s == LOCK:
        raise ValueError("That name is reserved.")
    if s in devices(data):
        raise ValueError("A device with that name already exists.")
    if len(devices(data)) >= MAX_DEVICES:
        raise ValueError(f"At most {MAX_DEVICES} devices.")
    address = onion_address(data)
    if address is None:
        raise ValueError("Tor has not made the address yet. Try again in a minute.")
    ensure_lock(data)
    public, private = new_client_key()
    write_private(clients_dir(data) / f"{s}.auth", f"descriptor:x25519:{public}\n")
    return s, f"{address.removesuffix('.onion')}:descriptor:x25519:{private}"


def remove_device(s: str, data: Path = DATA) -> bool:
    if s == LOCK or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", s):
        return False
    path = clients_dir(data) / f"{s}.auth"
    if not path.is_file():
        return False
    path.unlink()
    return True


# ---- Tor: the config and a reload over its control socket --------------------------------------

def parse_target(value: str | None) -> tuple[str, int]:
    """ip:port or [ipv6]:port. Tor's HiddenServicePort takes an address, not a name."""
    m = re.fullmatch(r"\[([0-9A-Fa-f:.]+)\]:(\d{1,5})|([0-9.]+):(\d{1,5})", (value or "").strip())
    if not m:
        raise ValueError(f"{TARGET_ENV} must be ip:port")
    host, port = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    addr, n = ipaddress.ip_address(host), int(port)
    if not 1 <= n <= 65535 or addr.is_unspecified or addr.is_multicast:
        raise ValueError(f"{TARGET_ENV} must be ip:port")
    return str(addr), n


def render_torrc(target: tuple[str, int], data: Path = DATA) -> str:
    host, port = target
    where = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return "\n".join([
        "# Written by tor_access.py init. Onion service only (NET-TOR-01, D-014).",
        f"DataDirectory {data}/data",
        "Log notice stdout",
        "# Never a proxy for anything on the box: no SOCKS, DNS, transparent or HTTP tunnel ports.",
        "SocksPort 0",
        "DNSPort 0",
        "TransPort 0",
        "NATDPort 0",
        "HTTPTunnelPort 0",
        "# Never a relay, a directory mirror or an exit.",
        "ORPort 0",
        "DirPort 0",
        "ClientOnly 1",
        "ExitRelay 0",
        "ExitPolicy reject *:*",
        "# The owner page reloads Tor after a device change through this socket (no TCP port).",
        f"ControlSocket unix:{data}/data/control.sock",
        "CookieAuthentication 1",
        f"CookieAuthFile {data}/data/control.cookie",
        "# The onion service: port 80 of the .onion goes to the OneMind dashboard, nothing else.",
        f"HiddenServiceDir {data}/onion",
        f"HiddenServicePort 80 {where}",
        "HiddenServiceEnableIntroDoSDefense 1",
        "",
    ])


def reload_tor(data: Path = DATA, timeout: float = 5.0, *, cut: bool = False) -> None:
    """Make Tor apply authorized_clients/. Raises OSError when Tor does not confirm.

    Adding a device: SIGNAL RELOAD, nobody is disconnected. Removing one: SIGNAL HALT. A reload
    refuses the removed key only for new connections; a circuit the device already has stays open
    (seen with tor 0.4.9.17). Tor exits, the pod restarts it with the same onion key, and every
    open circuit is gone, so the removed device is cut off at once.
    """
    ensure_lock(data)
    cookie = (data / "data" / "control.cookie").read_bytes().hex()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(data / "data" / "control.sock"))
        f = s.makefile("rwb")
        for command in (f"AUTHENTICATE {cookie}", "SIGNAL HALT" if cut else "SIGNAL RELOAD"):
            f.write(command.encode() + b"\r\n")
            f.flush()
            reply = f.readline().decode("ascii", "replace").strip()
            if cut and command == "SIGNAL HALT" and reply == "":
                return  # Tor may close the socket as it exits instead of answering
            if not reply.startswith("250"):
                raise OSError(f"Tor refused {command.split()[0]}: {reply[:80]}")
        if not cut:
            f.write(b"QUIT\r\n")
            f.flush()


def init(data: Path = DATA, torrc: Path = TORRC) -> int:
    try:
        target = parse_target(os.environ.get(TARGET_ENV))
    except ValueError as exc:
        print(f"tor-remote-access: {exc}. This OneMind does not give the app the dashboard address yet.",
              file=sys.stderr)
        return 1
    ensure_lock(data)
    # Tor makes the control socket only in a folder that exists and only its user can open.
    (data / "data").mkdir(mode=0o700, exist_ok=True)
    (data / "data").chmod(0o700)
    torrc.write_text(render_torrc(target, data))
    return 0


# ---- the owner page ------------------------------------------------------------------------------

STYLE = ("body{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem}"
         "code,textarea{font:14px ui-monospace,monospace;word-break:break-all}"
         "textarea{width:100%;height:6rem}.note{color:#555}")


def page(title: str, body: str) -> bytes:
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>{html.escape(title)}</title><style>{STYLE}</style><h1>{html.escape(title)}</h1>{body}"
            ).encode()


def home(data: Path = DATA) -> bytes:
    address = onion_address(data)
    where = (f"<p>This box's address: <code>{html.escape(address)}</code></p>" if address
             else "<p>Tor is still making this box's address. Reload in a minute.</p>")
    rows = "".join(
        f"<li>{html.escape(d)} <form method=post action='/devices/{html.escape(d)}/delete' style=display:inline>"
        f"<button>Remove</button></form></li>" for d in devices(data)) or "<li>No devices yet. Nobody can connect.</li>"
    return page("Remote access over Tor", (
        "<p class=note>Advanced, and slower than the mesh: use the mesh when you can. Only devices you add here "
        "can reach the address, and they still sign in to OneMind.</p>"
        f"{where}<h2>Devices</h2><ul>{rows}</ul>"
        "<p class=note>Removing a device restarts Tor so it is cut off at once; the others reconnect within "
        "about a minute.</p>"
        "<form method=post action=/devices><label>New device name <input name=name maxlength=32 required></label> "
        "<button>Add device</button></form>"))


def added(name: str, line: str) -> bytes:
    return page("Device added", (
        f"<p>The key for <b>{html.escape(name)}</b> is shown <b>once</b>. Save it now.</p>"
        f"<textarea readonly>{html.escape(line)}</textarea>"
        "<p>Tor Browser: open the .onion address, and when it asks for a key, paste the part after "
        "<code>x25519:</code>. Orbot or a tor client: save the whole line as a file ending in "
        "<code>.auth_private</code> in its ClientOnionAuthDir.</p><p><a href=/>Back</a></p>"))


class Handler(BaseHTTPRequestHandler):
    server_version = "onemind-tor"
    sys_version = ""
    data = DATA
    reload = staticmethod(reload_tor)

    def _send(self, status: int, body: bytes, ctype: str = "text/html; charset=utf-8", location: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(body)

    def _owner(self) -> bool:
        if self.headers.get("X-OneMind-Role") == "owner":
            return True
        self._send(403, page("Owner only", "<p>Only the box's owner can manage remote access.</p>"))
        return False

    def do_GET(self):  # noqa: N802 (http.server API)
        if self.path == "/healthz":
            return self._send(200, b"ok\n", "text/plain")
        if not self._owner():
            return
        if self.path != "/":
            return self._send(404, page("Not found", "<p><a href=/>Back</a></p>"))
        self._send(200, home(self.data))

    def do_POST(self):  # noqa: N802
        if not self._owner():
            return
        origin = urllib.parse.urlsplit(self.headers.get("Origin") or "")
        if not origin.hostname or origin.netloc != (self.headers.get("X-Forwarded-Host") or self.headers.get("Host")):
            return self._send(403, page("Refused", "<p>This form must be sent from this page.</p>"))
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1024:
            return self._send(413, page("Too large", ""))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        m = re.fullmatch(r"/devices/([a-z0-9_-]{1,32})/delete", self.path)
        if self.path == "/devices":
            try:
                s, line = add_device((form.get("name") or [""])[0], self.data)
            except ValueError as exc:
                return self._send(400, page("Not added", f"<p>{html.escape(str(exc))}</p><p><a href=/>Back</a></p>"))
            return self._reload_then(added(s, line))
        if m:
            if not remove_device(m.group(1), self.data):
                return self._send(404, page("No such device", "<p><a href=/>Back</a></p>"))
            return self._reload_then(None)
        self._send(404, page("Not found", ""))

    def _reload_then(self, body: bytes | None) -> None:
        try:
            self.reload(self.data, cut=body is None)
        except OSError:
            return self._send(503, page("Tor did not confirm", (
                "<p>The device list changed, but Tor did not confirm it re-read the list. Restart the app "
                "from the OneMind dashboard to be sure.</p>" + (body.decode() if body else ""))))
        if body is None:
            return self._send(303, b"", location="/")
        self._send(200, body)

    def log_message(self, *_):
        pass  # no addresses or device names in the logs


def serve(data: Path = DATA, port: int = PORT) -> None:
    Handler.data = data
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104 (pod network only)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "init":
        sys.exit(init())
    if command == "serve":
        serve()
    print("usage: tor_access.py init|serve", file=sys.stderr)
    sys.exit(2)
