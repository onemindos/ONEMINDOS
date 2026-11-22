# SPDX-License-Identifier: Apache-2.0
"""The setup wizard's root helper (#578): the web part runs unprivileged (DynamicUser, no capabilities) and
only asks; the root helper takes three fixed requests, checks every field again and applies the form.

Runs with plain python3 (no core venv): the hub path, which needs onemind_core, is covered in
test_firstboot.py. The unit-file checks here read the files only; the score checks need systemd-analyze.
"""
import contextlib, io, json, os, shutil, socket, stat, subprocess, sys, tempfile, threading, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
UNITS = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system")
sys.path.insert(0, LIB)
import onemind_firstboot as fb  # noqa: E402
import onemind_setup as setup  # noqa: E402
import onemind_setup_helper as helper  # noqa: E402

CA_SHA = "ab" * 32
JOIN = f"onemind-join:v1?code=7KQ4-M2XP-9D3F&ca={CA_SHA}&role=worker&hub=https%3A%2F%2Fhome-box.local"
LAN = "192.0.2.10"            # TEST-NET-1 (RFC 5737)
CODE = "23456789AB"


def text(path):
    with open(path) as f:
        return f.read()


def req(**kw) -> bytes:
    return json.dumps(kw).encode()


class Root(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = fb.Paths(self.tmp.name)
        os.makedirs(os.path.join(self.tmp.name, "dev"))
        open(self.p.console, "w").close()
        self.started = []
        for pt in (mock.patch.object(fb, "systemctl", lambda *a: self.started.append(a) or 0),
                   mock.patch.object(fb, "lan_addr", lambda: LAN),
                   mock.patch.object(fb.socket, "gethostname", lambda: "Home_Box")):
            pt.start()
            self.addCleanup(pt.stop)
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def configured(self):
        os.makedirs(os.path.dirname(self.p.state), exist_ok=True)
        with open(self.p.state, "w") as f:
            json.dump({"role": "hub", "node_id": "n"}, f)

    def refused(self, raw, kind):
        r = helper.handle(self.p, raw)
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["kind"], kind, r)
        self.assertIsInstance(r["error"], str)
        return r


class HelperInput(Root):
    """Every request is checked as if the web part were hostile: fixed ops, fixed fields, bounded values."""

    def test_status(self):
        self.assertEqual(helper.handle(self.p, req(op="status")), {"ok": True, "configured": False})
        self.configured()
        self.assertEqual(helper.handle(self.p, req(op="status")), {"ok": True, "configured": True})

    def test_not_json_or_not_an_object_or_too_big(self):
        for raw in (b"", b"role=hub", b"\xff\xfe", b"[1]", b'"status"', b"null"):
            self.refused(raw, "bad-request")
        self.refused(b" " * (helper.MAX_REQUEST + 1) + req(op="status"), "bad-request")

    def test_unknown_op_and_extra_fields(self):
        for raw in (req(op="chown"), req(op="STATUS"), req(op=None), req(), req(op="status", path="/etc"),
                    req(op="publish-code", code=CODE, mode=0o644), req(op="apply", config={"role": "hub"}, root="/")):
            self.refused(raw, "bad-request")

    def test_code_must_be_ten_symbols_of_the_alphabet(self):
        for bad in ("", "23456789A", "23456789ABC", "23456789ab", "0123456789", "OOOOOOOOOO", "IIIIIIIIII",
                    "2345-6789A", "../../etc/", 2345678912, None, ["23456789AB"]):
            self.refused(req(op="publish-code", code=bad), "bad-request")
        self.assertFalse(os.path.exists(os.path.join(self.p.run, helper.CODE_FILE)))

    def test_apply_config_shape(self):
        for cfg in ("role=hub", ["hub"], {}, {"name": "x"}, {"role": "hub", "owner": "me"},
                    {"role": 1}, {"role": "hub", "name": None}, {"role": "worker", "join_code": "x" * 4000}):
            self.refused(req(op="apply", config=cfg), "bad-request")
        self.assertFalse(os.path.exists(self.p.state))

    def test_apply_validates_again(self):
        # the web part checks the form too, but the helper never trusts it
        for cfg in ({"role": "admin"}, {"role": "worker"}, {"role": "worker", "join_code": "onemind-join:v1?code=x"},
                    {"role": "hub", "join_code": JOIN}, {"role": "hub", "name": 'a"b'},
                    {"role": "worker", "join_code": JOIN, "hub_addr": "not-an-ip"}):
            self.refused(req(op="apply", config=cfg), "invalid")
        self.assertFalse(os.path.exists(self.p.state))
        self.assertEqual(self.started, [])

    def test_nothing_after_the_owner_exists(self):
        self.configured()
        self.refused(req(op="publish-code", code=CODE), "configured")
        self.refused(req(op="apply", config={"role": "worker", "join_code": JOIN}), "configured")
        self.assertFalse(os.path.exists(self.p.join_code))


