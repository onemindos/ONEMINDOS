#!/usr/bin/python3 -I
# SPDX-License-Identifier: Apache-2.0
"""OneMind USB installer (os/boards/installer-x86_64/README.md, docs/leap/core/IMAGES.md §7).

A live system on a USB stick that writes the OneMind x86_64-efi disk image to a disk of this
computer, checks it byte for byte, sets the first-boot role and reboots into OneMind.

  onemind_installer.py tui               plain-text menu (runs on the screen, tty1, and the serial console)
  onemind_installer.py web [--port 8080] minimal LAN page; installs need the one-time code
  onemind_installer.py list              the disks it would offer, as JSON

The install (one function, used by both front ends):
  1. the payload's own sha256 is checked (payload.json, written at build time);
  2. the image is streamed through `zstd -dc` onto the disk; all-zero blocks are written with
     BLKZEROOUT, so old data never survives in them; the stream's sha256 must equal the image's;
  3. the disk's cache is dropped and the whole image range is read back: sha256 must match again;
  4. the GPT backup header is moved to the end of the disk and onemind-data grows to fill it;
  5. onemind.conf on the target's ESP gets the role (onemind-firstboot reads it, IMAGES.md §3);
  6. the firmware's next boot is set to the target (efibootmgr), then the machine reboots.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import stat
import struct
import subprocess
import sys
import threading
import time
import urllib.parse

PREFIX = "ONEMIND-INSTALLER:"
CONFIRM_WORD = "ERASE"
PAYLOAD_DIR = "/usr/share/onemind-installer/payload"
STICK_PARTLABELS = ("onemind-installer-root", "onemind-installer-esp")
RUN_DIR = "/run/onemind-installer"
LOCK = os.path.join(RUN_DIR, "install.lock")
CODE_FILE = os.path.join(RUN_DIR, "web-code")
CHUNK = 4 << 20
BLKZEROOUT = 0x127F
BLKFLSBUF = 0x1261
BLKGETSIZE64 = 0x80081272
MAX_WEB_ATTEMPTS = 5

# Same rules as onemind-firstboot's validate() (test/unit/test_installer.py checks they agree).
ROLES = ("hub", "worker", "leaf")
HOST_RE = re.compile(r"^(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9]{32,128}$")
NAME_RE = re.compile(r"^[^\x00-\x1f\"\\#=]{1,64}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class InstallError(RuntimeError):
    pass


def say(msg: str) -> None:
    print(f"{PREFIX} {msg}", flush=True)


# ------------------------------------------------------------------ payload
def load_payload(d: str = PAYLOAD_DIR) -> dict:
    with open(os.path.join(d, "payload.json"), encoding="utf-8") as f:
        p = json.load(f)
    for k in ("board", "version", "image", "image_size", "image_sha256", "file", "file_sha256"):
        if k not in p:
            raise InstallError(f"payload.json lacks {k}")
    if not (HEX64.match(p["image_sha256"]) and HEX64.match(p["file_sha256"])):
        raise InstallError("payload.json: sha256 values must be 64 lowercase hex digits")
    if not isinstance(p["image_size"], int) or p["image_size"] <= 0 or p["image_size"] % 512:
        raise InstallError("payload.json: image_size must be a positive multiple of 512")
    if os.path.basename(p["file"]) != p["file"]:
        raise InstallError("payload.json: file must be a plain file name")
    p["path"] = os.path.join(d, p["file"])
    return p


def sha256_file(path: str, progress=None) -> str:
    h, done, size = hashlib.sha256(), 0, os.path.getsize(path)
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(CHUNK), b""):
            h.update(buf)
            done += len(buf)
            if progress:
                progress("checking the installer's copy", done, size)
    return h.hexdigest()


# ------------------------------------------------------------------ disks
def human(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n < 1e12 else f"{n / 1e12:.2f} TB"


def _mounts(dev: dict) -> list:
    m = list(dev.get("mountpoints") or [])
    if dev.get("mountpoint"):
        m.append(dev["mountpoint"])
    return [x for x in m if x]


def _walk(dev: dict):
    yield dev
    for c in dev.get("children") or []:
        yield from _walk(c)


def classify_disks(lsblk: dict, min_size: int) -> tuple[list[dict], list[dict]]:
    """lsblk -J -b output -> (targets offered, disks not offered with the reason)."""
    targets, skipped = [], []
    for dev in lsblk.get("blockdevices", []):
        if dev.get("type") != "disk" or re.match(r"^(loop|ram|zram|sr|fd|nbd)", dev.get("name", "")):
            continue
        d = {"path": dev.get("path") or "/dev/" + dev["name"], "name": dev["name"], "size": int(dev.get("size") or 0),
             "model": (dev.get("model") or "").strip(), "serial": (dev.get("serial") or "").strip(),
             "tran": (dev.get("tran") or "").strip()}
        labels = [c.get("partlabel") for c in _walk(dev)]
        reason = None
        if any(l in STICK_PARTLABELS for l in labels):
            reason = "this installer stick"
        elif str(dev.get("ro")) in ("1", "True", "true"):
            reason = "read-only"
        elif any(_mounts(c) for c in _walk(dev)):
            reason = "in use (mounted)"
        elif d["size"] < min_size:
            reason = f"too small (needs {human(min_size)})"
        (skipped if reason else targets).append(dict(d, reason=reason) if reason else d)
    return targets, skipped


def scan_disks(min_size: int) -> tuple[list[dict], list[dict]]:
    subprocess.run(["udevadm", "settle", "--timeout=10"], capture_output=True)
    out = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,TYPE,RO,MODEL,SERIAL,TRAN,PARTLABEL,MOUNTPOINTS"],
                         check=True, capture_output=True, text=True).stdout
    return classify_disks(json.loads(out), min_size)


def describe(d: dict) -> str:
    bits = [d["path"], human(d["size"]), d.get("tran", "").upper(), d.get("model", "")]
    if d.get("serial"):
        bits.append(f"({d['serial']})")
    return "  ".join(b for b in bits if b)


# ------------------------------------------------------------------ role
def make_settings(role: str, name: str = "", hub: str = "", join_token: str = "") -> dict | None:
    """Validated first-boot settings, or None for 'setup' (decide in the wizard at first boot)."""
    role = (role or "").strip().lower()
    if role in ("setup", "wizard", ""):
        return None
    if role not in ROLES:
        raise InstallError(f"role must be hub, worker, leaf or setup (got {role!r})")
    out = {"role": role, "name": (name or "").strip() or "OneMind"}
    if not NAME_RE.match(out["name"]):
        raise InstallError("name: 1-64 printable characters, no quotes, backslashes, '#' or '='")
    if role in ("worker", "leaf"):
        hub = (hub or "").strip()
        if not HOST_RE.match(hub):
            raise InstallError("hub: the hub's host name or address is required for this role")
        if not TOKEN_RE.match((join_token or "").strip()):
            raise InstallError("join_token: the hub's join token (32-128 letters and digits) is required")
        out.update(hub=hub, join_token=join_token.strip())
    return out


def render_conf(s: dict) -> str:
    lines = ["# SPDX-License-Identifier: Apache-2.0",
             "# Written by the OneMind USB installer. Read once by onemind-firstboot at the first boot",
             "# (docs/leap/core/IMAGES.md §3), then renamed onemind.conf.applied.",
             f"role = {s['role']}", f"name = {s['name']}"]
    if s["role"] in ("worker", "leaf"):
        lines += [f"hub = {s['hub']}", f"join_token = {s['join_token']}"]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ write and verify
def _is_blk(fd: int) -> bool:
    return stat.S_ISBLK(os.fstat(fd).st_mode)


def dev_size(fd: int) -> int:
    if _is_blk(fd):
        return struct.unpack("Q", fcntl.ioctl(fd, BLKGETSIZE64, b"\0" * 8))[0]
    return os.fstat(fd).st_size


def _zero(fd: int, off: int, n: int, blk: bool) -> None:
    if blk:
        try:
            fcntl.ioctl(fd, BLKZEROOUT, struct.pack("QQ", off, n))
            return
        except OSError:
            pass  # fall back to writing zeros
    os.pwrite(fd, bytes(n), off)


def write_image(stream, fd: int, size: int, want_sha: str, progress=None) -> str:
    """Copy exactly `size` bytes from `stream` to fd at offset 0; zero blocks are zeroed on the
    device (never skipped). Raises InstallError on a short or long stream or a sha256 mismatch."""
    h, off, blk, zeros = hashlib.sha256(), 0, _is_blk(fd), bytes(CHUNK)
    while off < size:
        buf = stream.read(min(CHUNK, size - off))
        if not buf:
            raise InstallError(f"image stream ended early at {off} of {size} bytes")
        h.update(buf)
        if buf == zeros[:len(buf)]:
            _zero(fd, off, len(buf), blk)
        else:
            view, pos = memoryview(buf), 0
            while pos < len(buf):
                pos += os.pwrite(fd, view[pos:], off + pos)
        off += len(buf)
        if progress:
            progress("writing", off, size)
    if stream.read(1):
        raise InstallError("image stream is longer than the image size in payload.json")
    os.fsync(fd)
    got = h.hexdigest()
    if got != want_sha:
        raise InstallError(f"written stream sha256 {got} != image sha256 {want_sha}")
    return got


def read_back(fd: int, size: int, progress=None) -> str:
    """sha256 of the first `size` bytes as the device returns them (cache dropped first)."""
    os.fsync(fd)
    if _is_blk(fd):
        try:
            fcntl.ioctl(fd, BLKFLSBUF, 0)
        except OSError:
            pass
    if hasattr(os, "posix_fadvise"):       # Linux; absent on macOS (unit tests)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    h, off = hashlib.sha256(), 0
    while off < size:
        buf = os.pread(fd, min(CHUNK, size - off), off)
        if not buf:
            raise InstallError(f"read-back ended early at {off} of {size} bytes")
        h.update(buf)
        off += len(buf)
        if progress:
            progress("verifying", off, size)
    return h.hexdigest()


def parse_sgdisk_info(text: str) -> dict:
    g = lambda rx: (re.search(rx, text, re.M) or [None, None])[1]
    return {"type": g(r"^Partition GUID code: ([0-9A-Fa-f-]{36})"), "guid": g(r"^Partition unique GUID: ([0-9A-Fa-f-]{36})"),
            "first": int(g(r"^First sector: (\d+)") or -1), "last": int(g(r"^Last sector: (\d+)") or -1),
            "name": g(r"^Partition name: '([^']*)'")}


def _run(*cmd, check=True) -> subprocess.CompletedProcess:
    r = subprocess.run(list(cmd), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise InstallError(f"{' '.join(cmd)} failed ({r.returncode}): {(r.stderr or r.stdout).strip()[:300]}")
    return r


def partitions(disk: str) -> dict:
    """partlabel -> (partition number, device path) after the kernel re-read the table."""
    _run("blockdev", "--rereadpt", disk, check=False)
    _run("udevadm", "settle", "--timeout=20", check=False)
    out = json.loads(_run("lsblk", "-J", "-o", "PATH,PARTLABEL,PARTN", disk).stdout)
    res = {}
    for dev in out.get("blockdevices", []):
        for c in _walk(dev):
            if c.get("partlabel") and c.get("partn"):
                res[c["partlabel"]] = (int(c["partn"]), c["path"])
    return res


def grow_data(disk: str) -> str:
    parts = partitions(disk)
    if "onemind-data" not in parts:
        raise InstallError("onemind-data partition not found on the written disk")
    n, dev = parts["onemind-data"]
    info = parse_sgdisk_info(_run("sgdisk", "-i", str(n), disk).stdout)
    if not info["guid"] or info["first"] < 0:
        raise InstallError("cannot read the onemind-data partition entry")
    _run("sgdisk", "-d", str(n), "-n", f"{n}:{info['first']}:0", "-t", f"{n}:{info['type']}",
         "-c", f"{n}:onemind-data", "-u", f"{n}:{info['guid']}", disk)
    dev = partitions(disk)["onemind-data"][1]
    fsck = _run("e2fsck", "-fy", dev, check=False)
    if fsck.returncode not in (0, 1):
        raise InstallError(f"e2fsck on onemind-data failed ({fsck.returncode})")
    _run("resize2fs", dev)
    return dev


def set_role(disk: str, conf: str) -> None:
    esp = partitions(disk).get("onemind-esp")
    if not esp:
        raise InstallError("onemind-esp partition not found on the written disk")
    tmp = os.path.join(RUN_DIR, "onemind.conf")
    os.makedirs(RUN_DIR, mode=0o700, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(conf)
    _run("mcopy", "-o", "-i", esp[1], tmp, "::/onemind.conf")
    back = _run("mtype", "-i", esp[1], "::/onemind.conf").stdout
    os.unlink(tmp)
    if back.replace("\r\n", "\n") != conf:
        raise InstallError("onemind.conf read back from the ESP differs from what was written")


def set_next_boot(disk: str) -> str:
    """Point the firmware at the installed disk (stick left in or not). Best effort."""
    if not os.path.isdir("/sys/firmware/efi/efivars"):
        return "no EFI variables (legacy boot): remove the stick before the reboot"
    lst = _run("efibootmgr", check=False).stdout
    for num in re.findall(r"^Boot([0-9A-Fa-f]{4})\*? OneMind\b", lst, re.M):
        _run("efibootmgr", "-q", "-b", num, "-B", check=False)
    r = _run("efibootmgr", "-c", "-d", disk, "-p", "1", "-L", "OneMind", "-l", "\\EFI\\BOOT\\BOOTX64.EFI", check=False)
    m = re.findall(r"^Boot([0-9A-Fa-f]{4})\*? OneMind\b", r.stdout, re.M)
    if r.returncode != 0 or not m:
        return "could not add a firmware boot entry: remove the stick before the reboot"
    _run("efibootmgr", "-q", "-n", m[-1], check=False)
    return f"firmware boot entry Boot{m[-1]} set as next boot"


class Progress:
    def __init__(self, sink=say, step=5):
        self.sink, self.step, self.last = sink, step, {}

    def __call__(self, what, done, total):
        pct = int(done * 100 / total) if total else 100
        if pct >= self.last.get(what, -self.step) + self.step or done == total:
            self.last[what] = pct
            self.sink(f"{what} {pct}%")


def install(disk: str, settings: dict | None, payload: dict, progress=None, open_stream=None) -> dict:
    """The whole install onto the block device `disk`. Caller holds the lock and has confirmed."""
    progress = progress or Progress()
    t0 = time.time()
    say(f"install start target={disk} role={settings['role'] if settings else 'setup'} image={payload['image']}")
    got = sha256_file(payload["path"], progress)
    if got != payload["file_sha256"]:
        raise InstallError(f"the installer's copy of the image is damaged (sha256 {got}); rebuild the stick")
    say(f"payload verified sha256={got}")
    fd = os.open(disk, os.O_RDWR | os.O_EXCL | getattr(os, "O_CLOEXEC", 0))
    try:
        if dev_size(fd) < payload["image_size"]:
            raise InstallError(f"{disk} is smaller than the image ({human(payload['image_size'])})")
        if open_stream:
            stream, proc = open_stream(payload["path"]), None
        else:
            proc = subprocess.Popen(["zstd", "-dc", "-q", payload["path"]], stdout=subprocess.PIPE)
            stream = proc.stdout
        try:
            write_image(stream, fd, payload["image_size"], payload["image_sha256"], progress)
        finally:
            if proc:
                proc.stdout.close()
                if proc.wait() != 0:
                    raise InstallError(f"zstd failed ({proc.returncode})")
        say(f"written bytes={payload['image_size']}; reading the disk back")
        back = read_back(fd, payload["image_size"], progress)
        if back != payload["image_sha256"]:
            raise InstallError(f"read-back sha256 {back} != image sha256 {payload['image_sha256']}: the disk did not store the image")
        say(f"verified sha256={back} bytes={payload['image_size']}")
    finally:
        os.close(fd)
    _run("sgdisk", "-e", disk)            # backup GPT header to the real end of this disk
    try:
        dev = grow_data(disk)
        say(f"onemind-data grown to the end of the disk ({dev})")
    except InstallError as exc:            # the image still works at its own size
        say(f"WARNING: onemind-data not grown ({exc})")
    if settings:
        set_role(disk, render_conf(settings))
        say(f"first-boot role set: role={settings['role']} (onemind.conf on the ESP)")
    else:
        say("first-boot role left open: the setup wizard runs at http://onemind.local:8080/")
    say(set_next_boot(disk))
    os.sync()
    res = {"target": disk, "role": settings["role"] if settings else "setup", "sha256": back,
           "minutes": round((time.time() - t0) / 60, 1)}
    say(f"done target={disk} role={res['role']} in {res['minutes']} min")
    return res


class Lock:
    def __init__(self, path=LOCK):
        self.path, self.fd = path, None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            os.close(self.fd)
            self.fd = None
            return False


def reboot(delay=10) -> None:
    say(f"remove the USB stick now if you can; rebooting in {delay} s")
    time.sleep(delay)
    subprocess.run(["systemctl", "reboot"])


# ------------------------------------------------------------------ console menu
def lan_hint() -> str:
    ips = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)/", _run("ip", "-4", "-o", "addr", "show", "scope", "global", check=False).stdout)
    code = ""
    try:
        code = open(CODE_FILE).read().strip()
    except OSError:
        pass
    where = ", ".join(f"http://{ip}:8080/" for ip in ips) or "http://onemind-installer.local:8080/ (no network yet)"
    return f"LAN page: {where}" + (f"  one-time code: {code}" if code else "")


class PlainUI:
    def __init__(self, inp=input, out=print):
        self.inp, self.out = inp, out

    def ask(self, prompt, default=""):
        a = self.inp(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
        return a or default


def tui_once(ui, payload, scan=scan_disks, do_install=install, lock=None) -> dict | None:
    """One pass of the menu. Returns the install result, or None if nothing was written."""
    out = ui.out
    targets, skipped = scan(payload["image_size"])
    out("")
    out(f"OneMind installer: writes OneMind {payload['version']} ({payload['board']}) to a disk of this computer.")
    out(lan_hint())
    say(f"ready disks={len(targets)}")
    for i, d in enumerate(targets, 1):
        out(f"  [{i}] {describe(d)}")
    for d in skipped:
        out(f"   -  {describe(d)}  not offered: {d['reason']}")
    out("  [r] scan again   [p] power off")
    if not targets:
        out("No disk to install to. Attach one and press r.")
    a = ui.ask("Install OneMind on disk number").lower()
    if a == "p":
        subprocess.run(["systemctl", "poweroff"])
        return None
    if not a.isdigit() or not 1 <= int(a) <= len(targets):
        return None
    disk = targets[int(a) - 1]
    role = ui.ask("Role: hub, worker, leaf, or setup (choose later in the browser)", "hub").lower()
    try:
        if role in ("worker", "leaf"):
            settings = make_settings(role, hub=ui.ask("Hub address"), join_token=ui.ask("Join token (printed on the hub's console)"))
        elif role == "hub":
            settings = make_settings(role, name=ui.ask("Name shown in the dashboard", "OneMind"))
        else:
            settings = make_settings(role)
    except InstallError as exc:
        out(f"Not installed: {exc}")
        return None
    out("")
    out("!" * 72)
    out(f"  ALL DATA ON {describe(disk)}")
    out("  WILL BE ERASED. This cannot be undone.")
    out("!" * 72)
    if ui.ask(f"Type {CONFIRM_WORD} to erase this disk and install OneMind").strip() != CONFIRM_WORD:
        say("not confirmed; nothing was written")
        return None
    lock = lock or Lock()
    if not lock.acquire():
        say("another install is already running (console or LAN page); nothing was written")
        return None
    try:
        return do_install(disk["path"], settings, payload)
    except InstallError as exc:
        say(f"FAILED: {exc}")
        out("The disk may be incomplete. Fix the cause and install again.")
        return None


def cmd_tui(a) -> int:
    payload = load_payload(a.payload)
    ui = PlainUI()
    while True:
        try:
            res = tui_once(ui, payload)
        except EOFError:
            time.sleep(5)
            continue
        if res:
            reboot()
            return 0


# ------------------------------------------------------------------ LAN page
class WebState:
    def __init__(self, code: str):
        self.code, self.failures, self.status, self.busy = code, 0, "idle", False
        self.mu = threading.Lock()

    def check(self, form: dict, targets: list) -> tuple[int, str, dict | None]:
        """-> (http status, message, accepted request). Refuses before anything is written."""
        with self.mu:
            if self.failures >= MAX_WEB_ATTEMPTS:
                return 403, "too many wrong codes: LAN installs are off until the installer restarts", None
            if not hmac.compare_digest(form.get("code", "").strip().encode(), self.code.encode()):
                self.failures += 1
                return 403, "wrong one-time code (it is shown on this computer's screen)", None
            if self.busy:
                return 409, "an install is already running", None
        if form.get("confirm", "").strip() != CONFIRM_WORD:
            return 400, f"type {CONFIRM_WORD} to confirm that the disk will be erased", None
        disk = next((d for d in targets if d["path"] == form.get("disk")), None)
        if not disk:
            return 400, "choose one of the listed disks", None
        try:
            s = make_settings(form.get("role", ""), form.get("name", ""), form.get("hub", ""), form.get("join_token", ""))
        except InstallError as exc:
            return 400, str(exc), None
        return 202, "install started", {"disk": disk, "settings": s}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OneMind installer</title><style>body{{font:16px system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem}}
.warn{{background:#fee;border:2px solid #c00;padding:.75rem}}label{{display:block;margin:.5rem 0}}</style></head><body>
<h1>OneMind installer</h1><p>Installs OneMind {version} ({board}) on a disk of this computer.</p>
<p><b>Status:</b> {status}</p>{body}</body></html>"""


