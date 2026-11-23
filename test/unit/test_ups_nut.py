# SPDX-License-Identifier: Apache-2.0
"""IMG-06 (#244): a UPS on USB is found at boot, watched by NUT's upsmon, and a low battery shuts the box down in order.

The order (apps, then k3s, then the data volume, then poweroff) and the config the box writes for NUT are tested
here without NUT. DummyUpsEndToEnd runs the real NUT programs with NUT's dummy-ups driver: the fake UPS goes from
OL (on mains) to OB LB (on battery, low) and upsmon must start the ordered shutdown, in dry-run mode so nothing
stops. It needs the Debian nut-server and nut-client packages; without them it is skipped, and
ONEMIND_REQUIRE_NUT=1 turns that skip into a failure. Pulling the mains on a real UPS stays a device proof.
"""
import importlib.util, os, re, socket, subprocess, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAYER = os.path.join(ROOT, "os", "rootfs", "layers", "onemind")
LIB = os.path.join(LAYER, "usr", "lib", "onemind")
UNITS = os.path.join(LAYER, "usr", "lib", "systemd", "system")
SCRIPT = os.path.join(LIB, "onemind_ups.py")
spec = importlib.util.spec_from_file_location("onemind_ups", SCRIPT)
ups = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ups)


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def slurp(path):
    with open(path) as f:
        return f.read()


def unit(name):
    with open(os.path.join(UNITS, name)) as f:
        return f.read()


SCANNER = """[nutdev1]
\tdriver = "usbhid-ups"
\tport = "auto"
\tvendorid = "051D"
\tproductid = "0002"
\tproduct = "Back-UPS ES 700"
\tserial = "3B1234X56789"
\tvendor = "American Power Conversion"
\tbus = "001"
[nutdev2]
\tdriver = "blazer_usb"
\tport = "auto"
"""


class Recorder:
    """Stands in for subprocess: records every command, answers `crictl ps -q` with two containers."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def __call__(self, cmd, timeout=None):
        self.calls.append(list(cmd))
        if any(f in " ".join(cmd) for f in self.fail):
            raise subprocess.CalledProcessError(1, cmd)
        return "c1\nc2\n" if cmd[-2:] == ["ps", "-q"] else ""

    def joined(self):
        return [" ".join(c) for c in self.calls]


class Fs:
    """The few host facts the shutdown reads: k3s's leftover processes, mounts and the unlocked data disk."""

    def __init__(self, procs=("101", "102"), mounts=(), mapper=True):
        self.procs, self.mounts, self.mapper = list(procs), list(mounts), mapper
        self.killed = []

    def k3s_procs(self):
        return [] if self.killed else self.procs

    def mounts_under(self, prefixes):
        return [m for m in self.mounts if m.startswith(prefixes)]

    def has_mapper(self):
        return self.mapper


class Scanner(unittest.TestCase):
    def test_the_first_usb_ups_is_taken_with_only_known_keys(self):
        dev = ups.parse_scanner(SCANNER)
        self.assertEqual(dev, {"driver": "usbhid-ups", "port": "auto", "vendorid": "051D", "productid": "0002",
                               "serial": "3B1234X56789"})

    def test_nothing_found_or_a_strange_value_is_no_ups(self):
        self.assertIsNone(ups.parse_scanner(""))
        self.assertIsNone(ups.parse_scanner('[nutdev1]\n\tdriver = "usbhid-ups; rm -rf /"\n\tport = "auto"\n'))
        self.assertIsNone(ups.parse_scanner('[nutdev1]\n\tport = "auto"\n'))


