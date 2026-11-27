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


GOOD_F23 = (
    "F23 noauth=401\nF23 get=200\nF23 available=True\nF23 password_login=False\nF23 port=22\nF23 user=admin\n"
    "F23 b_code=202\nF23 b_state=awaiting_approval\nF23 b_type=ssh.key.add\nF23 b_pre_login=Permission denied (publickey).\n"
    "F23 c_state=succeeded\nF23 c_login=admin\nF23 c_listed=True\n"
    "F23 d_add_code=202\nF23 d_add_state=succeeded\nF23 d_k2_login=admin\n"
    "F23 d_del_code=202\nF23 d_del_state0=awaiting_approval\nF23 d_k2_before_approval=admin\nF23 d_del_state=succeeded\n"
    "F23 d_k2_after_rc=255\nF23 d_k2_after_denied=True\nF23 d_k1_still=admin\nF23 d_k2_listed=False\nF23 d_k1_listed=True\n"
    "F23 e_limit_first=True\n"
    "F23 f_code=202\nF23 f_state0=awaiting_approval\nF23 f_listen_before=2\nF23 f_state=succeeded\nF23 f_active=inactive\n"
    "F23 f_listen=0\nF23 f_nft=0\nF23 f_flag=True\nF23 f_login_rc=255\nF23 f_restart_active=inactive\n"
    "F23 g_state=succeeded\nF23 g_active=active\nF23 g_listen=2\nF23 g_flag=False\nF23 g_login=admin\n"
    "F23 e_limit_after_on=True\nF23 e_limit_after_fw=True\nF23 e_fw_login=admin\n"
    "F23 i_code=422\nF23 i_filed=0\n")


class F23SshKeysAndSwitch(unittest.TestCase):
    """F23 (CRITERIA-FIRSTBOOT.md section 16): every sub-check must be able to fail on its own."""

    def setUp(self):
        self.fb = load_firstboot()
        self.fb.RESULTS.clear()

    def mutate(self, old, new):
        self.assertIn(old, GOOD_F23)
        return self.fb.f23_judge(GOOD_F23.replace(old, new))

    def test_good_output_passes_every_check(self):
        c = self.fb.f23_judge(GOOD_F23)
        self.assertTrue(all(c.values()), c)

    def test_each_failure_is_caught(self):
        for old, new, key in (
            ("noauth=401", "noauth=200", "reads"),                                  # the API answered without a token
            ("password_login=False", "password_login=True", "reads"),
            ("b_state=awaiting_approval", "b_state=succeeded", "request_waits"),    # a request ran before approval
            ("b_pre_login=Permission denied (publickey).", "b_pre_login=admin", "request_waits"),
            ("c_login=admin", "c_login=Permission denied", "approval_adds"),
            ("c_listed=True", "c_listed=False", "approval_adds"),
            ("d_k2_login=admin", "d_k2_login=", "second_key"),
            ("d_k2_before_approval=admin", "d_k2_before_approval=", "removal_waits"),  # removed before approval
            ("d_k2_after_rc=255", "d_k2_after_rc=0", "removal_refuses"),            # the removed key still logs in
            ("d_k2_after_denied=True", "d_k2_after_denied=False", "removal_refuses"),
            ("d_k1_still=admin", "d_k1_still=", "removal_refuses"),                 # removal took the other key too
            ("d_k2_listed=False", "d_k2_listed=True", "removal_refuses"),
            ("e_limit_first=True", "e_limit_first=False", "rate_limit_rule"),
            ("e_limit_after_on=True", "e_limit_after_on=False", "rate_limit_rule"),   # lost on the second start of sshd
            ("e_limit_after_fw=True", "e_limit_after_fw=False", "rate_limit_rule"),   # lost after a firewall restart
            ("e_fw_login=admin", "e_fw_login=", "rate_limit_rule"),
            ("f_listen_before=2", "f_listen_before=0", "off_waits"),
            ("f_listen=0", "f_listen=1", "off_closes_port"),                        # the port is still open
            ("f_active=inactive", "f_active=active", "off_closes_port"),
            ("f_nft=0", "f_nft=1", "off_closes_port"),
            ("f_flag=True", "f_flag=False", "off_closes_port"),
            ("f_restart_active=inactive", "f_restart_active=active", "off_holds"),  # systemctl start undid the switch
            ("g_active=active", "g_active=inactive", "on_opens_it"),
            ("g_flag=False", "g_flag=True", "on_opens_it"),
            ("g_login=admin", "g_login=", "on_opens_it"),
            ("i_code=422", "i_code=202", "bad_key_refused"),
            ("i_filed=0", "i_filed=1", "bad_key_refused"),
        ):
            with self.subTest(change=new):
                self.assertFalse(self.mutate(old, new)[key], key)

    def test_missing_output_is_a_failure_not_a_pass(self):
        self.assertFalse(any(self.fb.f23_judge("").values()))

    def test_f23_runs_after_f15_and_prints_no_secret(self):
        src = open(os.path.join(ROOT, "test", "qemu", "firstboot.py")).read()
        main = src[src.index("def main("):]
        self.assertLess(main.index("f15(vm)"), main.index("f23(vm, token)"))
        script = src[src.index("F23_PY = "):src.index("def f23_judge(")]
        self.assertNotIn("print(TOKEN", script)
        self.assertNotRegex(script, r"out\([^)]*open\(K[12]\)(?!\.pub)")      # never the private key
        self.assertIn("ssh-keygen -q -t ed25519 -N ''", script)                   # keys are made in the guest


if __name__ == "__main__":
    unittest.main()