def render_page(payload: dict, targets: list, skipped: list, status: str) -> str:
    e = html.escape
    rows = "".join(f'<label><input type="radio" name="disk" value="{e(d["path"])}"{" checked" if i == 0 else ""}> {e(describe(d))}</label>'
                   for i, d in enumerate(targets))
    rows += "".join(f"<p>Not offered: {e(describe(d))} ({e(d['reason'])})</p>" for d in skipped)
    body = ("<p>No disk to install to.</p>" if not targets else
            f'<form method="post" action="/install"><fieldset><legend>Disk</legend>{rows}</fieldset>'
            '<label>Role <select name="role"><option>hub</option><option>worker</option><option>leaf</option>'
            '<option value="setup">setup (choose at first boot)</option></select></label>'
            '<label>Name (hub) <input name="name" value="OneMind"></label>'
            '<label>Hub address (worker, leaf) <input name="hub"></label>'
            '<label>Join token (worker, leaf) <input name="join_token" autocomplete="off"></label>'
            '<label>One-time code (on this computer\'s screen) <input name="code" autocomplete="off" required></label>'
            f'<p class="warn">The chosen disk will be <b>erased</b>: every file on it is lost. '
            f'Type <b>{CONFIRM_WORD}</b> to confirm.</p><label><input name="confirm" autocomplete="off" required></label>'
            '<button type="submit">Erase the disk and install OneMind</button></form>')
    return PAGE.format(version=e(payload["version"]), board=e(payload["board"]), status=e(status), body=body)


