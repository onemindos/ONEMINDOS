# SPDX-License-Identifier: Apache-2.0
"""UX-07 (#242 part 2): kiosk mode. plan() is a pure function of which programs the image has; the units
and the CLI share one flag file, so a test pins them to each other."""
import importlib.util, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib")
spec = importlib.util.spec_from_file_location("onemind_kiosk", os.path.join(LIB, "onemind", "onemind_kiosk.py"))
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


def read(*p):
    with open(os.path.join(LIB, *p)) as f:
        return f.read()


def have(*names):
    return lambda n: f"/usr/bin/{n}" if n in names else None


class Plan(unittest.TestCase):
    def test_cage_around_chromium_on_the_local_gateway(self):
        argv = k.plan(have("cage", "chromium"))
        self.assertEqual(argv[:3], ["/usr/bin/cage", "--", "/usr/bin/chromium"])
        self.assertEqual(argv[-1], "http://127.0.0.1:8080/")
        self.assertIn("--kiosk", argv)
        self.assertIn("--incognito", argv)             # nothing saved: no token or cookie survives the session
        self.assertIn("--user-data-dir=/run/onemind-kiosk/profile", argv)   # tmpfs, gone at stop

    def test_firefox_is_the_second_choice(self):
        argv = k.plan(have("cage", "firefox-esr"))
        self.assertEqual(argv[2], "/usr/bin/firefox-esr")
        self.assertIn("--private-window", argv)

    def test_without_cage_or_a_browser_the_text_screen_is_the_fallback(self):
        self.assertIsNone(k.plan(have("chromium")))
        self.assertIsNone(k.plan(have("cage")))
        self.assertIsNone(k.plan(have()))

    def test_flag_file_decides(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(k.enabled(root))
            os.makedirs(os.path.join(root, "data", "onemind", "kiosk"))
            open(os.path.join(root, "data", "onemind", "kiosk", "enabled"), "w").close()
            self.assertTrue(k.enabled(root))


class Monitor(unittest.TestCase):
    def sysfs(self, root, statuses):
        for name, status in statuses.items():
            d = os.path.join(root, "sys", "class", "drm", name)
            os.makedirs(d)
            with open(os.path.join(d, "status"), "w") as f:
                f.write(status + "\n")

    def test_a_connected_connector_is_a_monitor(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(k.monitor_connected(root))            # no GPU output at all (a server, QEMU -vga none)
            self.sysfs(root, {"card0-HDMI-A-1": "disconnected", "card0-eDP-1": "unknown"})
            self.assertFalse(k.monitor_connected(root))
            self.sysfs(root, {"card1-DP-2": "connected"})
            self.assertTrue(k.monitor_connected(root))

    def test_no_monitor_runs_the_text_screen_until_one_is_plugged_in(self):
        class Child:
            def __init__(self):
                self.stopped = False
            def poll(self):
                return 0 if self.stopped else None
            def terminate(self):
                self.stopped = True
            def wait(self, timeout=None):
                return 0
        child, spawned, answers = Child(), [], iter([False, False, True])
        rc = k.text_screen_until_monitor("/usr/lib/onemind/onemind_screen.py", connected=lambda: next(answers),
                                         spawn=lambda argv: spawned.append(argv) or child, sleep=lambda s: None)
        self.assertEqual(rc, 1)                       # systemd restarts the unit, which now opens the browser
        self.assertTrue(spawned[0][-1].endswith("onemind_screen.py"))
        self.assertTrue(child.stopped)                # the text screen does not outlive the switch

    def test_the_fallback_line_is_the_one_the_battery_reads(self):
        fb = importlib.util.spec_from_file_location("firstboot", os.path.join(ROOT, "test", "qemu", "firstboot.py"))
        src = open(fb.origin).read()
        self.assertIn(k.NO_MONITOR, src)              # F17 (CRITERIA-FIRSTBOOT.md section 12)


class Environment(unittest.TestCase):
    def test_the_browser_writes_only_to_the_runtime_dir(self):
        env = k.environment({"PATH": "/usr/bin", "HOME": "/nonexistent"})
        self.assertEqual(env["PATH"], "/usr/bin")
        for key in ("HOME", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            self.assertTrue(env[key].startswith("/run/onemind-kiosk"), key)

    def test_chromium_runs_on_wayland_under_cage(self):
        self.assertIn("--ozone-platform=wayland", k.plan(have("cage", "chromium")))


class DefaultOn(unittest.TestCase):
    """Founder decision 2026-11-28: the screen boards ship cage and Chromium, so first boot switches the kiosk on."""
    SCREEN = ("x86_64-efi", "rpi5")

    def words(self, path):
        import re
        with open(path) as f:
            return re.sub(r"#.*", "", f.read()).split()

    def test_screen_boards_ship_the_compositor_and_the_browser(self):
        for b in self.SCREEN:
            w = self.words(os.path.join(ROOT, "os", "boards", b, "packages-debian.txt"))
            self.assertTrue({"cage", "chromium", "libegl-mesa0", "libgl1-mesa-dri"} <= set(w), b)
            with open(os.path.join(ROOT, "os", "boards", b, "post-install.sh")) as f:
                self.assertIn("test -x /usr/bin/cage && test -x /usr/bin/chromium", f.read())

    def test_no_other_board_ships_them(self):
        import glob
        for path in glob.glob(os.path.join(ROOT, "os", "boards", "*", "packages-*.txt")) + \
                glob.glob(os.path.join(ROOT, "os", "rootfs", "packages", "*.txt")):
            if os.path.basename(os.path.dirname(path)) in self.SCREEN and path.endswith("packages-debian.txt"):
                continue
            self.assertFalse({"cage", "chromium"} & set(self.words(path)), path)

    def test_the_compositor_first_boot_looks_for_is_cage(self):
        src = read("onemind", "onemind_firstboot.py")
        self.assertIn('KIOSK_COMPOSITOR = "/usr/bin/cage"', src)
        self.assertIn('j("data", "onemind", "kiosk", "enabled")', src)       # the same flag as the units
        self.assertEqual(k.FLAG, "/data/onemind/kiosk/enabled")

    def test_both_screen_units_wait_for_first_boot(self):
        for unit in ("onemind-kiosk.service", "onemind-screen.service"):
            after = [l for l in read("systemd", "system", unit).splitlines() if l.startswith("After=")]
            self.assertIn("onemind-firstboot.service", " ".join(after), unit)


class Wait(unittest.TestCase):
    def test_waits_until_healthz_answers(self):
        calls = []
        def fetch(u):
            calls.append(u)
            if len(calls) < 3:
                raise OSError("refused")
            return 200
        slept = []
        self.assertTrue(k.wait_for_gateway(fetch=fetch, sleep=slept.append, pause=0.5))
        self.assertEqual(len(calls), 3)
        self.assertEqual(slept, [0.5, 0.5])
        self.assertEqual(calls[0], "http://127.0.0.1:8080/healthz")

    def test_gives_up_after_the_tries(self):
        def refuse(u):
            raise OSError("refused")
        self.assertFalse(k.wait_for_gateway(tries=3, fetch=refuse, sleep=lambda s: None))


class Wiring(unittest.TestCase):
    def test_kiosk_unit_is_owner_enabled_and_replaces_the_text_screen(self):
        unit = read("systemd", "system", "onemind-kiosk.service")
        self.assertIn("ConditionPathExists=" + k.FLAG, unit)
        # Conflicts= on the screen unit makes systemd drop both start jobs at boot (blank monitor); the two
        # ConditionPathExists lines already keep them exclusive. Only the getty may be conflicted.
        conflicts = [l for l in unit.splitlines() if l.startswith("Conflicts=")]
        self.assertEqual(conflicts, ["Conflicts=getty@tty1.service"])
        self.assertIn("ExecStart=/usr/lib/onemind/onemind-kiosk", unit)
        self.assertEqual(os.readlink(os.path.join(LIB, "systemd", "system", "multi-user.target.wants",
                                                  "onemind-kiosk.service")), "../onemind-kiosk.service")
        self.assertTrue(os.access(os.path.join(LIB, "onemind", "onemind-kiosk"), os.X_OK))

    def test_the_browser_never_runs_as_root(self):
        unit = read("systemd", "system", "onemind-kiosk.service")
        self.assertIn("User=onemind-kiosk", unit)        # Chromium refuses root; cage loops forever otherwise
        self.assertIn("ProtectSystem=strict", unit)      # also covers the text-screen fallback
        self.assertIn("onemind-kiosk", read("sysusers.d", "onemind-kiosk.conf"))
        self.assertNotIn("--no-sandbox", read("onemind", "onemind_kiosk.py"))

    def test_switching_over_the_api_reaches_the_screen(self):
        path = read("systemd", "system", "onemind-kiosk.path")
        self.assertIn("PathChanged=" + os.path.dirname(k.FLAG), path)
        self.assertIn("restart onemind-screen.service onemind-kiosk.service", read("systemd", "system", "onemind-kiosk-apply.service"))
        self.assertEqual(os.readlink(os.path.join(LIB, "systemd", "system", "multi-user.target.wants",
                                                  "onemind-kiosk.path")), "../onemind-kiosk.path")
        gw = read("systemd", "system", "onemind-gateway.service")    # the gateway may write only the flag dir
        self.assertIn("/data/onemind/kiosk", gw)

    def test_text_screen_steps_aside_only_when_kiosk_is_on(self):
        self.assertIn("ConditionPathExists=!" + k.FLAG, read("systemd", "system", "onemind-screen.service"))

    def test_the_kiosk_never_touches_the_owner_token(self):
        self.assertNotRegex(read("onemind", "onemind_kiosk.py").replace("owner token", ""), r"owner-token|secrets|join-token|Authorization")


if __name__ == "__main__":
    unittest.main()