class HelperApplies(Root):
    def test_publish_code_for_the_screen(self):
        self.assertEqual(helper.handle(self.p, req(op="publish-code", code=CODE)), {"ok": True})
        f = os.path.join(self.p.run, helper.CODE_FILE)
        self.assertEqual(text(f), CODE + "\n")
        self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.p.run).st_mode), 0o711)
        self.assertIn(f"ONEMIND SETUP CODE: {CODE}", text(self.p.console))

    def test_apply_a_worker(self):
        helper.handle(self.p, req(op="publish-code", code=CODE))
        r = helper.handle(self.p, req(op="apply", config={"role": "worker", "join_code": JOIN, "hub_addr": LAN}))
        self.assertEqual(r, {"ok": True, "role": "worker", "token": None})
        self.assertEqual(text(self.p.join_code), JOIN + "\n")
        st = json.loads(text(self.p.state))
        self.assertEqual((st["source"], st["hub_addr"]), ("wizard", LAN))
        self.assertFalse(os.path.exists(os.path.join(self.p.run, helper.CODE_FILE)))   # the code is spent
        self.assertTrue(self.started)


class PeerCheck(unittest.TestCase):
    """The socket is 0666 so the DynamicUser can reach it; the helper serves only the wizard unit's processes."""

    def test_cgroup_must_be_the_wizard_unit(self):
        self.assertEqual(helper.UNIT_CGROUP, "/system.slice/onemind-setup.service")
        self.assertTrue(helper.cgroup_ok("0::/system.slice/onemind-setup.service\n"))
        for text in ("", "0::/system.slice/onemind-gateway.service\n", "0::/user.slice/user-1000.slice/session-2.scope\n",
                     "0::/system.slice/onemind-setup.service/evil\n", "0::/system.slice/onemind-setup.services\n",
                     "1:name=systemd:/system.slice/onemind-setup.service\n"):
            self.assertFalse(helper.cgroup_ok(text), text)

    def test_root_and_strangers_are_refused(self):
        unit = lambda pid: "0::/system.slice/onemind-setup.service\n"
        other = lambda pid: "0::/system.slice/onemind-gateway.service\n"
        self.assertTrue(helper.peer_allowed(4242, 61500, read_cgroup=unit))
        self.assertFalse(helper.peer_allowed(4242, 0, read_cgroup=unit))        # the web part never runs as root
        self.assertFalse(helper.peer_allowed(4242, 61500, read_cgroup=other))
        self.assertFalse(helper.peer_allowed(0, 61500, read_cgroup=unit))       # no peer pid

        def gone(pid):
            raise FileNotFoundError(pid)
        self.assertFalse(helper.peer_allowed(4242, 61500, read_cgroup=gone))


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "needs Unix sockets")
class OverTheSocket(Root):
    """The web part's client and the helper's server talk the same one-line JSON over a Unix socket."""

    def serve(self, allowed=True):
        path = os.path.join(self.tmp.name, "h.sock")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        srv.listen(4)
        self.addCleanup(srv.close)

        def loop():
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                with conn:
                    helper.serve(self.p, conn, check=lambda c: allowed)
        threading.Thread(target=loop, daemon=True).start()
        return setup.Helper(path)

    def test_round_trip(self):
        h = self.serve()
        self.assertFalse(h.configured())
        h.publish_code(CODE)
        self.assertEqual(text(os.path.join(self.p.run, helper.CODE_FILE)).strip(), CODE)
        with self.assertRaises(setup.HelperError) as e:
            h.apply({"role": "worker"})
        self.assertEqual(e.exception.kind, "invalid")
        self.assertEqual(h.apply({"role": "worker", "join_code": JOIN})["role"], "worker")
        self.assertTrue(h.configured())

    def test_a_refused_peer_changes_nothing(self):
        h = self.serve(allowed=False)
        with self.assertRaises(setup.HelperError) as e:
            h.publish_code(CODE)
        self.assertEqual(e.exception.kind, "forbidden")
        self.assertFalse(os.path.exists(os.path.join(self.p.run, helper.CODE_FILE)))

    def test_a_failed_apply_is_an_answer(self):
        h = self.serve()
        with mock.patch.object(fb, "finish", side_effect=PermissionError("no")):
            with self.assertRaises(setup.HelperError) as e:
                h.apply({"role": "worker", "join_code": JOIN})
        self.assertEqual(e.exception.kind, "failed")
        self.assertFalse(h.configured())

    def test_no_helper_is_an_error_not_a_crash(self):
        with self.assertRaises(setup.HelperError) as e:
            setup.Helper(os.path.join(self.tmp.name, "missing.sock")).configured()
        self.assertEqual(e.exception.kind, "unavailable")


def unit(name):
    """A unit file as {section: [(key, value), ...]} (repeated keys kept, comments dropped)."""
    out, sec = {}, None
    with open(os.path.join(UNITS, name)) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("["):
                sec = line.strip("[]")
                out.setdefault(sec, [])
                continue
            k, v = line.split("=", 1)
            out[sec].append((k, v))
    return out


def values(u, sec, key):
    return [v for k, v in u.get(sec, []) if k == key]


