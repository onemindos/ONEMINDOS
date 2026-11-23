# SPDX-License-Identifier: Apache-2.0
"""FLD-03 (#201): the field protocol adapters in apps/{modbus,bacnet,opcua,can}-adapter, each against
an in-process simulator of its protocol (Modbus TCP server, BACnet/IP device, OPC UA server,
socketcand server) and a fake NATS server. The simulators also record what the adapter sent, so the
tests prove it only ever reads: no Modbus write function, no BACnet WriteProperty, no OPC UA Write
or Call, no socketcand `send`.

Run: python3 -I -m unittest test/unit/test_field_adapters.py -v
"""
import importlib.util, json, os, socketserver, struct, sys, threading, time, unittest
import urllib.error, urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROTOCOLS = ("modbus", "bacnet", "opcua", "can")


def load(proto):
    path = os.path.join(ROOT, "apps", f"{proto}-adapter", "manifests", f"{proto}_adapter.py")
    spec = importlib.util.spec_from_file_location(f"{proto}_adapter", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


mb, bn, ua, cn = (load(p) for p in PROTOCOLS)
fb = mb.fieldbus


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = daemon_threads = True


def serve(handler):
    srv = Server(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError
        buf += chunk
    return buf


def points(spec, mod):
    return fb.parse_points(spec, mod.parse_addr)


def readings(read, spec, mod):
    return {k: (str(v) if isinstance(v, Exception) else v) for k, v in read(points(spec, mod)).items()}


class Shared(unittest.TestCase):
    def test_every_app_carries_the_same_fieldbus(self):
        copies = {}
        for p in PROTOCOLS:
            with open(os.path.join(ROOT, "apps", f"{p}-adapter", "manifests", "fieldbus.py"), "rb") as f:
                copies[p] = f.read()
        self.assertEqual(len(set(copies.values())), 1, "fieldbus.py copies differ: " + ", ".join(copies))

    def test_points_are_validated(self):
        with self.assertRaisesRegex(ValueError, "twice"):
            points("a.b=hr:0, a.b=hr:1", mb)
        with self.assertRaisesRegex(ValueError, "class.metric"):
            points("Bad.Name=hr:0", mb)
        with self.assertRaisesRegex(ValueError, "does not fit"):
            points("a.b=co:0:u16", mb)
        with self.assertRaisesRegex(ValueError, "fit a CAN frame"):
            points("a.b=1A0:7:u16", cn)
        with self.assertRaisesRegex(ValueError, "ns=N"):
            points("a.b=nonsense", ua)
        with self.assertRaisesRegex(ValueError, "OBJECT-TYPE"):
            points("a.b=device:1", bn)

    def test_writes_are_always_refused(self):
        for client in (mb.Client("127.0.0.1"), bn.Client("127.0.0.1"), ua.Client("opc.tcp://127.0.0.1"),
                       cn.Listener("127.0.0.1")):
            with self.assertRaisesRegex(fb.WriteRefused, "observe-only"):
                client.write("anything", 1)
        with self.assertRaises(fb.WriteRefused):
            mb.Client("127.0.0.1").request(6, 0, 1)      # 6 = write single register: refused before sending

    def test_status_page_is_read_only(self):
        state = fb.State("modbus", points("power.watts=hr:0", mb))
        http = ThreadingHTTPServer(("127.0.0.1", 0), fb.make_handler(state))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{http.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/api/points", timeout=5) as r:
                self.assertEqual(json.load(r)["mode"], "observe-only")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(base + "/api/points", data=b"{}", method="POST"), timeout=5)
            self.assertEqual(e.exception.code, 405)
        finally:
            http.shutdown(), http.server_close()

    def test_nats_url_with_credentials_is_refused(self):
        nats = fb.Nats("nats://user:pw@127.0.0.1:4222", "t")
        self.assertFalse(nats.publish("tel.x-y.a.b", b"{}"))
        self.assertIn("not carry a user or password", nats.error)


class FakeNats(socketserver.BaseRequestHandler):
    published = []

    def handle(self):
        self.request.sendall(b'INFO {"server_id":"fake"}\r\n')
        f = self.request.makefile("rb")
        for line in f:
            if line.startswith(b"PUB "):
                _, subj, size = line.split()
                FakeNats.published.append((subj.decode(), json.loads(f.read(int(size)))))
                f.read(2)
            elif line.startswith(b"PING"):
                self.request.sendall(b"PONG\r\n")


# ---- Modbus TCP simulator ----
class ModbusSim(socketserver.BaseRequestHandler):
    tables = {3: {0: 0x0001, 1: 0x86A0, 5: 0x4148, 6: 0x0000}, 4: {3: (-55) & 0xFFFF}, 1: {0: 1}, 2: {}}
    functions = []

    def handle(self):
        try:
            while True:
                tid, proto, length, unit = struct.unpack(">HHHB", recv_exact(self.request, 7))
                fc, addr, count = struct.unpack(">BHH", recv_exact(self.request, length - 1))
                ModbusSim.functions.append(fc)
                table = self.tables.get(fc)
                if table is None or any(a not in table for a in range(addr, addr + count)):
                    pdu = bytes([fc | 0x80, 2 if table is not None else 1])   # illegal address/function
                elif fc in (1, 2):
                    pdu = bytes([fc, 1, table[addr] & 1])
                else:
                    data = b"".join(struct.pack(">H", table[a]) for a in range(addr, addr + count))
                    pdu = bytes([fc, len(data)]) + data
                self.request.sendall(struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit) + pdu)
        except ConnectionError:
            pass


class Modbus(unittest.TestCase):
    def test_reads_and_publishes_against_the_simulator(self):
        sim, nats = serve(ModbusSim), serve(FakeNats)
        FakeNats.published.clear()
        try:
            client = mb.Client("127.0.0.1", sim.server_address[1])
            spec = ("power.watts=hr:0:u32*0.1, temp.celsius=ir:3:i16*0.1, pump.running=co:0, "
                    "flow.lpm=hr:5:f32, missing.value=hr:100")
            got = readings(client.read_points, spec, mb)
            self.assertEqual(got["power.watts"], 10000.0)
            self.assertEqual(got["temp.celsius"], -5.5)
            self.assertIs(got["pump.running"], True)
            self.assertEqual(got["flow.lpm"], 12.5)
            self.assertIn("exception code 2", got["missing.value"])
            # one poll cycle publishes the good values on the locked subject grammar
            state = fb.State("modbus", points(spec, mb))
            fb.poll_once(state, client.read_points, fb.Nats(f"nats://127.0.0.1:{nats.server_address[1]}", "t"),
                         "box", "plc1")
            for _ in range(50):
                if len(FakeNats.published) >= 4:
                    break
                time.sleep(0.05)
            subjects = {s: p for s, p in FakeNats.published}
            self.assertEqual(subjects["tel.box-plc1.power.watts"]["value"], 10000.0)
            self.assertEqual(subjects["tel.box-plc1.power.watts"]["quality"], "good")
            self.assertNotIn("tel.box-plc1.missing.value", subjects)
            self.assertEqual(state.snapshot()["points"]["missing.value"]["quality"], "bad")
            self.assertTrue(set(ModbusSim.functions) <= {1, 2, 3, 4}, ModbusSim.functions)
        finally:
            sim.shutdown(), sim.server_close()
            nats.shutdown(), nats.server_close()


# ---- BACnet/IP simulator ----
class BacnetSim(socketserver.BaseRequestHandler):
    services = []
    objects = {(0, 1): b"\x44" + struct.pack(">f", 21.5), (5, 3): b"\x91\x01"}   # REAL, ENUMERATED

    def handle(self):
        data, sock = self.request
        apdu = data[6:]
        invoke, service = apdu[2], apdu[3]
        BacnetSim.services.append(service)
        oid = struct.unpack(">I", apdu[5:9])[0]
        value = self.objects.get((oid >> 22, oid & 0x3FFFFF))
        if value is None:   # Error PDU: class object (1), code unknown-object (31)
            reply = bytes([0x50, invoke, service, 0x91, 0x01, 0x91, 0x1F])
        else:
            reply = bytes([0x30, invoke, service]) + apdu[4:9] + b"\x19\x55\x3e" + value + b"\x3f"
        npdu = b"\x01\x00" + reply
        sock.sendto(b"\x81\x0a" + struct.pack(">H", len(npdu) + 4) + npdu, self.client_address)


class Bacnet(unittest.TestCase):
    def test_reads_against_the_simulator(self):
        sim = socketserver.ThreadingUDPServer(("127.0.0.1", 0), BacnetSim)
        threading.Thread(target=sim.serve_forever, daemon=True).start()
        try:
            client = bn.Client("127.0.0.1", sim.server_address[1])
            got = readings(client.read_points, "zone1.temp_c=analog-input:1, fan.on=binary-value:3, "
                                               "zone1.temp_f=analog-input:1*1.8, nothing.here=analog-value:9", bn)
            self.assertEqual(got["zone1.temp_c"], 21.5)
            self.assertEqual(got["fan.on"], 1)
            self.assertEqual(got["zone1.temp_f"], 38.7)
            self.assertIn("returned an error", got["nothing.here"])
            self.assertEqual(set(BacnetSim.services), {bn.READ_PROPERTY})   # 15 = WriteProperty never sent
        finally:
            sim.shutdown(), sim.server_close()


# ---- OPC UA simulator (UA TCP, SecurityPolicy None) ----
def ua_response_header(status=0):
    return struct.pack("<qII", 0, 1, status) + b"\x00" + struct.pack("<i", -1) + ua.NULL_EXT


def ua_variant(v):
    if isinstance(v, bool):
        return b"\x01" + struct.pack("<?", v)
    if isinstance(v, int):
        return b"\x06" + struct.pack("<i", v)
    if isinstance(v, float):
        return b"\x0b" + struct.pack("<d", v)
    return b"\x0c" + ua.string(v)


class OpcUaSim(socketserver.BaseRequestHandler):
    nodes = {ua.nodeid(2, "s", "Line1.Speed"): 1500.5, ua.nodeid(2, "i", 1001): 456,
             ua.nodeid(0, "i", 2258): "running", ua.nodeid(2, "i", 5): True}
    AUTH = ua.nodeid(1, "i", 4242)
    services = []

    def handle(self):
        s = self.request
        try:
            assert recv_exact(s, 4) == b"HELF"
            recv_exact(s, struct.unpack("<I", recv_exact(s, 4))[0] - 8)
            ack = struct.pack("<5I", 0, 65536, 65536, 1 << 24, 1)
            s.sendall(b"ACKF" + struct.pack("<I", len(ack) + 8) + ack)
            while True:
                kind = recv_exact(s, 4)
                body = recv_exact(s, struct.unpack("<I", recv_exact(s, 4))[0] - 8)
                if kind == b"CLOF":
                    return
                r = ua.Reader(body)
                if kind == b"OPNF":
                    r.take("<I"), r.string(), r.bytestring(), r.bytestring()
                    head = ua.u32(0) + ua.string(ua.POLICY_NONE) + ua.string(None) + ua.string(None)
                else:
                    channel, token = r.take("<I"), r.take("<I")
                    assert (channel, token) == (7, 1), "wrong channel or token"
                    head = ua.u32(7) + ua.u32(1)
                seq, req = r.take("<I"), r.take("<I")
                service = r.type_id()
                OpcUaSim.services.append(service)
                auth = r.nodeid_raw()
                r.pos += 16
                r.string(), r.take("<I"), r.extension_object()
                if service == ua.OPEN_REQ:
                    out = ua.nodeid(0, "i", ua.OPEN_RESP) + ua_response_header() + ua.u32(0)
                    out += struct.pack("<IIqI", 7, 1, 0, 3600000) + ua.string(None)
                elif service == ua.CREATE_SESSION_REQ:
                    out = ua.nodeid(0, "i", ua.CREATE_SESSION_RESP) + ua_response_header()
                    out += ua.nodeid(1, "i", 1) + self.AUTH
                elif service == ua.ACTIVATE_SESSION_REQ:
                    assert auth == self.AUTH
                    out = ua.nodeid(0, "i", ua.ACTIVATE_SESSION_RESP) + ua_response_header()
                elif service == ua.READ_REQ and auth == self.AUTH:
                    r.take("<d"), r.take("<I")
                    results = []
                    for _ in range(r.take("<i")):
                        node = r.nodeid_raw()
                        attr = r.take("<I")
                        r.string(), r.take("<H"), r.string()
                        if attr == ua.ATTR_VALUE and node in self.nodes:
                            results.append(b"\x01" + ua_variant(self.nodes[node]))
                        else:   # BadNodeIdUnknown
                            results.append(b"\x02" + ua.u32(0x80340000))
                    out = (ua.nodeid(0, "i", ua.READ_RESP) + ua_response_header()
                           + struct.pack("<i", len(results)) + b"".join(results) + struct.pack("<i", -1))
                else:   # anything else (Write, Call, a read without a session): ServiceFault
                    out = ua.nodeid(0, "i", ua.SERVICE_FAULT) + ua_response_header(0x80010000)
                msg = head + ua.u32(seq) + ua.u32(req) + out
                s.sendall(kind + struct.pack("<I", len(msg) + 8) + msg)
        except (ConnectionError, AssertionError):
            pass


class OpcUa(unittest.TestCase):
    def test_reads_against_the_simulator(self):
        sim = serve(OpcUaSim)
        try:
            client = ua.Client(f"opc.tcp://127.0.0.1:{sim.server_address[1]}/onemind")
            spec = ("line.speed_rpm=ns=2;s=Line1.Speed, tank.level_pct=ns=2;i=1001*0.1, "
                    "server.state=i=2258, valve.open=ns=2;i=5, gone.value=ns=2;i=99")
            got = readings(client.read_points, spec, ua)
            self.assertEqual(got["line.speed_rpm"], 1500.5)
            self.assertEqual(got["tank.level_pct"], 45.6)
            self.assertEqual(got["server.state"], "running")
            self.assertIs(got["valve.open"], True)
            self.assertIn("0x80340000", got["gone.value"])
            got = readings(client.read_points, spec, ua)          # the session is reused
            self.assertEqual(got["line.speed_rpm"], 1500.5)
            client.close()
            self.assertEqual(OpcUaSim.services.count(ua.CREATE_SESSION_REQ), 1)
            self.assertTrue(set(OpcUaSim.services) <= {ua.OPEN_REQ, ua.CREATE_SESSION_REQ,
                                                       ua.ACTIVATE_SESSION_REQ, ua.READ_REQ}, OpcUaSim.services)
        finally:
            sim.shutdown(), sim.server_close()

    def test_bad_url_is_refused(self):
        with self.assertRaisesRegex(ValueError, "opc.tcp://"):
            ua.Client("http://127.0.0.1:4840")


# ---- socketcand simulator ----
class SocketcandSim(socketserver.BaseRequestHandler):
    received = []

    def handle(self):
        s = self.request
        try:
            s.sendall(b"< hi >")
            for want in (b"< open can0 >", b"< rawmode >"):
                got = s.recv(1024)
                SocketcandSim.received.append(got)
                s.sendall(b"< ok >" if got == want else b"< error unexpected >")
            s.sendall(b"< frame 1A0 1.000000 0102E80300000000 >< frame 18FEEE00 1.500000 7D >")
            s.settimeout(2)
            while True:
                got = s.recv(1024)
                if not got:
                    return
                SocketcandSim.received.append(got)
        except OSError:
            pass


class Can(unittest.TestCase):
    def test_listens_against_the_simulator(self):
        sim = serve(SocketcandSim)
        try:
            listener = cn.Listener("127.0.0.1", sim.server_address[1], "can0", stale_s=5)
            spec = "engine.rpm=1A0:2:u16*0.125, engine.mode=1A0:0:u16be, coolant.celsius=18FEEE00:0:i8, quiet.id=7FF:0"
            got = {}
            for _ in range(50):
                got = readings(listener.read_points, spec, cn)
                if not isinstance(got["coolant.celsius"], str):
                    break
                time.sleep(0.05)
            self.assertEqual(got["engine.rpm"], 125.0)
            self.assertEqual(got["engine.mode"], 258)
            self.assertEqual(got["coolant.celsius"], 125)
            self.assertIn("no frame with id 7FF", got["quiet.id"])
            self.assertEqual(SocketcandSim.received, [b"< open can0 >", b"< rawmode >"])   # never "< send"
        finally:
            sim.shutdown(), sim.server_close()

    def test_bus_name_is_checked(self):
        with self.assertRaisesRegex(ValueError, "CAN_BUS"):
            cn.Listener("127.0.0.1", bus="can0 >< send 1 1 ff")


if __name__ == "__main__":
    unittest.main()
