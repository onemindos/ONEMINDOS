# SPDX-License-Identifier: Apache-2.0
"""The first-boot battery's F0 and F10 verdict logic (test/qemu/firstboot.py), fed canned guest output.

No VM: a fake `vm.run` returns what the booted image prints, so these tests pin how F0 and F10 read it.
F0 must take the NATS version from os/versions.lock.yaml (the pin the image build downloads), not a
hard-coded string, and F10 must accept the rescue console started at runtime but not enabled.
"""
import contextlib, importlib.util, io, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_firstboot():
    spec = importlib.util.spec_from_file_location("firstboot", os.path.join(ROOT, "test", "qemu", "firstboot.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeVM:
    def __init__(self, out):
        self.out = out

    def run(self, cmd, timeout=None):
        return 0, self.out


def quiet(fn, *args):
    """Run a check without its ===> line on the test output (the verdict is read from RESULTS)."""
    with contextlib.redirect_stdout(io.StringIO()):
        fn(*args)


class F0NatsVersion(unittest.TestCase):
    def setUp(self):
        import yaml
        self.fb = load_firstboot()
        self.fb.RESULTS.clear()
        nats = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))["onemind_layer"]["nats_server"]
        self.version, self.sha = str(nats["version"]), nats["amd64"]["binary"]

    def guest(self, nats_line):
        units = "".join(f"UNIT {u} {'enabled' if u == 'onemind-firstboot' else 'disabled'}\n" for u in self.fb.UNITS)
        return (f"onemindd v0.0.0\nonemind v0.0.0\n{nats_line}\r\nNATSSHA={self.sha}\nGATEWAY-IMPORT ok\n"
                f"DASH ok\nTUF ok\n{units}")

    def test_pinned_version_passes(self):
        quiet(self.fb.f0, FakeVM(self.guest(f"nats-server: {self.version}")), "x86_64-efi")
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "PASS", self.fb.RESULTS[-1]["detail"])

    def test_other_version_fails(self):
        quiet(self.fb.f0, FakeVM(self.guest("nats-server: v0.0.1")), "x86_64-efi")
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "FAIL")
        self.assertIn("nats_server_runs=False", self.fb.RESULTS[-1]["detail"])

    def test_version_prefix_is_not_enough(self):
        # v2.15.3 must not match v2.15.30: the version is anchored at the end of the line.
        quiet(self.fb.f0, FakeVM(self.guest(f"nats-server: {self.version}0")), "x86_64-efi")
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "FAIL")

    def test_no_hard_coded_nats_version(self):
        src = open(os.path.join(ROOT, "test", "qemu", "firstboot.py")).read()
        self.assertNotIn(r"nats-server: v2\.", src)


class F10RescueRuntimeStarted(unittest.TestCase):
    def setUp(self):
        self.fb = load_firstboot()
        self.fb.RESULTS.clear()

    def run_f10(self, enabled):
        out = (f"ENABLED={enabled}\nACTIVE=active\nK3S=inactive\nNOAUTH=401\nWITH=200\nJSON=200\n"
               "JSONOK=yes\nAFTER=active\n")
        quiet(self.fb.f10, FakeVM(out), "0" * 64)
        return self.fb.RESULTS[-1]

    def test_not_enabled_but_active_passes(self):
        r = self.run_f10("disabled")
        self.assertEqual(r["verdict"], "PASS", r["detail"])

    def test_enabled_in_etc_fails(self):
        # The image never enables it (F0); an enabled unit means the image changed and F0/F10 disagree.
        self.assertEqual(self.run_f10("enabled")["verdict"], "FAIL")

    def test_missing_or_masked_unit_fails(self):
        for state in ("not-found", "masked", ""):
            with self.subTest(state=state):
                self.assertEqual(self.run_f10(state)["verdict"], "FAIL")


GOOD_F15 = (
    "PKG=libpam-systemd openssh-server sudo\nADMIN=admin:x:1000:1000:OneMind admin:/home/admin:/bin/bash\n"
    "SHADOWLINE=0\nEXTRASH=0\nSLOTKEYS0=0\nSSH0=inactive\nLISTEN0=0\nNFT0=0\n"
    "ADDRC=0\nSSH1=active\nLISTEN1=2\nNFT1=1\nHK=/data/onemind/ssh/ssh_host_ed25519_key\nSLOTKEYS1=0\nKEYLOGIN=admin\n"
    "PWRC=0\nPWRC2=255\nPWOUT=admin@127.0.0.1: Permission denied (publickey).\n"
    "permitrootlogin no\npasswordauthentication no\nkbdinteractiveauthentication no\nauthenticationmethods publickey\n"
    "allowusers admin\nTTY2=enabled\nF15LOGIN good_who=admin good_sudo=0 bad_denied=True bad_shell=False\n"
    "KIOSK=active\nSESS=1\n")


