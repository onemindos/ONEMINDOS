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


class Keyboard(unittest.TestCase):
    """P-11: the kiosk screen starts with the owner's layout, read from the file the console unit also reads."""

    def file(self, text):
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = os.path.join(d.name, "keyboard")
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_the_layout_and_variant_become_xkb_variables_for_cage(self):
        env = k.keyboard_env(self.file('XKBMODEL="pc105"\nXKBLAYOUT="de"\nXKBVARIANT="nodeadkeys"\nXKBOPTIONS=""\n'))
        self.assertEqual(env, {"XKB_DEFAULT_MODEL": "pc105", "XKB_DEFAULT_LAYOUT": "de", "XKB_DEFAULT_VARIANT": "nodeadkeys"})

    def test_no_file_means_no_variables_so_the_compositor_keeps_its_default(self):
        self.assertEqual(k.keyboard_env("/nonexistent/keyboard"), {})

    def test_a_file_with_odd_characters_is_refused_whole_and_never_run(self):
        self.assertEqual(k.keyboard_env(self.file('XKBMODEL="pc105"\nXKBLAYOUT="de$(reboot)"\n')), {})
        self.assertEqual(k.keyboard_env(self.file('XKBLAYOUT="de"\nXKBOPTIONS="ctrl:nocaps;x"\n')), {})

    def test_last_line_wins_and_unknown_keys_are_ignored(self):
        env = k.keyboard_env(self.file('XKBLAYOUT=us\nBACKSPACE="guess"\nXKBLAYOUT="fr"\n'))
        self.assertEqual(env, {"XKB_DEFAULT_LAYOUT": "fr"})

    def test_main_hands_the_variables_to_the_compositor(self):
        src = read("onemind", "onemind_kiosk.py")
        self.assertIn("os.environ.update(keyboard_env())", src)
        self.assertLess(src.index("os.environ.update(keyboard_env())"), src.index("os.execv(argv[0], argv)"))