class Render(unittest.TestCase):
    def setUp(self):
        self.files = ups.render(ups.parse_scanner(SCANNER), "pw-not-real")

    def test_standalone_mode_on_loopback_only(self):
        self.assertEqual(self.files["nut.conf"].strip(), "MODE=standalone")
        self.assertEqual(self.files["upsd.conf"].split(), ["LISTEN", "127.0.0.1", "3493", "LISTEN", "::1", "3493"])
        self.assertIn('[onemind]\n\tdriver = "usbhid-ups"\n\tport = "auto"\n\tvendorid = "051D"', self.files["ups.conf"])

    def test_upsmon_is_the_primary_and_starts_the_shutdown_unit(self):
        mon = self.files["upsmon.conf"]
        self.assertIn("MONITOR onemind@127.0.0.1:3493 1 upsmon-onemind pw-not-real primary", mon)
        self.assertIn('SHUTDOWNCMD "/usr/bin/systemctl start --no-block onemind-ups-shutdown.service"', mon)
        self.assertIn("FINALDELAY 0", mon)
        self.assertIn("RUN_AS_USER nut", mon)
        self.assertIn("POWERDOWNFLAG /run/onemind-ups-monitor/killpower", mon)   # never /etc: the root is read-only
        self.assertIn("[upsmon-onemind]\n\tpassword = pw-not-real\n\tupsmon primary", self.files["upsd.users"])

    def test_setup_writes_the_files_once_and_keeps_the_password(self):
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "ups")
            self.assertEqual(ups.setup(conf, scan=lambda: SCANNER, gid=None), 0)
            first = slurp(os.path.join(conf, "upsmon.conf"))
            for name in ups.FILES:
                self.assertEqual(os.stat(os.path.join(conf, name)).st_mode & 0o777, 0o640, name)
            self.assertEqual(os.stat(conf).st_mode & 0o777, 0o750)
            self.assertEqual(ups.setup(conf, scan=lambda: "", gid=None), 0)    # already set up: no new scan, same file
            self.assertEqual(slurp(os.path.join(conf, "upsmon.conf")), first)
            pw = re.search(r"upsmon-onemind (\S+) primary", first).group(1)
            self.assertGreaterEqual(len(pw), 32)

    def test_no_ups_means_the_unit_is_skipped_not_failed(self):
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "ups")
            self.assertEqual(ups.setup(conf, scan=lambda: "", gid=None), 1)   # ExecCondition: 1 = skip quietly
            self.assertFalse(os.path.exists(conf))