class F15OwnerShell(unittest.TestCase):
    """F15 (CRITERIA-FIRSTBOOT.md section 11): every sub-check must be able to fail on its own."""

    def setUp(self):
        self.fb = load_firstboot()

    def verdict(self, out):
        return self.fb.f15_judge(out)

    def test_good_output_passes_every_check(self):
        c = self.verdict(GOOD_F15)
        self.assertTrue(all(c.values()), c)

    def mutate(self, old, new):
        self.assertIn(old, GOOD_F15)
        return self.verdict(GOOD_F15.replace(old, new))

    def test_each_failure_is_caught(self):
        for old, new, key in (
            ("SHADOWLINE=0", "SHADOWLINE=1", "no_baked_password"),            # a hash baked into /etc/shadow
            ("EXTRASH=0", "EXTRASH=1", "no_baked_password"),
            ("SLOTKEYS0=0", "SLOTKEYS0=2", "no_slot_hostkeys"),               # shared host keys in the image
            ("SSH0=inactive", "SSH0=active", "no_key_sshd_inactive"),         # sshd up with no owner key
            ("LISTEN0=0", "LISTEN0=1", "no_key_nothing_listens"),
            ("SSH1=active", "SSH1=inactive", "key_starts_sshd"),              # the first key did not start sshd
            ("NFT1=1", "NFT1=0", "firewall_opens_22"),
            ("KEYLOGIN=admin", "KEYLOGIN=Permission denied", "key_login"),
            ("PWRC2=255", "PWRC2=0", "password_refused"),                     # password login accepted
            ("Permission denied (publickey)", "Welcome", "password_refused"),
            ("passwordauthentication no", "passwordauthentication yes", "sshd_config"),
            ("allowusers admin", "allowusers admin root", "sshd_config"),
            ("TTY2=enabled", "TTY2=disabled", "tty2_enabled"),
            ("good_sudo=0", "good_sudo=None", "tty2_login"),
            ("good_who=admin", "good_who=None", "tty2_login"),
            ("bad_denied=True", "bad_denied=False", "tty2_wrong_password_refused"),
            ("bad_shell=False", "bad_shell=True", "tty2_wrong_password_refused"),  # a wrong password reached a shell
            ("KIOSK=active", "KIOSK=failed", "kiosk_starts"),
            ("SESS=1", "SESS=0", "kiosk_starts"),                             # no logind session: libpam-systemd missing
            ("PKG=libpam-systemd openssh-server sudo", "PKG=openssh-server sudo", "packages"),
            ("/bin/bash", "/usr/sbin/nologin", "admin_uid1000_bash"),
        ):
            with self.subTest(change=new):
                self.assertFalse(self.mutate(old, new)[key], key)

    def test_f15_never_prints_the_password_or_key(self):
        src = open(os.path.join(ROOT, "test", "qemu", "firstboot.py")).read()
        body = src[src.index("def f15("):src.index("def main(")]
        self.assertNotIn("echo $F15_PW", body)
        self.assertNotIn("cat /run/f15/k\n", body)
        self.assertIn("F15_PW=$(head -c 18 /dev/urandom", body)         # generated in the guest, never baked


if __name__ == "__main__":
    unittest.main()


class F17KioskByDefault(unittest.TestCase):
    """F17/F17r (CRITERIA-FIRSTBOOT.md section 12): kiosk on by default on a screen board, the text screen inside it
    with no monitor, the owner's off kept after a reboot; none of it on a no-screen board."""

    GOOD = ("PKGS=cage chromium \nBINS=yes\nFLAG=yes\nDIROWNER=onemind\nMARKER=yes\nKIOSK=active\nSCREEN=inactive\n"
            "TEXTPROC=1\nCHROMIUM=0\nKLOG kiosk: no monitor is connected; showing the text screen until one is\n")

    def setUp(self):
        self.fb = load_firstboot()

    def test_good_output_passes_every_check(self):
        c = self.fb.f17_judge(self.GOOD, "x86_64-efi")
        self.assertTrue(all(c.values()), c)

    def test_each_failure_is_caught(self):
        for old, new, check in [("PKGS=cage chromium", "PKGS=cage", "image_packages"),
                                ("FLAG=yes", "FLAG=no", "default_on"),
                                ("DIROWNER=onemind", "DIROWNER=root", "default_on"),
                                ("MARKER=yes", "MARKER=no", "default_on"),
                                ("KIOSK=active", "KIOSK=failed", "kiosk_active"),
                                ("SCREEN=inactive", "SCREEN=active", "text_unit_skipped"),
                                ("TEXTPROC=1", "TEXTPROC=0", "no_monitor_fallback"),
                                ("CHROMIUM=0", "CHROMIUM=1", "no_monitor_fallback"),
                                ("KLOG kiosk: no monitor", "KLOG kiosk: cage", "no_monitor_fallback")]:
            c = self.fb.f17_judge(self.GOOD.replace(old, new), "x86_64-efi")
            self.assertFalse(c[check], (old, new))
        leak = self.GOOD + "KLOG token " + "ab" * 32 + "\n"
        self.assertFalse(self.fb.f17_judge(leak, "x86_64-efi")["nothing_secret"])

    def test_no_screen_board(self):
        good = "PKGS=\nFLAG=no\nSCREEN=active\n"
        self.assertTrue(all(self.fb.f17_judge(good, "arm64-efi").values()))
        self.assertFalse(all(self.fb.f17_judge(good.replace("PKGS=", "PKGS=cage"), "arm64-efi").values()))
        self.assertFalse(all(self.fb.f17_judge(good.replace("FLAG=no", "FLAG=yes"), "arm64-efi").values()))

    def test_after_the_reboot_the_owners_off_is_kept(self):
        good = "FLAG=no\nSCREEN=active\nKIOSK=inactive\n"
        self.assertTrue(all(self.fb.f17_judge(good, "x86_64-efi", after_reboot=True).values()))
        self.assertFalse(all(self.fb.f17_judge(good.replace("FLAG=no", "FLAG=yes"), "x86_64-efi", True).values()))
        self.assertFalse(all(self.fb.f17_judge(good.replace("KIOSK=inactive", "KIOSK=active"), "x86_64-efi", True).values()))

    def test_f17_runs_before_f15_removes_the_flag(self):
        src = open(os.path.join(ROOT, "test", "qemu", "firstboot.py")).read()
        self.assertLess(src.index("f17(vm, a.board)"), src.index("f15(vm)\n"))
        self.assertIn('f17(vm, a.board, "F17r", after_reboot=True)', src)
