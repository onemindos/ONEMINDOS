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


class Wiring(unittest.TestCase):
    def test_kiosk_unit_is_owner_enabled_and_replaces_the_text_screen(self):
        unit = read("systemd", "system", "onemind-kiosk.service")
        self.assertIn("ConditionPathExists=" + k.FLAG, unit)
        self.assertIn("Conflicts=getty@tty1.service onemind-screen.service", unit)
        self.assertIn("ExecStart=/usr/lib/onemind/onemind-kiosk", unit)
        self.assertEqual(os.readlink(os.path.join(LIB, "systemd", "system", "multi-user.target.wants",
                                                  "onemind-kiosk.service")), "../onemind-kiosk.service")
        self.assertTrue(os.access(os.path.join(LIB, "onemind", "onemind-kiosk"), os.X_OK))

    def test_text_screen_steps_aside_only_when_kiosk_is_on(self):
        self.assertIn("ConditionPathExists=!" + k.FLAG, read("systemd", "system", "onemind-screen.service"))

    def test_the_kiosk_never_touches_the_owner_token(self):
        self.assertNotRegex(read("onemind", "onemind_kiosk.py").replace("owner token", ""), r"owner-token|secrets|join-token|Authorization")


if __name__ == "__main__":
    unittest.main()