class Shutdown(unittest.TestCase):
    def go(self, **kw):
        r, fs = Recorder(**kw), Fs(mounts=["/run/k3s/containerd/io.containerd.runtime.v2.task/k8s.io/c1/rootfs",
                                           "/var/lib/kubelet/pods/p1/volumes/x", "/run/k3s/containerd"])

        def kill(sig, pids):
            r.calls.append(["kill", "-" + sig, *pids])
            fs.killed.append(sig)
        ups.shutdown(runner=r, fs=fs, kill=kill, sleep=lambda s: None)
        return r.joined()

    def test_apps_then_k3s_then_the_data_volume_then_poweroff(self):
        calls = self.go()
        idx = {c: i for i, c in enumerate(calls)}
        order = ["systemctl stop k3s.service",                                # nothing restarts an app from here
                 "/usr/local/bin/k3s crictl stop --timeout 30 c1 c2",          # apps get SIGTERM and 30 s
                 "kill -TERM 101 102",                                         # then the container runtime
                 "umount /run/k3s/containerd/io.containerd.runtime.v2.task/k8s.io/c1/rootfs",
                 "journalctl --relinquish-var", "sync", "systemctl stop data.mount",
                 "/usr/lib/systemd/systemd-cryptsetup detach onemind-data",
                 "systemctl poweroff"]
        for c in order:
            self.assertIn(c, idx, c)
        self.assertEqual([idx[c] for c in order], sorted(idx[c] for c in order))
        self.assertEqual(calls[-1], "systemctl poweroff")

    def test_deepest_mounts_go_first(self):
        um = [c for c in self.go() if c.startswith("umount ")]
        self.assertEqual(um[-1], "umount /run/k3s/containerd")

    def test_a_failing_step_never_stops_the_poweroff(self):
        calls = self.go(fail=("crictl", "data.mount", "cryptsetup"))
        self.assertEqual(calls[-1], "systemctl poweroff")
        self.assertIn("kill -TERM 101 102", calls)

    def test_poweroff_is_forced_when_the_plain_one_fails(self):
        calls = self.go(fail=("systemctl poweroff",))
        self.assertEqual(calls[-2:], ["systemctl poweroff", "systemctl poweroff --force"])

    def test_every_step_hanging_still_powers_off_before_systemd_kills_the_unit(self):
        # Every command runs until its timeout and the k3s processes never exit: the steps run out of time, the
        # data volume still gets its reserved slice, and poweroff runs (twice) before TimeoutStartSec.
        now = [0.0]
        calls, timeouts = [], []

        def hang(cmd, timeout=None):
            calls.append(" ".join(cmd))
            timeouts.append(timeout)
            now[0] += timeout
            raise subprocess.TimeoutExpired(cmd, timeout)

        def sleep(s):
            now[0] += s
        fs = Fs(mounts=[f"/run/k3s/m{i:02d}" for i in range(40)])
        rc = ups.shutdown(runner=hang, fs=fs, kill=lambda sig, pids: None, sleep=sleep, clock=lambda: now[0])
        self.assertEqual(rc, 1)                                   # both poweroffs failed: FailureAction is next
        self.assertEqual(calls[-2:], ["systemctl poweroff", "systemctl poweroff --force"])
        self.assertIn("sync", calls)
        self.assertIn("systemctl stop data.mount", calls)
        self.assertLess(len([c for c in calls if c.startswith("umount ")]), 40)   # k3s ran out of time
        self.assertTrue(all(t >= 1 for t in timeouts))
        limit = int(re.search(r"(?m)^TimeoutStartSec=(\d+)$", unit("onemind-ups-shutdown.service")).group(1))
        self.assertLessEqual(now[0], ups.BUDGET + 2 * ups.POWEROFF_TIMEOUT)
        self.assertLess(now[0], limit - 10)

    def test_the_budget_fits_the_unit_and_a_failure_forces_the_poweroff(self):
        u = unit("onemind-ups-shutdown.service")
        limit = int(re.search(r"(?m)^TimeoutStartSec=(\d+)$", u).group(1))
        self.assertLess(ups.BUDGET + 2 * ups.POWEROFF_TIMEOUT, limit - 10)
        self.assertIn("\nFailureAction=poweroff-force\n", u)

    def test_dry_run_prints_the_plan_and_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "plan.log")
            out = subprocess.run([sys.executable, "-I", SCRIPT, "shutdown", "--dry-run", "--log", log],
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(out.returncode, 0, out.stderr)
            steps = [line.split(":", 1)[0] for line in slurp(log).splitlines()]
            self.assertEqual(sorted(set(steps), key=steps.index), ["apps", "k3s", "data", "poweroff"])


class Image(unittest.TestCase):
    def test_nut_is_in_the_debian_leg(self):
        pkgs = re.sub(r"#.*", "", read("os", "rootfs", "packages", "debian-common.txt")).split()
        self.assertIn("nut-client", pkgs)
        self.assertIn("nut-server", pkgs)

    def test_the_debian_nut_units_are_masked_and_ours_are_enabled(self):
        cf = read("os", "rootfs", "Containerfile")
        masked = " ".join(re.findall(r"systemctl mask ([^;>]*)", cf)).split()
        for u in ("nut-server.service", "nut-monitor.service", "nut-client.service", "ups-monitor.service",
                  "nut-driver-enumerator.service", "nut-driver-enumerator.path", "nut-driver@.service"):
            self.assertIn(u, masked)
        self.assertIn("systemctl enable onemind-ups.service onemind-ups-monitor.service", cf)

    def test_the_server_starts_only_when_a_ups_is_set_up_and_runs_as_nut(self):
        u = unit("onemind-ups.service")
        self.assertIn("ExecCondition=+/usr/lib/onemind/onemind-ups setup", u)
        self.assertIn("Environment=NUT_CONFPATH=/data/onemind/ups", u)
        self.assertIn("User=nut", u)
        self.assertIn("ExecStart=/usr/lib/nut/upsd -F", u)   # /usr/sbin/upsd is a wrapper that reads /etc/nut

    def test_the_monitor_follows_the_server(self):
        u = unit("onemind-ups-monitor.service")
        self.assertIn("BindsTo=onemind-ups.service", u)
        self.assertIn("ExecStart=/usr/lib/nut/upsmon -F", u)

    def test_the_shutdown_unit_never_needs_data(self):
        # Stopping data.mount stops every unit that needs /data: the shutdown must not be one of them.
        u = "\n".join(line for line in unit("onemind-ups-shutdown.service").splitlines() if not line.startswith("#"))
        self.assertNotIn("RequiresMountsFor", u)
        self.assertNotIn("[Install]", u)                                   # only upsmon starts it
        self.assertIn("ExecStart=/usr/lib/onemind/onemind-ups shutdown", u)


# The real programs, as the units call them (Debian's /usr/sbin/upsd and upsmon are wrappers that read /etc/nut).
NUT = {"upsd": "/usr/lib/nut/upsd", "upsmon": "/usr/lib/nut/upsmon", "dummy": "/usr/lib/nut/dummy-ups",
       "upsdrvctl": "/usr/sbin/upsdrvctl"}
HAVE_NUT = all(os.access(p, os.X_OK) for p in NUT.values())


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(HAVE_NUT or os.environ.get("ONEMIND_REQUIRE_NUT") == "1", "needs nut-server and nut-client")
class DummyUpsEndToEnd(unittest.TestCase):
    def test_on_battery_low_battery_starts_the_ordered_shutdown(self):
        self.assertTrue(HAVE_NUT, "ONEMIND_REQUIRE_NUT=1 but NUT is not installed")
        with tempfile.TemporaryDirectory() as d:
            port, dev, log = free_port(), os.path.join(d, "onemind.dev"), os.path.join(d, "plan.log")
            with open(dev, "w") as f:
                f.write("ups.status: OL\nbattery.charge: 100\n")
            cmd = f"{sys.executable} -I {SCRIPT} shutdown --dry-run --log {log}"
            files = ups.render({"driver": "dummy-ups", "port": dev}, "pw-test", port=port, shutdowncmd=cmd,
                               run_as=None, flag=os.path.join(d, "killpower"), pollfreq=1)
            for name, text in files.items():
                path = os.path.join(d, name)
                with open(path, "w") as f:
                    f.write(text)
                os.chmod(path, 0o600)
            env = dict(os.environ, NUT_CONFPATH=d, NUT_STATEPATH=d, NUT_ALTPIDPATH=d)
            procs, logs = [], {}
            try:
                # As the units start it: upsdrvctl puts the driver in the background, then upsd and upsmon run with -F.
                logs["upsdrvctl"] = open(os.path.join(d, "upsdrvctl.out"), "w")
                subprocess.run([NUT["upsdrvctl"], "start"], env=env, stdout=logs["upsdrvctl"], stderr=subprocess.STDOUT,
                               timeout=60, check=True)
                for name, argv in (("upsd", [NUT["upsd"], "-F", "-D"]), ("upsmon", [NUT["upsmon"], "-F", "-D"])):
                    logs[name] = open(os.path.join(d, name + ".out"), "w")
                    procs.append(subprocess.Popen(argv, env=env, stdout=logs[name], stderr=subprocess.STDOUT))
                    time.sleep(2)
                time.sleep(3)
                self.assertFalse(os.path.exists(log), "shut down while the UPS was on mains")
                with open(dev, "w") as f:
                    f.write("ups.status: OB LB\nbattery.charge: 5\n")
                os.utime(dev, (time.time() + 5, time.time() + 5))         # dummy-ups re-reads a file whose mtime moved
                deadline = time.time() + 60
                while time.time() < deadline and not (os.path.exists(log) and "poweroff:" in slurp(log)):
                    time.sleep(1)
            finally:
                for p in reversed(procs):
                    p.terminate()
                    try:
                        p.wait(10)
                    except subprocess.TimeoutExpired:
                        p.kill()
                subprocess.run([NUT["upsdrvctl"], "stop"], env=env, capture_output=True, timeout=30)
                for f in logs.values():
                    f.close()

            def tail(name):
                with open(os.path.join(d, name + ".out")) as f:
                    return f"--- {name}\n" + f.read()[-2000:]
            self.assertTrue(os.path.exists(log), "upsmon never ran the shutdown:\n" + tail("upsdrvctl") + tail("upsd") + tail("upsmon"))
            steps = [line.split(":", 1)[0] for line in slurp(log).splitlines()]
            self.assertEqual(sorted(set(steps), key=steps.index), ["apps", "k3s", "data", "poweroff"])


if __name__ == "__main__":
    unittest.main()
