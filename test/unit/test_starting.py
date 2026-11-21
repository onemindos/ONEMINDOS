# SPDX-License-Identifier: Apache-2.0
"""The "OneMind is starting" page (onemind_starting.py): it answers 503 over HTTPS, shares the port with the
gateway (SO_REUSEPORT), hands over without a gap, and the units are ordered so the gateway no longer waits
for the network. Whole-boot proof is test/qemu F10 (CRITERIA-FIRSTBOOT.md section 6)."""
from pathlib import Path
import importlib.util, os, socket, ssl, sys, tempfile, threading, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib")
sys.path.insert(1, os.path.join(ROOT, "core"))
spec = importlib.util.spec_from_file_location("onemind_starting", os.path.join(LIB, "onemind", "onemind_starting.py"))
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fetch(port, method="GET"):
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE   # loopback test with a throw-away CA
    with socket.create_connection(("127.0.0.1", port), 3) as raw, ctx.wrap_socket(raw) as s:
        s.sendall(f"{method} /anything HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        buf = b""
        while chunk := s.recv(4096):
            buf += chunk
    return buf.decode()


class Units(unittest.TestCase):
    def test_gateway_does_not_wait_for_the_network_or_nats(self):
        unit = read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-gateway.service")
        active = [l for l in unit.splitlines() if l.startswith(("After=", "Wants=", "Requires="))]
        self.assertTrue(active)
        for l in active:
            self.assertNotIn("network-online", l)
        self.assertFalse([l for l in active if l.startswith("After=") and "onemind-nats" in l])
        self.assertTrue([l for l in active if l.startswith("After=") and "onemind-starting.service" in l])

    def test_starting_unit(self):
        unit = read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-starting.service")
        for want in ("Type=notify", "User=onemind", "AmbientCapabilities=CAP_NET_BIND_SERVICE",
                     "ExecStart=/usr/lib/onemind/onemind-starting", "After=onemind-firstboot.service"):
            self.assertIn(want, unit)
        self.assertNotIn("network-online", unit)
        wrapper = os.path.join(LIB, "onemind", "onemind-starting")
        self.assertTrue(os.access(wrapper, os.X_OK))
        self.assertIn("onemind_starting.py", read("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind-starting"))

    def test_hub_firstboot_starts_it_first_and_workers_do_not(self):
        spec2 = importlib.util.spec_from_file_location("fb", os.path.join(LIB, "onemind", "onemind_firstboot.py"))
        fb = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(fb)
        self.assertEqual(fb.ROLE_UNITS["hub"][0], "onemind-starting.service")
        for role in ("worker", "leaf"):
            self.assertNotIn("onemind-starting.service", fb.ROLE_UNITS[role])


class Page(unittest.TestCase):
    def test_503_with_marker_and_never_200(self):
        self.assertIn(b"503 Service Unavailable", st.RESPONSE)
        self.assertIn(b"X-OneMind-Starting: 1", st.RESPONSE)
        self.assertIn(b"no-store", st.RESPONSE)
        self.assertIn(b"OneMind is starting", st.PAGE_BYTES)
        self.assertIn(b"Content-Length: " + str(len(st.PAGE_BYTES)).encode(), st.RESPONSE)

    def test_no_tls_means_nothing_to_hold(self):
        self.assertEqual(st.run({}), 0)


try:
    from onemind_core.ca import BoxCA   # noqa: F401
    HAVE_CA = True
except Exception:                       # a system cryptography older than the gateway venv's: CI image job runs it
    HAVE_CA = False


@unittest.skipUnless(HAVE_CA, "onemind_core.ca needs the gateway's cryptography")
class Handover(unittest.TestCase):
    def test_serves_then_hands_the_port_to_a_listener_with_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            port = free_port()
            env = {"ONEMIND_NET_TLS": "1", "ONEMIND_NET_TLS_DIR": d, "ONEMIND_NET_BOX_NAME": "testbox",
                   "ONEMIND_NET_HTTPS_HOST": "127.0.0.1", "ONEMIND_NET_HTTPS_PORTS": str(port)}
            ready = threading.Event()
            result = []
            t = threading.Thread(target=lambda: result.append(st.run(env, ready=lambda _u: ready.is_set(), grace=0.5, poll=0.05)))
            # the CA must exist as firstboot makes it
            BoxCA(Path(d), "testbox").ensure_https_cert()
            t.start()
            for _ in range(100):
                try:
                    out = fetch(port)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                self.fail("the starting page never answered")
            self.assertTrue(out.startswith("HTTP/1.1 503"))
            self.assertIn("X-OneMind-Starting: 1", out)
            self.assertTrue(fetch(port, "HEAD").startswith("HTTP/1.1 503"))
            # the "gateway": same option, same port, listening only now
            gw = st.bind("127.0.0.1", port)
            ready.set()
            refused = 0
            t0 = time.time()
            while t.is_alive() and time.time() - t0 < 10:
                try:
                    fetch(port)
                except ConnectionRefusedError:
                    refused += 1
                except OSError:
                    pass
                time.sleep(0.02)
            t.join(5)
            gw.close()
            self.assertEqual(result, [0])
            self.assertEqual(refused, 0)


class Wiring(unittest.TestCase):
    def test_f10_probe_compiles_and_budget_has_the_key(self):
        import ast, json, re as _re
        src = read("test", "qemu", "firstboot.py")
        ast.parse(src)
        probe = _re.search(r"F10_PY = r'''(.*?)'''", src, _re.S).group(1)
        compile(probe, "f10-probe", "exec")
        self.assertIn("f10(vm", src)
        self.assertIn("time_to_dashboard_s", json.loads(read("test", "perf", "budget.json")))

    def test_perf_check_reads_the_dashboard_report(self):
        pspec = importlib.util.spec_from_file_location("perf", os.path.join(ROOT, "test", "perf", "perf.py"))
        perf = importlib.util.module_from_spec(pspec)
        pspec.loader.exec_module(perf)
        m = perf.measured([{"kind": "dashboard", "time_to_dashboard_s": 42.0}])
        self.assertEqual(m, {"time_to_dashboard_s": 42.0})
        _, ok = perf.check({"time_to_dashboard_s": 90}, m, ["time_to_dashboard_s"])
        self.assertTrue(ok)
        _, ok = perf.check({"time_to_dashboard_s": 30}, m, ["time_to_dashboard_s"])
        self.assertFalse(ok)

    def test_criteria_section_is_preregistered(self):
        import hashlib
        h = hashlib.sha256(open(os.path.join(ROOT, "test", "qemu", "CRITERIA-FIRSTBOOT.md"), "rb").read()).hexdigest()
        self.assertIn(h, read("test", "qemu", "PREREGISTRATION.sha256"))


class GatewayBind(unittest.TestCase):
    def test_gateway_binds_with_reuseport(self):
        self.assertIn("SO_REUSEPORT", read("core", "onemind_core", "serve.py"))
        try:
            from onemind_core import serve
        except Exception as e:      # uvicorn not installed in this interpreter
            self.skipTest(str(e))
        port = free_port()
        a = serve._bind("127.0.0.1", port)
        try:
            b = st.bind("127.0.0.1", port)   # would raise EADDRINUSE without SO_REUSEPORT on both
            b.close()
        finally:
            a.close()


if __name__ == "__main__":
    unittest.main()