def cmd_web(a) -> int:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    payload = load_payload(a.payload)
    code = f"{secrets.randbelow(10 ** 8):08d}"
    os.makedirs(RUN_DIR, mode=0o700, exist_ok=True)
    fd = os.open(CODE_FILE + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, (code + "\n").encode()); os.close(fd)
    os.replace(CODE_FILE + ".tmp", CODE_FILE)
    st = WebState(code)

    def run_install(req):
        lock = Lock()
        if not lock.acquire():
            with st.mu:
                st.busy, st.status = False, "another install is already running; nothing was written"
            return
        try:
            res = install(req["disk"]["path"], req["settings"], payload,
                          progress=Progress(lambda m: (say(m), setattr(st, "status", m))))
            st.status = f"done: {res['target']} role={res['role']} sha256 verified; rebooting"
            reboot()
        except InstallError as exc:
            st.status = f"FAILED: {exc}"
            say(st.status)
        finally:
            st.busy = False

    class H(BaseHTTPRequestHandler):
        def _send(self, code, text, ctype="text/html; charset=utf-8"):
            b = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == "/status":
                return self._send(200, json.dumps({"status": st.status, "busy": st.busy}), "application/json")
            if self.path != "/":
                return self._send(404, "not found", "text/plain")
            t, s = scan_disks(payload["image_size"])
            self._send(200, render_page(payload, t, s, st.status))

        def do_POST(self):
            if self.path != "/install":
                return self._send(404, "not found", "text/plain")
            n = min(int(self.headers.get("Content-Length") or 0), 8192)
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
            t, _ = scan_disks(payload["image_size"])
            code, msg, req = st.check(form, t)
            if req:
                with st.mu:
                    if st.busy:
                        code, msg, req = 409, "an install is already running", None
                    else:
                        st.busy, st.status = True, "starting"
            if req:
                threading.Thread(target=run_install, args=(req,), daemon=True).start()
            self._send(code, f"<!doctype html><title>OneMind installer</title><p>{html.escape(msg)}</p><p><a href=\"/\">back</a></p>")

        def log_message(self, fmt, *args):
            pass

    say(f"LAN page listening on :{a.port}")
    ThreadingHTTPServer(("", a.port), H).serve_forever()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--payload", default=PAYLOAD_DIR)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("tui").set_defaults(fn=cmd_tui)
    w = sp.add_parser("web"); w.add_argument("--port", type=int, default=8080); w.set_defaults(fn=cmd_web)
    sp.add_parser("list").set_defaults(fn=lambda a: print(json.dumps(scan_disks(load_payload(a.payload)["image_size"]), indent=1)) or 0)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
