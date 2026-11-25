# SPDX-License-Identifier: Apache-2.0
"""Shared part of OneMind's field protocol adapters (FLD-03, #201). Identical copy in every
apps/<proto>-adapter/manifests/ (kustomize only packs files inside the app's own directory);
test/unit/test_field_adapters.py fails when the copies differ.

What it does, in plain words: read points from a field device (the protocol module supplies
`read()`), publish each value on NATS as telemetry, and show the latest values on a small
read-only web page. It never writes to the device (observe-first): `refuse_write()` is the only
write path, and it always refuses.

Subjects follow the locked grammar (research-output/fabric/06-DATA-AND-NAMING.md):
`tel.<node_id>-<device_id>.<class>.<metric>`. Commands (`cmd.<domain>.<node>-<device>.<action>`)
are published only by the gateway after an owner approves the action; the gateway does not publish
them yet, so these adapters do not subscribe to `cmd.` at all.

Python standard library only, so it runs on the stock python image with nothing installed.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

TOKEN_RE = re.compile(r"^[a-z0-9_]{1,40}$")
WRITE_REFUSAL = ("writes are refused: this adapter is observe-only. A write must be an owner-approved "
                 "gateway action published by the gateway as cmd.<domain>.<node>-<device>.<action>; "
                 "that path is not built yet, so nothing is written to the device")


class WriteRefused(PermissionError):
    pass


def refuse_write(*_args, **_kwargs):
    """The only write path. AI never actuates without human approval (D-B9): always refuses."""
    raise WriteRefused(WRITE_REFUSAL)


@dataclass(frozen=True)
class Point:
    cls: str      # telemetry class, e.g. power
    metric: str   # metric name, e.g. watts
    addr: object  # protocol address, parsed by the protocol module
    raw: str      # the address as the owner wrote it


def parse_points(spec: str, parse_addr) -> list[Point]:
    """'class.metric=ADDRESS, ...' -> points. Raises ValueError naming the bad entry."""
    points, seen = [], set()
    for item in (spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        name, sep, addr = item.partition("=")
        cls, dot, metric = name.strip().partition(".")
        if not (sep and dot and TOKEN_RE.match(cls) and TOKEN_RE.match(metric)):
            raise ValueError(f"point {item!r}: expected class.metric=ADDRESS (lower-case a-z, 0-9, _)")
        if (cls, metric) in seen:
            raise ValueError(f"point {cls}.{metric} is listed twice")
        seen.add((cls, metric))
        try:
            points.append(Point(cls, metric, parse_addr(addr.strip()), addr.strip()))
        except ValueError as e:
            raise ValueError(f"point {cls}.{metric}: {e}") from None
    return points


def scaled(value, scale: float | None):
    return value if scale is None else round(value * scale, 6)


def subject(node: str, device: str, p: Point) -> str:
    return f"tel.{node}-{device}.{p.cls}.{p.metric}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Nats:
    """Minimal NATS publisher (client protocol: https://docs.nats.io/reference/reference-protocols/nats-protocol).

    CONNECT, then PUB; a reader thread answers the server's PING with PONG. Empty URL: publishing
    is off and values show on the page only. The URL comes from app settings, a plain ConfigMap
    (not secret), so a user or password in it is refused instead of being stored there.
    """

    def __init__(self, url: str, name: str):
        self.url, self.name = url, name
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()
        self.error = "" if url else "NATS_URL not set: values are shown on this page only"

    def _connect(self) -> None:
        u = urlsplit(self.url)
        if u.scheme != "nats" or not u.hostname:
            raise ValueError("NATS_URL must look like nats://host:4222")
        if u.username or u.password:
            raise ValueError("NATS_URL must not carry a user or password (settings are not secret)")
        s = socket.create_connection((u.hostname, u.port or 4222), timeout=5)
        f = s.makefile("rb")
        if not f.readline().startswith(b"INFO "):
            s.close()
            raise ConnectionError("not a NATS server")
        opts = {"verbose": False, "pedantic": False, "name": self.name, "lang": "python-stdlib",
                "version": "0.1.0", "protocol": 0}
        s.sendall(b"CONNECT " + json.dumps(opts).encode() + b"\r\nPING\r\n")
        s.settimeout(None)
        threading.Thread(target=self._reader, args=(s, f), daemon=True).start()
        self.sock = s

    def _reader(self, s: socket.socket, f) -> None:
        try:
            for line in f:
                if line.startswith(b"PING"):
                    with self.lock:
                        s.sendall(b"PONG\r\n")
                elif line.startswith(b"-ERR"):
                    self.error = line.decode(errors="replace").strip()
        except OSError:
            pass
        with self.lock:
            if self.sock is s:
                self.sock = None

    def publish(self, subj: str, payload: bytes) -> bool:
        if not self.url:
            return False
        with self.lock:
            try:
                if self.sock is None:
                    self._connect()
                self.sock.sendall(b"PUB %s %d\r\n%s\r\n" % (subj.encode(), len(payload), payload))
                return True
            except (OSError, ValueError, ConnectionError) as e:
                self.error = f"NATS: {e}"
                if self.sock:
                    self.sock.close()
                self.sock = None
                return False


class State:
    def __init__(self, protocol: str, points: list[Point], config_error: str = ""):
        self.protocol, self.points = protocol, points
        self.values: dict[str, dict] = {}
        self.error = config_error
        self.lock = threading.Lock()

    def snapshot(self) -> dict:
        with self.lock:
            return {"protocol": self.protocol, "mode": "observe-only", "writes": WRITE_REFUSAL,
                    "error": self.error, "points": dict(self.values)}


def poll_once(state: State, read, nats: Nats, node: str, device: str) -> None:
    """One cycle: read every point, publish the good ones. A failed read marks the point bad."""
    try:
        results = read(state.points)
        state.error = ""
    except Exception as e:  # noqa: BLE001 - any device or network error is shown, never fatal
        results, state.error = {}, f"{type(e).__name__}: {e}"
    ts = now_iso()
    for p in state.points:
        key = f"{p.cls}.{p.metric}"
        r = results.get(key)
        if isinstance(r, Exception) or r is None:
            rec = {"quality": "bad", "ts": ts, "point": p.raw,
                   "error": str(r) if r is not None else state.error or "no value"}
        else:
            rec = {"value": r, "quality": "good", "ts": ts, "point": p.raw}
            nats.publish(subject(node, device, p), json.dumps(rec, separators=(",", ":")).encode())
        with state.lock:
            state.values[key] = rec
    if nats.url and nats.error:
        state.error = (state.error + "; " if state.error else "") + nats.error


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        server_version = "onemind-field"

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body, indent=1).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, {"ok": True})
            if self.path in ("/", "/api/points"):
                return self._send(200, state.snapshot())
            self._send(404, {"error": "not found"})

        def do_POST(self):
            self._send(405, {"error": WRITE_REFUSAL})

        do_PUT = do_PATCH = do_DELETE = do_POST

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    return Handler


def env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.environ.get(name, "") or default)))
    except ValueError:
        return default


def main(protocol: str, parse_addr, make_reader) -> None:
    """Entry point: settings come from the environment (the gateway's onemind-settings ConfigMap)."""
    node = os.environ.get("FIELD_NODE", "") or "box"
    device = os.environ.get("FIELD_DEVICE", "") or protocol
    err = ""
    if not (TOKEN_RE.match(node) and TOKEN_RE.match(device)):
        err, node, device = "FIELD_NODE and FIELD_DEVICE must be lower-case a-z, 0-9, _", "box", protocol
    try:
        points = parse_points(os.environ.get("FIELD_POINTS", ""), parse_addr)
    except ValueError as e:
        points, err = [], str(e)
    state = State(protocol, points, err or ("" if points else "no points configured (setting FIELD_POINTS)"))
    port = env_int("PORT", 8080, 1, 65535)
    http = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    print(f"{protocol} adapter: {len(points)} point(s), status page on :{port}", flush=True)
    nats = Nats(os.environ.get("NATS_URL", ""), f"onemind-{protocol}-adapter")
    interval = env_int("FIELD_POLL_S", 5, 1, 3600)
    reader = None
    while True:
        if points and not err:
            try:
                reader = reader or make_reader()
                poll_once(state, reader, nats, node, device)
            except Exception as e:  # noqa: BLE001 - bad settings show on the page
                state.error = f"{type(e).__name__}: {e}"
        time.sleep(interval)
