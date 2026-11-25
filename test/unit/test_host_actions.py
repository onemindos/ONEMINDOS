# SPDX-License-Identifier: Apache-2.0
"""#146 / #142: the host action service (onemindd host serve) ships in the image and runs on hubs only.

The service itself is tested in Go (internal/host); this pins how the image starts it.
"""
import os, re, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
import onemind_firstboot as fb  # noqa: E402

UNIT = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                         "onemind-host.service")).read()
CONTAINERFILE = open(os.path.join(ROOT, "os", "rootfs", "Containerfile")).read()


class HostService(unittest.TestCase):
    def test_hub_starts_it_and_other_roles_do_not(self):
        # Only the hub runs the gateway that approves actions; a worker has nothing to call it.
        for units in (fb.ROLE_UNITS, fb.LEGACY_ROLE_UNITS):
            self.assertIn("onemind-host.service", units["hub"])
            self.assertNotIn("onemind-host.service", units["worker"] + units["leaf"])

    def test_not_enabled_in_the_image(self):
        # Like every role unit it starts from onemind-firstboot once the box has a role, never at build time.
        for line in re.findall(r"systemctl enable [^;]*", CONTAINERFILE):
            self.assertNotIn("onemind-host", line)

    def test_waits_for_first_boot_and_the_data_partition(self):
        self.assertIn("ConditionPathExists=/data/onemind/firstboot/state.json", UNIT)
        self.assertIn("RequiresMountsFor=/data", UNIT)
        self.assertRegex(UNIT, r"(?m)^After=.*onemind-firstboot\.service")

    def test_systemd_makes_the_socket(self):
        # The service's filter forbids chown, so systemd owns the socket's group and mode.
        sock = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                                 "onemind-host.socket")).read()
        for line in ("ListenStream=/run/onemind/host.sock", "SocketGroup=onemind", "SocketMode=0660"):
            self.assertIn(line, sock)
        self.assertIn("Requires=onemind-host.socket", UNIT)
        self.assertNotIn("CAP_CHOWN", UNIT)

    def test_the_gateway_can_reach_the_socket_folder(self):
        # DirectoryMode= only applies when systemd creates /run/onemind; first boot may make it earlier.
        sock = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                                 "onemind-host.socket")).read()
        self.assertIn("ExecStartPre=/bin/sh -c 'mkdir -p /run/onemind && chmod go+x /run/onemind'", sock)
        src = open(os.path.join(LIB, "onemind_firstboot.py")).read()
        self.assertNotRegex(src, r"makedirs\(p\.run, mode=0o700")
        with tempfile.TemporaryDirectory() as d:
            p = fb.Paths(d)
            os.makedirs(p.run, mode=0o700)
            os.chmod(p.run, 0o700)              # what an older first boot left
            fb.run_dir(p)
            self.assertEqual(os.stat(p.run).st_mode & 0o777, 0o711)
            fb.write(os.path.join(p.run, "owner-token"), "x\n")
            self.assertEqual(os.stat(os.path.join(p.run, "owner-token")).st_mode & 0o777, 0o600)

    def test_the_gateway_unit_can_reach_the_host_socket(self):
        # The gateway talks to /run/onemind/host.sock as the user the socket admits (HostLink, core/onemind_core/hostlink.py).
        sysd = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system")
        gw = open(os.path.join(sysd, "onemind-gateway.service")).read()
        sock = open(os.path.join(sysd, "onemind-host.socket")).read()
        self.assertIn("User=onemind", gw)
        self.assertIn("SocketGroup=onemind", sock)             # the gateway's group may open it (mode 0660)
        self.assertRegex(gw, r"(?m)^RestrictAddressFamilies=.*\bAF_UNIX\b")
        self.assertRegex(gw, r"(?m)^After=.*\bonemind-host\.socket\b")   # socket first, so the first poll finds it
        self.assertNotRegex(gw, r"(?m)^PrivateNetwork=yes")
        # The default path in the gateway is the socket the host listens on.
        py = open(os.path.join(ROOT, "core", "onemind_core", "hostlink.py")).read()
        self.assertIn('Path("/run/onemind/host.sock")', py)
        self.assertIn("ListenStream=/run/onemind/host.sock", sock)

    def test_never_installs_with_rauc_directly(self):
        # An OS install goes through the update engine (snapshot + health gate), never a raw rauc call.
        self.assertNotIn("rauc install", UNIT)
        go = open(os.path.join(ROOT, "internal", "host", "update.go")).read()
        self.assertNotRegex(go, r'"rauc"|rauc install"')


