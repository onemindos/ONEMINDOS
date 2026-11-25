# SPDX-License-Identifier: Apache-2.0
"""Modbus TCP adapter (FLD-03, #201): reads registers and coils, publishes them on NATS.

Written from the public specifications, no third-party code: MODBUS Application Protocol
Specification V1.1b3 and MODBUS Messaging on TCP/IP Implementation Guide V1.0b (modbus.org).
Only the four read functions are ever sent: 1 read coils, 2 read discrete inputs, 3 read holding
registers, 4 read input registers. There is no code for the write functions (5, 6, 15, 16).

Point address: TABLE:ADDRESS[:TYPE][*SCALE]
  TABLE   hr (holding register), ir (input register), co (coil), di (discrete input)
  ADDRESS 0-based protocol address (register 40001 in a vendor manual is hr:0)
  TYPE    u16 (default), i16, u32, i32, f32 (big-endian words, the most common layout); bool for co/di
  SCALE   multiplier, e.g. *0.1
Example: FIELD_POINTS="power.watts=hr:0:u32*0.1, temp.celsius=ir:3:i16*0.1, pump.running=co:0"
"""
from __future__ import annotations

import os
import socket
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fieldbus  # noqa: E402

TABLES = {"co": 1, "di": 2, "hr": 3, "ir": 4}   # table -> read function code
TYPES = {"u16": (1, ">H"), "i16": (1, ">h"), "u32": (2, ">I"), "i32": (2, ">i"), "f32": (2, ">f")}
READ_FUNCTIONS = frozenset(TABLES.values())


@dataclass(frozen=True)
class Addr:
    fc: int
    address: int
    type: str
    scale: float | None


def parse_addr(text: str) -> Addr:
    body, _, scale = text.partition("*")
    parts = body.split(":")
    if len(parts) not in (2, 3) or parts[0] not in TABLES:
        raise ValueError(f"{text!r}: expected hr|ir|co|di:ADDRESS[:TYPE][*SCALE]")
    fc = TABLES[parts[0]]
    try:
        address = int(parts[1], 0)
        factor = float(scale) if scale else None
    except ValueError:
        raise ValueError(f"{text!r}: address and scale must be numbers") from None
    if not 0 <= address <= 0xFFFF:
        raise ValueError(f"{text!r}: address must be 0..65535")
    typ = parts[2] if len(parts) == 3 else ("bool" if fc in (1, 2) else "u16")
    if (fc in (1, 2)) != (typ == "bool") or (typ != "bool" and typ not in TYPES):
        raise ValueError(f"{text!r}: type {typ} does not fit table {parts[0]}")
    return Addr(fc, address, typ, factor)


class ModbusError(IOError):
    pass


class Client:
    """Modbus TCP client: one request at a time, reconnects after any error."""

    def __init__(self, host: str, port: int = 502, unit: int = 1, timeout: float = 3.0):
        self.host, self.port, self.unit, self.timeout = host, port, unit, timeout
        self.sock: socket.socket | None = None
        self.tid = 0

    write = staticmethod(fieldbus.refuse_write)

    def close(self) -> None:
        if self.sock:
            self.sock.close()
        self.sock = None

    def _recv(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ModbusError("connection closed by the device")
            buf += chunk
        return buf

    def request(self, fc: int, address: int, count: int) -> bytes:
        if fc not in READ_FUNCTIONS:
            fieldbus.refuse_write()
        try:
            if self.sock is None:
                self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self.tid = (self.tid + 1) & 0xFFFF
            pdu = struct.pack(">BHH", fc, address, count)
            self.sock.sendall(struct.pack(">HHHB", self.tid, 0, len(pdu) + 1, self.unit) + pdu)
            tid, proto, length, _unit = struct.unpack(">HHHB", self._recv(7))
            body = self._recv(length - 1)
            if tid != self.tid or proto != 0 or not body:
                raise ModbusError("reply does not match the request")
            if body[0] == fc | 0x80:
                raise ModbusError(f"device exception code {body[1] if len(body) > 1 else '?'}")
            if body[0] != fc or len(body) < 2 or len(body) - 2 != body[1]:
                raise ModbusError("malformed reply")
            return body[2:]
        except (OSError, struct.error) as e:
            self.close()
            raise e if isinstance(e, ModbusError) else ModbusError(str(e)) from None

    def read(self, a: Addr):
        if a.fc in (1, 2):
            return bool(self.request(a.fc, a.address, 1)[0] & 1)
        words, fmt = TYPES[a.type]
        data = self.request(a.fc, a.address, words)
        if len(data) != 2 * words:
            raise ModbusError("short reply")
        return fieldbus.scaled(struct.unpack(fmt, data)[0], a.scale)

    def read_points(self, points) -> dict:
        out = {}
        for p in points:
            try:
                out[f"{p.cls}.{p.metric}"] = self.read(p.addr)
            except ModbusError as e:
                out[f"{p.cls}.{p.metric}"] = e
        return out


def make_reader():
    host = os.environ.get("MODBUS_HOST", "")
    if not host:
        raise ValueError("setting MODBUS_HOST is empty")
    return Client(host, fieldbus.env_int("MODBUS_PORT", 502, 1, 65535),
                  fieldbus.env_int("MODBUS_UNIT", 1, 0, 255)).read_points


if __name__ == "__main__":
    fieldbus.main("modbus", parse_addr, make_reader)
