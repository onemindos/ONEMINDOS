# SPDX-License-Identifier: Apache-2.0
"""IMG-LUKS-01: /data as LUKS2, first-boot encryption, TPM2 + recovery-key unlock. data_encrypt.py decides everything;
these tests run it with a fake command runner and check the command sequence, the secrets handling and the
'never touch data that is already there' rules. The real boot (swtpm) is test/qemu/dataenc.py, run in CI."""
import copy, hashlib, importlib.util, os, re, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib")
spec = importlib.util.spec_from_file_location("data_encrypt", os.path.join(BASE, "onemind", "data_encrypt.py"))
de = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de)
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))

RECOVERY = "cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd"


def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


class FakeRunner:
    """Records every command; `fail` is a substring of a command that should fail."""
    def __init__(self, fail=None, enroll_out=None):
        self.calls, self.fail = [], fail
        self.enroll_out = f"A secret recovery key has been generated:\n\n    {RECOVERY}\n" if enroll_out is None else enroll_out

    def __call__(self, cmd, input=None, check=True):
        line = " ".join(cmd)
        self.calls.append((cmd, input))
        rc = 1 if self.fail and self.fail in line else 0
        out = self.enroll_out if "--recovery-key" in line and rc == 0 else ""
        if rc and check:
            raise subprocess.CalledProcessError(rc, cmd, output="", stderr="boom")
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="")

    def lines(self):
        return [" ".join(c) for c, _ in self.calls]


class Classify(unittest.TestCase):
    def test_only_a_zero_head_with_no_signature_is_blank(self):
        self.assertEqual(de.classify("", True), "blank")
        self.assertEqual(de.classify("", False), "unknown")          # random or foreign data: never formatted
        self.assertEqual(de.classify("xfs", True), "unknown")
        self.assertEqual(de.classify("btrfs", False), "unknown")

    def test_ext4_and_luks_are_recognised(self):
        self.assertEqual(de.classify("ext4", False), "ext4")
        self.assertEqual(de.classify("crypto_LUKS", False), "luks")

    def test_recovery_key_is_found_in_cryptenroll_output(self):
        self.assertEqual(de.parse_recovery_key(f"noise\n  {RECOVERY}\nmore"), RECOVERY)
        self.assertIsNone(de.parse_recovery_key("no key here"))
        self.assertIsNone(de.parse_recovery_key("aaaaaaaa-aaaaaaaa"))  # 'a' is not a modhex letter; too short anyway


class FirstBoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(de, "KEYFILE", os.path.join(self.tmp, "vol.key"))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def go(self, tpm, **kw):
        r = FakeRunner(**kw)
        return r, de.first_boot_encrypt("/dev/vda7", tpm, r, rand=lambda n: b"\x07" * n)

    def test_order_and_flags(self):
        r, res = self.go(True)
        L = r.lines()
        self.assertEqual([next(w for w in ("luksFormat", "open", "mkfs.ext4", "--recovery-key", "--tpm2-device=auto", "luksKillSlot") if w in l)
                          for l in L], ["luksFormat", "open", "mkfs.ext4", "--recovery-key", "--tpm2-device=auto", "luksKillSlot"])
        fmt = L[0]
        self.assertIn("--type luks2", fmt)
        self.assertIn("aes-xts-plain64", fmt)
        self.assertTrue(fmt.endswith("/dev/vda7"))
        self.assertIn("--tpm2-pcrs=7", L[4])
        self.assertIn("mkfs.ext4 -q -L onemind-data", L[2])
        self.assertIn("/dev/mapper/onemind-data", L[2])
        self.assertEqual(res, {"recovery_key": RECOVERY, "tpm2": True})

    def test_no_tpm_means_no_tpm_enrolment(self):
        r, res = self.go(False)
        self.assertFalse(any("--tpm2" in l for l in r.lines()))
        self.assertEqual(res["tpm2"], False)
        self.assertEqual(res["recovery_key"], RECOVERY)

    def test_a_tpm_that_refuses_is_not_fatal(self):
        r, res = self.go(True, fail="--tpm2-device")
        self.assertEqual(res["tpm2"], False)
        self.assertEqual(res["recovery_key"], RECOVERY)

    def test_the_volume_key_is_in_a_0600_file_removed_afterwards_and_never_on_a_command_line(self):
        seen = {}
        class Spy(FakeRunner):
            def __call__(s, cmd, input=None, check=True):
                if "luksFormat" in cmd:
                    seen["mode"] = oct(os.stat(de.KEYFILE).st_mode & 0o777)
                    seen["bytes"] = open(de.KEYFILE, "rb").read()
                return super().__call__(cmd, input, check)
        r = Spy()
        de.first_boot_encrypt("/dev/vda7", True, r, rand=lambda n: b"\x07" * n)
        self.assertEqual(seen["mode"], "0o600")
        self.assertEqual(seen["bytes"], b"\x07" * 64)
        self.assertFalse(os.path.exists(de.KEYFILE))
        for line in r.lines():
            self.assertNotIn(RECOVERY, line)
            self.assertNotIn("0707", line)

    def test_a_failure_wipes_the_partition_back_to_blank_and_removes_the_key(self):
        for step in ("luksFormat", "mkfs.ext4", "--recovery-key"):
            with self.subTest(step=step):
                r = FakeRunner(fail=step)
                with self.assertRaises(subprocess.CalledProcessError if step != "--recovery-key" else subprocess.CalledProcessError):
                    de.first_boot_encrypt("/dev/vda7", True, r)
                self.assertTrue(r.lines()[-1].startswith("wipefs --all --force /dev/vda7"), r.lines())
                self.assertFalse(os.path.exists(de.KEYFILE))
                if step != "luksFormat":
                    self.assertTrue(any(l.startswith("cryptsetup close onemind-data") for l in r.lines()))

    def test_no_recovery_key_in_the_output_is_a_failure_not_a_silent_success(self):
        r = FakeRunner(enroll_out="nothing useful")
        with self.assertRaises(RuntimeError):
            de.first_boot_encrypt("/dev/vda7", True, r)
        self.assertTrue(r.lines()[-1].startswith("wipefs"))


