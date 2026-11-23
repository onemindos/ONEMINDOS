# SPDX-License-Identifier: Apache-2.0
"""BACnet/IP adapter (FLD-03, #201): reads object properties, publishes them on NATS.

Written from the BACnet standard's public structure (ANSI/ASHRAE 135: Annex J BACnet/IP BVLL,
clause 6 NPDU, clause 20 APDU and tag encoding), no third-party code. Only the confirmed
ReadProperty service (choice 12) is ever sent; there is no code for WriteProperty.

Point address: OBJECT-TYPE:INSTANCE[:PROPERTY][*SCALE]
  OBJECT-TYPE analog-input, analog-output, analog-value, binary-input, binary-output,
              binary-value, multi-state-input, multi-state-output, multi-state-value
  PROPERTY    present-value (default) or a property number, e.g. 85
Example: FIELD_POINTS="zone1.temp_c=analog-input:1, fan.on=binary-value:3"
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

OBJECT_TYPES = {"analog-input": 0, "analog-output": 1, "analog-value": 2, "binary-input": 3,
                "binary-output": 4, "binary-value": 5, "multi-state-input": 13,
                "multi-state-output": 14, "multi-state-value": 19}
PROPERTIES = {"present-value": 85}
READ_PROPERTY = 12


@dataclass(frozen=True)
class Addr:
    obj_type: int
    instance: int
    prop: int
    scale: float | None


def parse_addr(text: str) -> Addr:
    body, _, scale = text.partition("*")
    parts = body.split(":")
    if len(parts) not in (2, 3) or parts[0] not in OBJECT_TYPES:
        raise ValueError(f"{text!r}: expected OBJECT-TYPE:INSTANCE[:PROPERTY], types {', '.join(OBJECT_TYPES)}")
    try:
        instance = int(parts[1])
        prop = 85 if len(parts) == 2 else PROPERTIES.get(parts[2]) or int(parts[2])
        factor = float(scale) if scale else None
    except ValueError:
        raise ValueError(f"{text!r}: instance, property and scale must be numbers") from None
    if not 0 <= instance < 0x3FFFFF or not 0 <= prop <= 0xFFFF:
        raise ValueError(f"{text!r}: instance or property out of range")
    return Addr(OBJECT_TYPES[parts[0]], instance, prop, factor)


class BacnetError(IOError):
    pass


def read_property_request(invoke_id: int, a: Addr) -> bytes:
    """BVLC Original-Unicast-NPDU + NPDU (expecting reply) + confirmed ReadProperty APDU."""
    prop = struct.pack(">B", a.prop) if a.prop < 256 else struct.pack(">H", a.prop)
    apdu = (bytes([0x00, 0x05, invoke_id, READ_PROPERTY])          # confirmed, max APDU 1476
            + b"\x0c" + struct.pack(">I", (a.obj_type << 22) | a.instance)   # [0] object id
            + bytes([0x18 | len(prop)]) + prop)                       # [1] property id
    npdu = b"\x01\x04" + apdu
    return b"\x81\x0a" + struct.pack(">H", len(npdu) + 4) + npdu


def _tag(data: bytes, i: int) -> tuple[int, bool, int, int]:
    """Decode one tag header at i -> (tag number, context?, length/value, index after header)."""
    b = data[i]
    num, ctx, lvt = b >> 4, bool(b & 0x08), b & 0x07
    i += 1
    if num == 15:
        num, i = data[i], i + 1
    if lvt == 5:                                   # extended length (6/7 are open/close tags)
        lvt, i = data[i], i + 1
        if lvt == 254:
            lvt, i = struct.unpack_from(">H", data, i)[0], i + 2
        elif lvt == 255:
            lvt, i = struct.unpack_from(">I", data, i)[0], i + 4
    return num, ctx, lvt, i


def decode_value(data: bytes, i: int):
    """One application-tagged primitive value (clause 20.2)."""
    num, ctx, length, i = _tag(data, i)
    if ctx:
        raise BacnetError("unexpected context tag in value")
    raw = data[i:i + length]
    if num == 1:                                   # boolean: value lives in the tag itself
        return bool(length)
    if num in (2, 9):                              # unsigned, enumerated
        return int.from_bytes(raw, "big")
    if num == 3:                                   # signed
        return int.from_bytes(raw, "big", signed=True)
    if num == 4:
        return struct.unpack(">f", raw)[0]
    if num == 5:
        return struct.unpack(">d", raw)[0]
    if num == 7 and raw:                           # character string, UTF-8 (charset 0)
        return raw[1:].decode("utf-8", errors="replace")
    raise BacnetError(f"unsupported value type (application tag {num})")


def parse_ack(packet: bytes, invoke_id: int):
    if len(packet) < 6 or packet[0] != 0x81:
        raise BacnetError("not a BACnet/IP packet")
    i = 4
    if packet[i] != 0x01:
        raise BacnetError("unsupported NPDU version")
    ctrl, i = packet[i + 1], i + 2
    if ctrl & 0x20:                                # destination present: DNET, DLEN, DADR, hop
        i += 3 + packet[i + 2] + 1
    if ctrl & 0x08:                                # source present: SNET, SLEN, SADR
        i += 3 + packet[i + 2]
    pdu = packet[i] >> 4
    if packet[i + 1] != invoke_id:
        raise BacnetError("reply for another request")
    if pdu == 5:
        raise BacnetError("device returned an error (class/code in the reply)")
    if pdu in (6, 7):
        raise BacnetError("device rejected or aborted the request")
    if pdu != 3 or packet[i + 2] != READ_PROPERTY:
        raise BacnetError("unexpected reply type")
    i += 3
    while i < len(packet):                         # skip [0] object id, [1] property, [2] index
        num, ctx, length, j = _tag(packet, i)
        if ctx and num == 3 and length == 6:       # opening tag [3]: the value follows
            return decode_value(packet, j)
        i = j + length
    raise BacnetError("no value in the reply")


class Client:
    def __init__(self, host: str, port: int = 47808, timeout: float = 3.0):
        self.target, self.timeout, self.invoke = (host, port), timeout, 0

    write = staticmethod(fieldbus.refuse_write)

    def read(self, a: Addr):
        self.invoke = (self.invoke + 1) & 0xFF
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(self.timeout)
            s.connect(self.target)
            s.send(read_property_request(self.invoke, a))
            try:
                value = parse_ack(s.recv(1500), self.invoke)
            except (OSError, IndexError, struct.error) as e:
                raise e if isinstance(e, BacnetError) else BacnetError(str(e) or "no reply") from None
        return fieldbus.scaled(value, a.scale) if isinstance(value, (int, float)) and not isinstance(
            value, bool) else value

    def read_points(self, points) -> dict:
        out = {}
        for p in points:
            try:
                out[f"{p.cls}.{p.metric}"] = self.read(p.addr)
            except BacnetError as e:
                out[f"{p.cls}.{p.metric}"] = e
        return out


def make_reader():
    host = os.environ.get("BACNET_HOST", "")
    if not host:
        raise ValueError("setting BACNET_HOST is empty")
    return Client(host, fieldbus.env_int("BACNET_PORT", 47808, 1, 65535)).read_points


if __name__ == "__main__":
    fieldbus.main("bacnet", parse_addr, make_reader)
