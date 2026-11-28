# SPDX-License-Identifier: Apache-2.0
"""P-11 keyboard layout: the wiring that no single package test sees. The host kind, the gateway's action type, the
kiosk, the image check and the QEMU check F32 must all name the same things (the behaviour of each part is tested in
internal/keymap, internal/host, core/tests/test_keyboard.py, cmd/onemind/cli/keyboard_test.go, dashboard
SettingsRegion.test.tsx and test_kiosk.py)."""
import hashlib, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


class Wiring(unittest.TestCase):
    def test_the_kind_is_known_to_the_host_and_to_the_gateway(self):
        go = rd("internal", "host", "host.go")
        self.assertIn('KindSetKeymap      = "set-keymap"', go)
        self.assertRegex(go, r"var Kinds = \[\]string\{[^}]*KindSetKeymap\}")  # listed in GET /v1/status
        self.assertIn('"system.set_keymap": "set-keymap"', rd("core", "onemind_core", "hostlink.py"))
        self.assertIn('ACTION = "system.set_keymap"', rd("core", "onemind_core", "routers", "keyboard.py"))

    def test_the_host_and_the_gateway_check_layout_names_the_same_way(self):
        go, py = rd("internal", "keymap", "keymap.go"), rd("core", "onemind_core", "hostkeyboard.py")
        for pat in (r"[A-Za-z0-9_]{1,24}", r"[A-Za-z0-9_-]{1,32}", r"[A-Za-z0-9_,:+-]"):
            self.assertIn(pat, go)
            self.assertIn(pat, py)
        self.assertIn(r"[A-Za-z0-9_,:+-]", rd("os", "rootfs", "layers", "base", "usr", "lib", "onemind", "onemind-console-keyboard"))
        self.assertIn(r"[^A-Za-z0-9_,:+-]", rd("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind_kiosk.py"))

    def test_the_host_reads_and_writes_the_file_the_console_unit_and_the_kiosk_read(self):
        self.assertIn('DefaultPath    = "/data/onemind/console/keyboard"', rd("internal", "keymap", "keymap.go"))
        self.assertIn('KEYBOARD = "/data/onemind/console/keyboard"', rd("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind_kiosk.py"))
        self.assertIn("/data/onemind/console/keyboard", rd("os", "rootfs", "layers", "base", "usr", "lib", "onemind", "onemind-console-keyboard"))
        self.assertIn("ReadWritePaths=/data /boot/efi", rd("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-host.service"))

    def test_the_units_the_host_restarts_are_restartable_cards_in_the_registry(self):
        reg = rd("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "services.yaml")
        for unit in ("onemind-console-keyboard.service", "onemind-kiosk.service"):
            self.assertRegex(reg, r"unit: " + re.escape(unit) + r"[^\n]*restartable: true")
        go = rd("internal", "host", "keymap.go")
        self.assertIn('ConsoleUnit = "onemind-console-keyboard.service"', go)
        self.assertIn('KioskUnit   = "onemind-kiosk.service"', go)

    def test_the_image_has_the_layout_list_the_picker_offers(self):
        c = rd("os", "rootfs", "Containerfile")
        self.assertIn("test -f /usr/share/X11/xkb/rules/base.lst", c)  # xkb-data, from keyboard-configuration
        self.assertIn("/usr/share/X11/xkb/rules/base.lst", rd("internal", "keymap", "keymap.go"))

    def test_the_host_is_wired_in_the_service_binary(self):
        self.assertIn("Keymap: &host.KeymapStore{Units: units}", re.sub(r"\s+", " ", rd("cmd", "onemindd", "host.go")))

    def test_the_cli_and_the_dashboard_use_the_same_route(self):
        self.assertIn('"/v1/system/keyboard"', rd("sdk", "go", "keyboard.go"))
        self.assertIn("keyboardCommands,", rd("cmd", "onemind", "cli", "root.go"))
        self.assertIn("/v1/system/keyboard", rd("dashboard", "src", "pages", "SettingsRegion.tsx"))
        self.assertIn("id: 'region'", rd("dashboard", "src", "screens", "settings-pages", "region.ts"))
        self.assertIn("{ id: 'region', label: 'Language & region'", rd("ui", "src", "settings", "SettingsLayout.tsx"))


class F32(unittest.TestCase):
    CRIT = rd("test", "qemu", "CRITERIA-FIRSTBOOT.md")
    FB = rd("test", "qemu", "firstboot.py")

    def test_f23_is_preregistered_with_a_recorded_hash(self):
        h = hashlib.sha256(self.CRIT.encode()).hexdigest()
        lines = [l.split() for l in rd("test", "qemu", "PREREGISTRATION.sha256").splitlines() if "CRITERIA-FIRSTBOOT.md" in l]
        self.assertIn(h, [l[0] for l in lines])
        self.assertIn("| F32 |", self.CRIT)

    def test_f23_runs_after_f21_before_the_reboot_and_is_judged_at_the_end(self):
        i = self.FB.index
        self.assertLess(i("pre30 = f30_before(vm)"), i("pre32 = f32_before(vm)"))
        self.assertLess(i("pre32 = f32_before(vm)"), i('vm.mark("F3 reboot keeps state")'))
        self.assertLess(i("mid32 = f32_state(vm)"), i('vm.mark("F4 A/B update keeps /data")'))
        self.assertLess(i('vm.mark("F4 A/B update keeps /data")'), i("final32 = f32_state(vm)"))
        self.assertLess(i("final32 = f32_state(vm)"), i("f32_record(pre32, mid32, final32)"))
        self.assertIn('record("F32"', self.FB)

    def test_f23_sends_the_host_contract_and_not_a_shortcut(self):
        body = self.FB[self.FB.index("def f32_before("):self.FB.index("def f32_state(")]
        self.assertIn('"kind": "set-keymap"', body)
        self.assertIn("unknown_layout", body)
        self.assertNotIn("sed -i", body)  # the file is changed by the host service, never by the test
        self.assertIn("--unix-socket /run/onemind/host.sock", self.FB)


if __name__ == "__main__":
    unittest.main()
