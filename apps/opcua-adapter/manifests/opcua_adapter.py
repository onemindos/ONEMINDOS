# SPDX-License-Identifier: Apache-2.0
"""OPC UA adapter (FLD-03, #201): reads node values over opc.tcp, publishes them on NATS.

Written from the public OPC UA specification (reference.opcfoundation.org): Part 6 (UA TCP
Hello/Acknowledge, secure conversation headers, binary encoding) and Part 4 (services), no
third-party code. It speaks SecurityPolicy None with an anonymous (empty) user token, and the
only data service it ever sends is Read (attribute 13, Value). There is no code for Write or Call.

Point address: NODEID[*SCALE] in the standard text form
  ns=2;i=1001   numeric identifier in namespace 2
  ns=3;s=Pump1.Speed   string identifier
  i=2258        namespace 0 (here: Server_ServerStatus_CurrentTime)
Example: FIELD_POINTS="line.speed_rpm=ns=2;s=Line1.Speed, tank.level_pct=ns=2;i=1001*0.1"
"""
from __future__ import annotations

import os
import re
import socket
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fieldbus  # noqa: E402

# Binary encoding ids of the service messages (Part 6, NodeIds.csv: <Type>_Encoding_DefaultBinary).
OPEN_REQ, OPEN_RESP = 446, 449
CLOSE_REQ = 452
CREATE_SESSION_REQ, CREATE_SESSION_RESP = 461, 464
ACTIVATE_SESSION_REQ, ACTIVATE_SESSION_RESP = 467, 470
READ_REQ, READ_RESP = 631, 634
SERVICE_FAULT = 397
POLICY_NONE = "http://opcfoundation.org/UA/SecurityPolicy#None"
ATTR_VALUE = 13
NODE_RE = re.compile(r"^(?:ns=(\d{1,5});)?(i|s)=(.+)$")


class UaError(IOError):
    pass


@dataclass(frozen=True)
class Addr:
    ns: int
    kind: str          # "i" numeric, "s" string
    ident: object
    scale: float | None


def parse_addr(text: str) -> Addr:
    body, star, scale = text.rpartition("*") if "*" in text else (text, "", "")  # last * = scale
    m = NODE_RE.match(body.strip())
    if not m:
        raise ValueError(f"{text!r}: expected ns=N;i=NUMBER or ns=N;s=NAME")
    ns, kind, ident = int(m.group(1) or 0), m.group(2), m.group(3)
    try:
        factor = float(scale) if star else None
        ident = int(ident) if kind == "i" else ident
    except ValueError:
        raise ValueError(f"{text!r}: identifier and scale must be numbers") from None
    if ns > 0xFFFF or (kind == "i" and not 0 <= ident <= 0xFFFFFFFF):
        raise ValueError(f"{text!r}: namespace or identifier out of range")
    return Addr(ns, kind, ident, factor)


# ---- binary encoding (Part 6 §5.2) ----

def u32(v: int) -> bytes:
    return struct.pack("<I", v)


def string(s: str | None) -> bytes:
    if s is None:
        return struct.pack("<i", -1)
    b = s.encode()
    return struct.pack("<i", len(b)) + b


def nodeid(ns: int, kind: str, ident) -> bytes:
    if kind == "s":
        return b"\x03" + struct.pack("<H", ns) + string(ident)
    if ns == 0 and ident < 256:
        return bytes([0, ident])
    if ns < 256 and ident < 65536:
        return bytes([1, ns]) + struct.pack("<H", ident)
    return b"\x02" + struct.pack("<HI", ns, ident)


NULL_NODE = b"\x00\x00"
NULL_EXT = NULL_NODE + b"\x00"              # ExtensionObject with no body


def request_header(token: bytes, handle: int) -> bytes:
    # authenticationToken, timestamp (0 = not given), requestHandle, returnDiagnostics,
    # auditEntryId, timeoutHint (ms), additionalHeader
    return token + struct.pack("<qII", 0, handle, 0) + string(None) + u32(10000) + NULL_EXT