class WebUnitIsUnprivileged(unittest.TestCase):
    """Acceptance (#578): the web part has no root and none of the chown/permission capabilities."""
    WEB = "onemind-setup.service"

    def test_web_runs_as_a_dynamic_user_without_capabilities(self):
        u = unit(self.WEB)
        self.assertEqual(values(u, "Service", "DynamicUser"), ["yes"])
        self.assertNotIn("root", values(u, "Service", "User"))
        self.assertEqual(values(u, "Service", "CapabilityBoundingSet"), [""])   # empty: no capability at all
        self.assertEqual(values(u, "Service", "AmbientCapabilities"), [""])
        self.assertEqual(values(u, "Service", "PrivateDevices"), ["yes"])
        self.assertEqual(values(u, "Service", "NoNewPrivileges"), ["yes"])
        self.assertEqual(values(u, "Service", "ReadWritePaths"), [])            # it writes nothing on the box
        for k, v in u["Service"]:
            for cap in ("CAP_CHOWN", "CAP_DAC_OVERRIDE", "CAP_FOWNER", "CAP_SYS_ADMIN"):
                self.assertNotIn(cap, v, f"{k}={v}")

    def test_only_the_firewall_lines_run_privileged(self):
        u = unit(self.WEB)
        # an Exec line's prefix is the characters before the path; "+" there means full privileges
        privileged = [v for k, v in u["Service"] if k.startswith("Exec") and "+" in v.split("/", 1)[0]]
        self.assertTrue(privileged)
        for v in privileged:
            self.assertRegex(v, r"^-\+(/usr/sbin/nft |/bin/sh -c 'test -e /etc/onemind/wizard-local-only \|\| exec "
                                r"/usr/sbin/nft |/bin/rm -f /run/onemind/setup-code$)")
        self.assertEqual(values(u, "Service", "ExecStart"), ["/usr/lib/onemind/onemind-setup"])

    def test_web_needs_the_helper_socket(self):
        u = unit(self.WEB)
        self.assertIn("onemind-setup-helper.socket", " ".join(values(u, "Unit", "Requires")))
        self.assertIn("onemind-setup-helper.socket", " ".join(values(u, "Unit", "After")))


class HelperUnits(unittest.TestCase):
    def test_socket(self):
        u = unit("onemind-setup-helper.socket")
        self.assertEqual(values(u, "Socket", "ListenStream"), [setup.HELPER_SOCK])
        self.assertEqual(values(u, "Socket", "Accept"), ["yes"])
        self.assertEqual(values(u, "Socket", "SocketMode"), ["0666"])        # peer check in the helper (cgroup)
        self.assertIn("onemind-setup.service", values(u, "Unit", "PartOf"))  # gone when the wizard stops
        self.assertNotIn("Install", u)                                       # never enabled on its own

    def test_helper_keeps_the_root_part_small_and_sandboxed(self):
        u = unit("onemind-setup-helper@.service")
        s = dict(u["Service"])
        self.assertEqual(s["ExecStart"], "/usr/lib/onemind/onemind-setup-helper")
        self.assertEqual(s["StandardInput"], "socket")
        self.assertEqual(s["StandardOutput"], "journal")   # log lines never land on the socket
        self.assertEqual(s["CapabilityBoundingSet"], "CAP_CHOWN CAP_DAC_OVERRIDE CAP_FOWNER")
        for d, v in (("NoNewPrivileges", "yes"), ("ProtectSystem", "strict"), ("ProtectHome", "yes"),
                     ("MemoryDenyWriteExecute", "yes"), ("RestrictNamespaces", "yes"), ("ProtectProc", "default"),
                     ("UMask", "0077")):
            self.assertEqual(s.get(d), v, d)
        self.assertIn("@system-service", values(u, "Service", "SystemCallFilter"))

    def test_wrappers_are_executable(self):
        for name in ("onemind-setup", "onemind-setup-helper"):
            path = os.path.join(LIB, name)
            self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR, name)
        with open(os.path.join(LIB, "onemind-setup-helper")) as f:
            self.assertIn("/usr/lib/onemind/onemind_setup_helper.py", f.read())


@unittest.skipUnless(shutil.which("systemd-analyze"), "needs systemd-analyze")
class Scores(unittest.TestCase):
    def score_ok(self, name, threshold):
        with tempfile.TemporaryDirectory() as d:
            # a template cannot be scored by itself: score an instance of it
            path = os.path.join(d, name.replace("@.", "@1."))
            shutil.copy(os.path.join(UNITS, name), path)
            r = subprocess.run(["systemd-analyze", "security", "--offline=true", f"--threshold={threshold}",
                                "--no-pager", path], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # --threshold is on the 0..100 exposure scale (19 = under 2.0 of 10). Measured with systemd 255: web 1.2
    # (it was 8.4 as root), helper 2.5.
    def test_web_scores_under_2(self):
        self.score_ok("onemind-setup.service", 19)

    def test_helper_scores_under_3(self):
        self.score_ok("onemind-setup-helper@.service", 29)


if __name__ == "__main__":
    unittest.main()
