# SPDX-License-Identifier: Apache-2.0
"""Root helper of the setup wizard (#578). The web part (onemind_setup.py) runs as an unprivileged dynamic
user with no capabilities; it shows the form, checks the setup code and asks this helper to do the few
things that need root: publish the setup code for the box screen, and apply the form (configure() chowns
the data tree, writes /boot/efi and starts the role's units).

One request per connection (onemind-setup-helper.socket, Accept=yes), one JSON line each way:

  {"op": "status"}                                  -> {"ok": true, "configured": false}
  {"op": "publish-code", "code": "<10 symbols>"}    -> {"ok": true}
  {"op": "apply", "config": {"role": ..., ...}}     -> {"ok": true, "role": "hub", "token": "<shown once>"}

Anything else is refused ({"ok": false, "kind": ..., "error": ...}): unknown ops or fields, values that are
not short strings, a code outside the alphabet, a form onemind_firstboot.validate() rejects, and every
change once the box has an owner. The helper never trusts the web part's own checks.

Who may ask: the socket is 0666 (the web part's uid is allocated at start, so no fixed owner fits), and the
helper serves only a non-root process in the wizard's own cgroup (SO_PEERCRED, then /proc/<pid>/cgroup).
Other local users could reach the same form on the loopback page anyway; the cgroup check keeps the root
side to the one caller it was built for.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import socket
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import onemind_firstboot as fb  # noqa: E402

MAX_REQUEST = 8192
MAX_FIELD = 700                       # a join code is at most 640 characters (JOIN_CODE_RE)
CODE_FILE = "setup-code"              # in /run/onemind (tmpfs, 0600): the box screen reads it, a reboot clears it
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"   # no 0/O/1/I
CODE_LEN = 10
CODE_RE = re.compile(f"^[{ALPHABET}]{{{CODE_LEN}}}$")
UNIT_CGROUP = "/system.slice/onemind-setup.service"
FIELDS = {"status": {"op"}, "publish-code": {"op", "code"}, "apply": {"op", "config"}}
TIMEOUT_S = 10.0


class Refused(Exception):
    def __init__(self, kind: str, msg: str):
        super().__init__(msg)
        self.kind = kind


def _no(kind: str, msg: str) -> dict:
    return {"ok": False, "kind": kind, "error": msg}


def parse(raw: bytes) -> dict:
    """The request, checked field by field; raises Refused."""
    if len(raw) > MAX_REQUEST:
        raise Refused("bad-request", "request too large")
    try:
        req = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Refused("bad-request", "not a JSON request") from None
    if not isinstance(req, dict) or req.get("op") not in FIELDS:
        raise Refused("bad-request", "unknown request")
    op = req["op"]
    if set(req) != FIELDS[op]:
        raise Refused("bad-request", "unexpected fields")
    if op == "publish-code" and not (isinstance(req["code"], str) and CODE_RE.match(req["code"])):
        raise Refused("bad-request", "the setup code is not 10 symbols of the code alphabet")
    if op == "apply":
        cfg = req["config"]
        if (not isinstance(cfg, dict) or "role" not in cfg or set(cfg) - set(fb.KEYS)
                or not all(isinstance(v, str) and len(v) <= MAX_FIELD for v in cfg.values())):
            raise Refused("bad-request", "config must map role, name, join_code, hub_addr to short text")
        try:
            req = {"op": op, "config": fb.validate({k: cfg.get(k, "") for k in fb.KEYS})}
        except fb.ConfigError as exc:
            raise Refused("invalid", str(exc)) from None
    return req


class _Lock:
    """One change at a time: Accept=yes runs one helper per connection, so two posts could race."""

    def __init__(self, p: fb.Paths):
        fb.run_dir(p)
        self.fd = os.open(os.path.join(p.run, "setup-helper.lock"), os.O_RDWR | os.O_CREAT, 0o600)

    def __enter__(self):
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        os.close(self.fd)


def handle(p: fb.Paths, raw: bytes) -> dict:
    """Answer one request (never raises for anything the caller sent)."""
    try:
        req = parse(raw)
    except Refused as exc:
        return _no(exc.kind, str(exc))
    if req["op"] == "status":
        return {"ok": True, "configured": fb.load_state(p) is not None}
    with _Lock(p):
        if fb.load_state(p) is not None:
            return _no("configured", "This box is already set up.")
        code_path = os.path.join(p.run, CODE_FILE)
        if req["op"] == "publish-code":
            fb.write(code_path, req["code"] + "\n", 0o600)
            fb.console(p, f"ONEMIND SETUP CODE: {req['code']} (type it on the setup page from another device)")
            return {"ok": True}
        cfg = req["config"]
        fb.finish(p, cfg, "wizard")
        token = None
        tok_path = os.path.join(p.run, "owner-token")
        if cfg["role"] == "hub":
            try:
                with open(tok_path) as f:
                    token = f.read().strip() or None
                os.unlink(tok_path)                          # shown once, on the page that asked
            except OSError:
                token = None                                 # the page then points at the console
        try:
            os.unlink(code_path)                             # the code is spent
        except OSError:
            pass
        return {"ok": True, "role": cfg["role"], "token": token}


# ------------------------------------------------------------------ who may ask
def cgroup_ok(text: str) -> bool:
    """True when a /proc/<pid>/cgroup (cgroup v2 line "0::<path>") names the wizard unit itself."""
    for line in text.splitlines():
        if line.startswith("0::"):
            return line[3:] == UNIT_CGROUP
    return False


def _read_cgroup(pid: int) -> str:
    with open(f"/proc/{pid}/cgroup") as f:
        return f.read()


def peer_allowed(pid: int, uid: int, read_cgroup=_read_cgroup) -> bool:
    """A non-root process of onemind-setup.service. Root is refused: the web part must never run as root,
    and a root caller has no need for this door."""
    if pid <= 0 or uid == 0:
        return False
    try:
        return cgroup_ok(read_cgroup(pid))
    except OSError:
        return False


def peer_of(conn: socket.socket) -> bool:
    pid, uid, _gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    return peer_allowed(pid, uid)


def _recv(conn: socket.socket) -> bytes:
    """Up to one line (or until the caller closes its side), at most MAX_REQUEST + 1 bytes."""
    buf = b""
    while len(buf) <= MAX_REQUEST and b"\n" not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf if len(buf) > MAX_REQUEST else buf.split(b"\n", 1)[0]


def serve(p: fb.Paths, conn: socket.socket, check=peer_of) -> None:
    """Answer the one request on an accepted connection."""
    conn.settimeout(TIMEOUT_S)
    try:
        raw = _recv(conn)        # read (bounded) even when refusing: closing on unread data resets the caller
        try:
            resp = handle(p, raw) if check(conn) else _no("forbidden", "only the setup wizard may ask")
        except Exception as exc:  # noqa: BLE001 - the caller gets an answer; the journal gets the reason
            print(f"onemind-setup-helper: failed ({exc.__class__.__name__}: {exc})", file=sys.stderr, flush=True)
            resp = _no("failed", "the setup could not be applied; see the journal")
        conn.sendall(json.dumps(resp).encode() + b"\n")
    except OSError:
        pass


def main() -> int:
    # systemd hands the accepted connection over as stdin (StandardInput=socket); stdout is the journal,
    # so log lines of onemind_firstboot (and the units it starts) never reach the caller.
    conn = socket.socket(fileno=os.dup(0))
    try:
        serve(fb.Paths(os.environ.get("ONEMIND_FIRSTBOOT_ROOT", "/")), conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