class Unlock(unittest.TestCase):
    def test_tpm_first_and_headless(self):
        r = FakeRunner()
        self.assertEqual(de.unlock("/dev/vda7", True, r), "tpm2")
        self.assertEqual(len(r.calls), 1)
        self.assertIn("tpm2-device=auto,headless=true", r.lines()[0])

    def test_a_tpm_that_does_not_match_falls_back_to_asking(self):
        r = FakeRunner(fail="tpm2-device")
        self.assertEqual(de.unlock("/dev/vda7", True, r), "recovery-key")
        self.assertIn("luks,tries=3", r.lines()[1])
        self.assertNotIn("headless", r.lines()[1])           # headless would forbid the prompt

    def test_no_tpm_goes_straight_to_the_prompt(self):
        r = FakeRunner()
        self.assertEqual(de.unlock("/dev/vda7", False, r), "recovery-key")
        self.assertEqual(len(r.calls), 1)

    def test_three_wrong_keys_leave_it_locked(self):
        self.assertIsNone(de.unlock("/dev/vda7", False, FakeRunner(fail="tries=3")))


class Main(unittest.TestCase):
    """main() with the disk faked: what it finds decides what it does."""
    def run_main(self, sig, zero, tpm=False):
        r = FakeRunner()
        exists = lambda p: {"/dev/tpmrm0": tpm}.get(p, False)
        with mock.patch.object(de, "wait_for", return_value=True), \
             mock.patch.object(de.os.path, "realpath", return_value="/dev/vda7"), \
             mock.patch.object(de.os.path, "exists", side_effect=exists), \
             mock.patch.object(de, "signature", return_value=sig), \
             mock.patch.object(de, "head_is_zero", return_value=zero), \
             mock.patch.object(de, "say"), mock.patch.object(de, "write_state") as ws, \
             mock.patch.object(de, "keep_recovery_key") as keep, \
             mock.patch.object(de, "first_boot_encrypt", return_value={"recovery_key": RECOVERY, "tpm2": tpm}) as fb, \
             mock.patch.object(de, "unlock", return_value="tpm2" if tpm else None) as ul:
            rc = de.main(r)
        return rc, r, ws, keep, fb, ul

    def test_ext4_boxes_are_left_alone(self):
        rc, r, ws, keep, fb, ul = self.run_main("ext4", False)
        self.assertEqual(rc, 0)
        fb.assert_not_called(); ul.assert_not_called(); keep.assert_not_called()
        self.assertEqual(ws.call_args.kwargs["state"], "plain")

    def test_unknown_data_is_never_formatted(self):
        for sig, zero in (("", False), ("xfs", True), ("btrfs", False)):
            rc, r, ws, keep, fb, ul = self.run_main(sig, zero)
            fb.assert_not_called(); ul.assert_not_called()
            self.assertEqual(ws.call_args.kwargs["state"], "unknown")

    def test_blank_is_encrypted_and_the_key_is_kept_in_ram(self):
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=True)
        fb.assert_called_once()
        keep.assert_called_once_with(RECOVERY)
        self.assertEqual(ws.call_args.kwargs["state"], "encrypted")

    def test_luks_is_unlocked_and_a_failure_is_reported_not_raised(self):
        rc, r, ws, keep, fb, ul = self.run_main("crypto_LUKS", False, tpm=True)
        ul.assert_called_once(); fb.assert_not_called()
        rc, r, ws, keep, fb, ul = self.run_main("crypto_LUKS", False, tpm=False)
        self.assertEqual(rc, 0)
        self.assertEqual(ws.call_args.kwargs["state"], "locked")

    def test_safe_main_never_fails_the_boot(self):
        with mock.patch.object(de, "main", side_effect=OSError("disk gone")), mock.patch.object(de, "say"):
            self.assertEqual(de.safe_main(), 0)

    def test_the_recovery_key_is_never_printed_to_the_journal(self):
        said = []
        with mock.patch.object(de, "print", create=True) as pr, mock.patch("builtins.open", mock.mock_open()):
            de.say("RECOVERY KEY: " + RECOVERY, journal=False)
            pr.assert_not_called()