class HostSocketReach(unittest.TestCase):
    """#875 mount-host-socket: the gateway is a systemd unit, not a k3s pod, so the socket reaches it through
    onemind-gateway.service and no manifest mounts anything from the host for it."""
    GATE = open(os.path.join(ROOT, "os", "gate", "onemind-health-gate")).read()
    FB = open(os.path.join(ROOT, "test", "qemu", "firstboot.py")).read()

    def manifests(self):
        for top in (os.path.join(ROOT, "os", "rootfs", "layers"), os.path.join(ROOT, "deploy")):
            for d, _, files in os.walk(top):
                for f in files:
                    if f.endswith((".yaml", ".yml")):
                        yield os.path.join(d, f)

    def test_no_shipped_manifest_mounts_the_host_socket_or_a_host_path(self):
        seen = 0
        for path in self.manifests():
            text = open(path).read()
            if not re.search(r"(?m)^apiVersion:", text):
                continue   # Kubernetes objects only (services.yaml and friends name the socket's unit, not a mount)
            seen += 1
            self.assertNotIn("host.sock", text, path)
            self.assertNotIn("/run/onemind", text, path)
            if "/manifests/" in path or "/k8s/" in path:
                self.assertNotIn("hostPath", text, path)   # the core pods stay PSA baseline: no host path
        self.assertGreater(seen, 3)

    def test_the_core_platform_pod_stays_unprivileged(self):
        core = open(os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib", "onemind", "manifests",
                                 "onemind-core.yaml")).read()
        for never in ("privileged", "capabilities", "hostPath", "hostNetwork", "hostPID"):
            self.assertNotIn(never, core)

    def gate_probe(self):
        m = re.search(r"(?ms)^host_helper\(\) \{.*?^\}", self.GATE)
        self.assertIsNotNone(m, "the gate defines host_helper()")
        return m.group(0)

    def run_probe(self, sock, active):
        import subprocess
        stub = "systemctl() { return %d; }" % (0 if active else 3)
        out = subprocess.run(["bash", "-c", f"{stub}\nHOST_SOCK={sock}\n{self.gate_probe()}\nhost_helper"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return out

    def test_the_gate_reports_reachable_or_missing(self):
        import socket
        d = tempfile.mkdtemp(prefix="hg")
        sock = os.path.join(d, "host.sock")
        self.assertEqual(self.run_probe(sock, True), "missing")         # no socket file
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(sock); s.listen(1)
        try:
            self.assertEqual(self.run_probe(sock, True), "reachable")
            self.assertEqual(self.run_probe(sock, False), "missing")    # the socket unit is not active
        finally:
            s.close()
        regular = os.path.join(d, "file")
        open(regular, "w").close()
        self.assertEqual(self.run_probe(regular, True), "missing")      # a plain file is not a socket

    def test_the_gate_only_logs_it_and_never_connects(self):
        # onemind-host.service is ordered After= the gate, so a connect from the gate would wait on itself.
        probe = self.gate_probe()
        for never in ("curl", "socat", "nc ", "/dev/tcp"):
            self.assertNotIn(never, probe)
        uses = [l for l in self.GATE.splitlines() if "host_helper" in l and not l.startswith("host_helper()")]
        self.assertTrue(uses)
        for line in uses:
            self.assertRegex(line, r'log "HOST-HELPER \$\(host_helper\)')   # report only, never a verdict
        self.assertGreaterEqual(self.GATE.count("report_host"), 4)   # defined, then after every k3s verdict

    def test_firstboot_f12_proves_the_socket_end_to_end(self):
        body = self.FB[self.FB.index("F12_PY = "):self.FB.index("def main(")]
        for needle in ("/v1/status", "/v1/os/updates", "Bearer", "hostname",
                       "systemctl stop onemind-host.service onemind-host.socket", "rm -f /run/onemind/host.sock",
                       "systemctl start onemind-host.socket", "engine_unreachable", 'record("F12"'):
            self.assertIn(needle, body)
        main = self.FB[self.FB.index("def main("):]
        self.assertLess(main.index("f11(vm"), main.index("f12(vm, token)"))
        self.assertLess(main.index("f12(vm, token)"), main.index('vm.mark("F3 reboot keeps state")'))
        crit = open(os.path.join(ROOT, "test", "qemu", "CRITERIA-FIRSTBOOT.md")).read()
        self.assertIn("| F12 |", crit)


class GateReleasesTheHostHelperAtTheDecision(unittest.TestCase):
    """F12 root cause (image run 45537872867): onemind-host.service is ordered After= the health gate, and the
    gate was Type=oneshot, so on a committed boot the helper did not start until the gate's report-only k3s watch
    ended (up to ONEMIND_GATE_TIMEOUT, 300 s). The gate now says READY=1 once the slot is decided."""
    GATE = open(os.path.join(ROOT, "os", "gate", "onemind-health-gate")).read()
    GATE_UNIT = open(os.path.join(ROOT, "os", "gate", "onemind-health-gate.service")).read()

    def case(self, mode):
        m = re.search(r"(?ms)^%s\)\n(.*?);;" % re.escape(mode), self.GATE)
        self.assertIsNotNone(m, mode)
        return m.group(1)

    def test_the_unit_is_notify_so_after_waits_for_ready_only(self):
        unit = {k.strip(): v.strip() for k, v in
                (l.split("=", 1) for l in self.GATE_UNIT.splitlines() if "=" in l and not l.startswith("#"))}
        self.assertEqual(unit["Type"], "notify")
        self.assertEqual(unit["NotifyAccess"], "all")      # systemd-notify is a child of the script
        self.assertEqual(unit["RemainAfterExit"], "yes")
        self.assertEqual(unit["TimeoutStartSec"], "infinity")   # a trial still has its own deadline

    def test_the_host_helper_still_waits_for_the_gate(self):
        # A trial boot keeps the helper (and so OS install) back until the slot is marked good.
        after = re.search(r"(?m)^After=(.*)$", UNIT).group(1).split()
        self.assertIn("onemind-health-gate.service", after)

    def test_committed_and_fell_back_say_ready_before_the_watch(self):
        for mode, word in (("committed", "committed"), ("fell-back", "fell-back")):
            body = self.case(mode)
            self.assertLess(body.index("commit &&"), body.index("notify_ready " + word), mode)
            self.assertLess(body.index("notify_ready " + word), body.index("watch_only"), mode)

    def test_a_trial_says_ready_only_after_mark_good(self):
        body = self.case("trial")
        self.assertEqual(body.count("notify_ready"), 1)
        line = next(l for l in body.splitlines() if "notify_ready" in l)
        self.assertIn("RESULT mark-good", line)
        self.assertRegex(line, r"notify_ready mark-good; exit 0$")

    def run_notify(self, sock, rc):
        import subprocess
        d = tempfile.mkdtemp(prefix="gn")
        calls = os.path.join(d, "calls")
        fn = re.search(r"(?ms)^notify_ready\(\) \{.*?^\}", self.GATE)
        self.assertIsNotNone(fn, "the gate defines notify_ready()")
        script = (f'systemd-notify() {{ echo "$*" >> {calls}; return {rc}; }}\n'
                  f'log() {{ echo "LOG $*"; }}\nSLOT=A\n{fn.group(0)}\nnotify_ready committed; echo RC=$?')
        env = {k: v for k, v in os.environ.items() if k != "NOTIFY_SOCKET"}
        if sock:
            env["NOTIFY_SOCKET"] = sock
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, check=True).stdout
        return out, (open(calls).read() if os.path.exists(calls) else "")

    def test_notify_ready_sends_ready_under_systemd_only(self):
        out, calls = self.run_notify(None, 0)
        self.assertEqual(calls, "")                         # run by hand or in a test: nothing to tell
        self.assertIn("RC=0", out)
        out, calls = self.run_notify("/run/systemd/notify", 0)
        self.assertIn("--ready", calls)
        self.assertIn("slot A decided: committed", calls)
        self.assertNotIn("NOTIFY-ERROR", out)
        out, calls = self.run_notify("/run/systemd/notify", 1)
        self.assertIn("LOG NOTIFY-ERROR", out)              # a failed notify is logged, never silent
        self.assertIn("RC=0", out)                          # and the gate goes on to its watch


if __name__ == "__main__":
    unittest.main()