class Reader:
    """Cursor over a received message body."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data, self.pos = data, pos

    def take(self, fmt: str):
        v = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += struct.calcsize(fmt)
        return v[0] if len(v) == 1 else v

    def bytestring(self) -> bytes | None:
        n = self.take("<i")
        if n < 0:
            return None
        if self.pos + n > len(self.data):
            raise UaError("truncated message")
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def string(self) -> str | None:
        b = self.bytestring()
        return None if b is None else b.decode("utf-8", errors="replace")

    def nodeid_raw(self) -> bytes:
        start, enc = self.pos, self.take("<B")
        kind = enc & 0x0F
        if kind == 0:
            self.pos += 1
        elif kind == 1:
            self.pos += 3
        elif kind == 2:
            self.pos += 6
        elif kind in (3, 5):
            self.pos += 2
            self.bytestring()
        elif kind == 4:
            self.pos += 18
        else:
            raise UaError("bad NodeId encoding")
        if enc & 0x80:
            self.string()
        if enc & 0x40:
            self.pos += 4
        return self.data[start:self.pos]

    def type_id(self) -> int:
        """The numeric id of an encoding NodeId (ns 0), -1 otherwise."""
        raw = self.nodeid_raw()
        if raw[0] == 0:
            return raw[1]
        if raw[0] == 1:
            return struct.unpack_from("<H", raw, 2)[0]
        return struct.unpack_from("<I", raw, 3)[0] if raw[0] == 2 else -1

    def extension_object(self) -> None:
        self.nodeid_raw()
        if self.take("<B") in (1, 2):
            self.bytestring()

    def diagnostic_info(self) -> None:
        mask = self.take("<B")
        self.pos += 4 * bin(mask & 0x0F).count("1")
        if mask & 0x10:
            self.string()
        if mask & 0x20:
            self.pos += 4
        if mask & 0x40:
            self.diagnostic_info()

    def response_header(self) -> int:
        """Skip a ResponseHeader, return its serviceResult."""
        self.pos += 8 + 4                        # timestamp, requestHandle
        result = self.take("<I")
        self.diagnostic_info()
        n = self.take("<i")
        for _ in range(max(n, 0)):
            self.string()
        self.extension_object()
        return result

    def variant(self):
        enc = self.take("<B")
        if enc & 0xC0:
            raise UaError("array values are not supported; point at a scalar node")
        t = enc & 0x3F
        fmts = {1: "<?", 2: "<b", 3: "<B", 4: "<h", 5: "<H", 6: "<i", 7: "<I", 8: "<q", 9: "<Q",
                10: "<f", 11: "<d"}
        if t in fmts:
            return self.take(fmts[t])
        if t == 12:
            return self.string()
        if t == 13:                              # DateTime: 100 ns ticks since 1601-01-01 UTC
            return round(self.take("<q") / 1e7 - 11644473600, 3)
        raise UaError(f"unsupported value type (built-in type {t})")

    def data_value(self):
        """-> (value or None, status code)."""
        mask, value, status = self.take("<B"), None, 0
        if mask & 0x01:
            value = self.variant()
        if mask & 0x02:
            status = self.take("<I")
        return value, status


class Client:
    """One opc.tcp connection: Hello, OpenSecureChannel (None), CreateSession, ActivateSession."""

    def __init__(self, url: str, timeout: float = 5.0):
        u = urlsplit(url)
        if u.scheme != "opc.tcp" or not u.hostname:
            raise ValueError("OPCUA_URL must look like opc.tcp://host:4840[/path]")
        self.url, self.addr, self.timeout = url, (u.hostname, u.port or 4840), timeout
        self.sock: socket.socket | None = None
        self.channel = self.token_id = self.seq = self.req = 0
        self.auth = NULL_NODE

    write = staticmethod(fieldbus.refuse_write)

    def close(self) -> None:
        if self.sock:
            try:
                self._send(b"CLOF", nodeid(0, "i", CLOSE_REQ) + request_header(self.auth, self.req))
            except OSError:
                pass
            self.sock.close()
        self.sock = None

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise UaError("connection closed by the server")
            buf += chunk
        return buf

    def _recv_msg(self) -> tuple[bytes, bytes]:
        head = self._recv_exact(8)
        kind, size = head[:4], struct.unpack_from("<I", head, 4)[0]
        if not 8 <= size <= 1 << 24:
            raise UaError("bad message size")
        body = self._recv_exact(size - 8)
        if kind == b"ERRF":
            r = Reader(body)
            code = r.take("<I")
            raise UaError(f"server error 0x{code:08X}: {r.string() or ''}")
        if kind[3:4] != b"F":
            raise UaError("chunked replies are not supported")
        return kind, body

    def _send(self, kind: bytes, body: bytes) -> None:
        self.seq += 1
        self.req += 1
        if kind == b"OPNF":
            hdr = u32(0) + string(POLICY_NONE) + string(None) + string(None)
        else:
            hdr = u32(self.channel) + u32(self.token_id)
        msg = hdr + u32(self.seq) + u32(self.req) + body
        self.sock.sendall(kind + u32(len(msg) + 8) + msg)

    def _call(self, kind: bytes, type_id: int, body: bytes, expect: int) -> Reader:
        self._send(kind, nodeid(0, "i", type_id) + request_header(self.auth, self.req + 1) + body)
        rkind, data = self._recv_msg()
        r = Reader(data)
        if rkind == b"OPNF":
            r.take("<I")
            r.string(), r.bytestring(), r.bytestring()
        else:
            r.pos += 8                            # channel id, token id
        r.pos += 8                                # sequence number, request id
        got = r.type_id()
        result = r.response_header()
        if got == SERVICE_FAULT or result & 0x80000000:
            raise UaError(f"service failed with status 0x{result:08X}")
        if got != expect:
            raise UaError(f"unexpected reply type {got}")
        return r

    def connect(self) -> None:
        self.sock = socket.create_connection(self.addr, timeout=self.timeout)
        self.channel = self.token_id = self.seq = self.req = 0
        self.auth = NULL_NODE
        hello = u32(0) + u32(65536) + u32(65536) + u32(1 << 24) + u32(1) + string(self.url)
        self.sock.sendall(b"HELF" + u32(len(hello) + 8) + hello)
        if self._recv_msg()[0] != b"ACKF":
            raise UaError("no Acknowledge from the server")
        # OpenSecureChannel: protocol 0, Issue (0), SecurityMode None (1), no nonce, 1 h lifetime.
        r = self._call(b"OPNF", OPEN_REQ, u32(0) + u32(0) + u32(1) + string("") + u32(3600000), OPEN_RESP)
        r.pos += 4                                # server protocol version
        self.channel, self.token_id = r.take("<I"), r.take("<I")
        # CreateSession: ApplicationDescription of this client, then endpoint and session settings.
        app = (string("urn:onemind:opcua-adapter") + string("urn:onemind") + b"\x02"
               + string("OneMind OPC UA adapter") + u32(1) + string(None) + string(None)
               + struct.pack("<i", -1))
        body = (app + string(None) + string(self.url) + string("onemind-opcua-adapter")
                + string(None) + string(None) + struct.pack("<d", 600000.0) + u32(1 << 24))
        r = self._call(b"MSGF", CREATE_SESSION_REQ, body, CREATE_SESSION_RESP)
        r.nodeid_raw()                            # sessionId
        self.auth = r.nodeid_raw()                # authenticationToken
        # ActivateSession: no signature, no software certificates, no locales, and an empty user
        # identity token, which Part 4 (ActivateSession) treats as anonymous.
        empty_sig = string(None) + string(None)
        body = empty_sig + struct.pack("<ii", -1, -1) + NULL_EXT + empty_sig
        self._call(b"MSGF", ACTIVATE_SESSION_REQ, body, ACTIVATE_SESSION_RESP)

    def read_values(self, addrs: list[Addr]) -> list:
        nodes = b"".join(nodeid(a.ns, a.kind, a.ident) + u32(ATTR_VALUE) + string(None)
                         + struct.pack("<H", 0) + string(None) for a in addrs)
        # maxAge 0 (read from the device), timestampsToReturn Neither (3)
        body = struct.pack("<dI", 0.0, 3) + struct.pack("<i", len(addrs)) + nodes
        r = self._call(b"MSGF", READ_REQ, body, READ_RESP)
        n = r.take("<i")
        if n != len(addrs):
            raise UaError("reply has the wrong number of results")
        out = []
        for a in addrs:
            value, status = r.data_value()
            if status & 0x80000000:
                out.append(UaError(f"bad status 0x{status:08X}"))
            elif value is None:
                out.append(UaError("no value"))
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(fieldbus.scaled(value, a.scale))
            else:
                out.append(value)
        return out

    def read_points(self, points) -> dict:
        try:
            if self.sock is None:
                self.connect()
            values = self.read_values([p.addr for p in points])
        except (OSError, struct.error, UnicodeError) as e:
            self.close()
            raise e if isinstance(e, UaError) else UaError(str(e) or type(e).__name__) from None
        return {f"{p.cls}.{p.metric}": v for p, v in zip(points, values)}


def make_reader():
    url = os.environ.get("OPCUA_URL", "")
    if not url:
        raise ValueError("setting OPCUA_URL is empty")
    return Client(url).read_points


if __name__ == "__main__":
    fieldbus.main("opcua", parse_addr, make_reader)