class Wiring(unittest.TestCase):
    def test_unit_runs_before_any_mount_and_a_locked_disk_is_not_a_failed_unit(self):
        u = rd("os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-encrypt.service")
        self.assertIn("Before=local-fs-pre.target", u)
        self.assertIn("DefaultDependencies=no", u)
        self.assertRegex(u, r"(?m)^ExecStart=-/usr/lib/onemind/data-encrypt$")
        self.assertIn("TimeoutStartSec=infinity", u)         # a person may take a while to find the key
        self.assertNotIn("Requires=", u)

    def test_enabled_by_symlink_and_the_script_is_executable_and_uses_the_gateway_python(self):
        link = os.path.join(BASE, "systemd", "system", "sysinit.target.wants", "onemind-data-encrypt.service")
        self.assertEqual(os.readlink(link), "../onemind-data-encrypt.service")
        self.assertTrue(os.access(os.path.join(BASE, "onemind", "data-encrypt"), os.X_OK))
        self.assertIn("/usr/lib/onemind/gateway/venv/bin/python3 -I /usr/lib/onemind/data_encrypt.py",
                      rd("os/rootfs/layers/base/usr/lib/onemind/data-encrypt"))

    def test_the_unlocked_volume_takes_over_the_name_fstab_uses(self):
        rule = rd("os/rootfs/layers/base/usr/lib/udev/rules.d/70-onemind-data-crypt.rules")
        self.assertIn('SYMLINK+="disk/by-partlabel/onemind-data"', rule)
        self.assertIn("link_priority=100", rule)
        self.assertIn("PARTLABEL=onemind-data", rd("os/rootfs/layers/base/etc/fstab"))   # unchanged: legacy boxes still mount

    def test_packages_for_every_tool_it_runs_are_in_the_debian_list(self):
        words = {w for line in rd("os/rootfs/packages/debian-common.txt").splitlines() for w in line.split("#")[0].split()}
        for pkg in ("cryptsetup-bin", "systemd-cryptsetup", "e2fsprogs", "util-linux",
                    "libtss2-esys-3.0.2-0t64", "libtss2-rc0t64", "libtss2-mu-4.0.1-0t64", "libtss2-tcti-device0t64"):
            self.assertIn(pkg, words)
        src = rd("os/rootfs/layers/base/usr/lib/onemind/data_encrypt.py")
        for tool in ("cryptsetup", "mkfs.ext4", "wipefs", "blkid", "udevadm", "systemd-cryptenroll"):
            self.assertIn(f'"{tool}"', src)

    def test_the_grow_service_skips_an_encrypted_volume(self):
        src = rd("os/rootfs/layers/base/usr/lib/onemind/data_extend.py")
        self.assertIn('startswith("dm-")', src)

    def test_tools_image_has_swtpm_for_the_battery(self):
        self.assertRegex(rd("os/rootfs/Containerfile"), r"qemu-system-x86[^\n]*swtpm")


class Assembler(unittest.TestCase):
    def test_layout_accepts_ext4_and_luks2_only(self):
        import assemble
        lay = assemble.load_yaml(os.path.join(ROOT, "os", "boards", "x86_64-efi", "layout.yaml"))
        for fs, ok in (("ext4", True), ("luks2", True), ("btrfs", False)):
            l = copy.deepcopy(lay)
            l["partitions"][-1]["fs"] = fs
            if ok:
                assemble.validate_layout(l)
            else:
                with self.assertRaises(AssertionError):
                    assemble.validate_layout(l)

    def test_every_shipped_layout_is_still_ext4_until_the_battery_passes(self):
        import yaml
        boards = os.path.join(ROOT, "os", "boards")
        for b in sorted(os.listdir(boards)):
            f = os.path.join(boards, b, "layout.yaml")
            if os.path.exists(f):
                parts = yaml.safe_load(open(f))["partitions"]
                data = [p for p in parts if p.get("label") == "onemind-data"]
                for p in data:
                    self.assertIn(p.get("fs", "ext4"), ("ext4", "luks2"), b)

    def test_the_criteria_file_matches_its_preregistered_hash(self):
        want = [l.split()[0] for l in rd("test/qemu/PREREGISTRATION.sha256").splitlines() if "CRITERIA-DATAENC.md" in l]
        self.assertEqual(len(want), 1)
        have = hashlib.sha256(open(os.path.join(ROOT, "test", "qemu", "CRITERIA-DATAENC.md"), "rb").read()).hexdigest()
        self.assertEqual(have, want[0])


if __name__ == "__main__":
    unittest.main()
