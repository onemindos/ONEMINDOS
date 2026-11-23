# SPDX-License-Identifier: Apache-2.0
"""CAN adapter (FLD-03, #201): listens to CAN frames through socketcand, publishes signals on NATS.

Why socketcand and not SocketCAN directly: a SocketCAN interface (can0) lives in the host's network
namespace, and an app pod may not use hostNetwork or host devices (the app gate refuses both). So
the adapter reaches the bus over TCP through socketcand, the Linux-CAN project's CAN-over-TCP
server, running next to the CAN interface (on the host or on a small CAN gateway box).

Written from socketcand's public protocol description (github.com/linux-can/socketcand,
doc/protocol.md), no third-party code: the server greets with `< hi >`, the adapter sends
`< open BUS >` and `< rawmode >`, and the server then streams `< frame ID SECONDS.USECONDS DATA >`
with DATA as upper-case hex, no spaces. CAN is a broadcast bus, so listening never changes it.
The adapter never sends `< send ... >`: there is no code for it.

Point address: ID:BYTE[:TYPE][*SCALE]
  ID     CAN identifier in hex, e.g. 1A0 (11-bit) or 18FEF100 (29-bit)
  BYTE   offset of the signal's first byte in the frame (0-7)
  TYPE   u8 (default), i8, u16, i16, u32, i32, f32: little-endian (Intel); add "be" for big-endian
         (Motorola), e.g. u16be. Signals that are not whole bytes are not supported yet.
Example: FIELD_POINTS="engine.rpm=0CF00400:3:u16*0.125, coolant.celsius=18FEEE00:0:u8"
"""
from __future__ import annotations

import os
import re
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fieldbus  # noqa: E402

TYPES = {"u8": "B", "i8": "b", "u16": "H", "i16": "h", "u32": "I", "i32": "i", "f32": "f"}
BUS_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")
FRAME_RE = re.compile(r"^< frame ([0-9A-Fa-f]{1,8}) (\d+\.\d+) ?([0-9A-Fa-f]*) >$")


class CanError(IOError):
    pass


@dataclass(frozen=True)
class Addr:
    can_id: int
    offset: int
    fmt: str
    scale: float | None


def parse_addr(text: str) -> Addr:
    body, _, scale = text.partition("*")
    parts = body.split(":")
    typ = parts[2] if len(parts) == 3 else "u8"
    order = ">" if typ.endswith("be") else "<"
    base = typ[:-2] if typ.endswith("be") else typ
    if len(parts) not in (2, 3) or base not in TYPES:
        raise ValueError(f"{text!r}: expected HEXID:BYTE[:TYPE][*SCALE], types {', '.join(TYPES)} (+be)")
    try:
        can_id, offset = int(parts[0], 16), int(parts[1])
        factor = float(scale) if scale else None
    except ValueError:
        raise ValueError(f"{text!r}: ID is hex, BYTE and scale are numbers") from None
    fmt = order + TYPES[base]
    if not 0 <= can_id <= 0x1FFFFFFF or not 0 <= offset or offset + struct.calcsize(fmt) > 8:
        raise ValueError(f"{text!r}: ID or byte range does not fit a CAN frame")
    return Addr(can_id, offset, fmt, factor)


class Listener:
    """Keeps the latest frame per CAN id, read from a socketcand server in raw mode."""

    def __init__(self, host: str, port: int = 29536, bus: str = "can0", stale_s: float = 30.0):
        if not BUS_RE.match(bus):
            raise ValueError("CAN_BUS must be an interface name such as can0")
        self.target, self.bus, self.stale_s = (host, port), bus, stale_s
        self.frames: dict[int, tuple[float, bytes]] = {}
        self.error = "not connected yet"
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    write = staticmethod(fieldbus.refuse_write)

    @staticmethod
    def _messages(s: socket.socket):
        """Yield each "< ... >" message; socketcand does not end them with a newline."""
        buf = b""
        while True:
            while b">" in buf:
                msg, buf = buf.split(b">", 1)
                yield (msg + b">").decode(errors="replace").strip()
            chunk = s.recv(4096)
            if not chunk:
                raise CanError("socketcand closed the connection")
            if len(buf) > 65536:
                raise CanError("socketcand sent an over-long message")
            buf += chunk

    def _session(self) -> None:
        with socket.create_connection(self.target, timeout=10) as s:
            msgs = self._messages(s)
            for send, want in ((None, "< hi >"), (f"< open {self.bus} >", "< ok >"), ("< rawmode >", "< ok >")):
                if send:
                    s.sendall(send.encode())
                got = next(msgs)
                if got != want:
                    raise CanError(f"socketcand said {got!r}, expected {want!r}")
            s.settimeout(max(self.stale_s, 5))
            self.error = ""
            for msg in msgs:
                self.handle(msg)

    def handle(self, msg: str) -> None:
        m = FRAME_RE.match(msg)
        if not m:
            if msg.startswith("< error"):
                self.error = msg
            return
        data = bytes.fromhex(m.group(3)) if len(m.group(3)) % 2 == 0 else b""
        with self.lock:
            self.frames[int(m.group(1), 16)] = (time.monotonic(), data[:8])

    def _run(self) -> None:
        while True:
            try:
                self._session()
            except (OSError, CanError, ValueError) as e:
                self.error = f"socketcand {self.target[0]}:{self.target[1]}: {e}"
            time.sleep(5)

    def start(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def value(self, a: Addr):
        with self.lock:
            seen = self.frames.get(a.can_id)
        if seen is None or time.monotonic() - seen[0] > self.stale_s:
            raise CanError(f"no frame with id {a.can_id:X} in the last {self.stale_s:g} s"
                           + (f" ({self.error})" if self.error else ""))
        data = seen[1]
        if a.offset + struct.calcsize(a.fmt) > len(data):
            raise CanError(f"frame {a.can_id:X} has only {len(data)} bytes")
        return fieldbus.scaled(struct.unpack_from(a.fmt, data, a.offset)[0], a.scale)

    def read_points(self, points) -> dict:
        self.start()
        out = {}
        for p in points:
            try:
                out[f"{p.cls}.{p.metric}"] = self.value(p.addr)
            except CanError as e:
                out[f"{p.cls}.{p.metric}"] = e
        return out


def make_reader():
    host = os.environ.get("CAN_HOST", "")
    if not host:
        raise ValueError("setting CAN_HOST is empty")
    return Listener(host, fieldbus.env_int("CAN_PORT", 29536, 1, 65535),
                    os.environ.get("CAN_BUS", "") or "can0").read_points


if __name__ == "__main__":
    fieldbus.main("can", parse_addr, make_reader)
