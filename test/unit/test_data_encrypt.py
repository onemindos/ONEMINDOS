# SPDX-License-Identifier: Apache-2.0
"""IMG-LUKS-01 / IMG-05 (#152): /data as btrfs (subvolumes @, @storage, @snapshots), inside LUKS2 when the box has a TPM,
TPM2 + recovery-key unlock, and the founder's rule of 2026-11-22: no TPM means unencrypted unless the owner opts in to a
passphrase. data_encrypt.py decides everything; these tests run it with a fake command runner and check the command
sequence, the secrets handling and the 'never touch data that is already there' rules. The real boot (swtpm) is
test/qemu/dataenc.py, run in CI."""
import copy, hashlib, importlib.util, os, re, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib")
spec = importlib.util.spec_from_file_location("data_encrypt", os.path.join(BASE, "onemind", "data_encrypt.py"))
de = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de)
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))

RECOVERY = "cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd"
PASSPHRASE = "correct horse battery staple"


def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


class FakeRunner:
    """Records every command; `fail` is a substring of a command that should fail; `answers` are what
    systemd-ask-password returns, one per call (None = the person gave up)."""
    def __init__(self, fail=None, enroll_out=None, answers=()):
        self.calls, self.fail, self.answers = [], fail, list(answers)
        self.enroll_out = f"A secret recovery key has been generated:\n\n    {RECOVERY}\n" if enroll_out is None else enroll_out

    def __call__(self, cmd, input=None, check=True):
        line = " ".join(cmd)
        self.calls.append((cmd, input))
        rc = 1 if self.fail and self.fail in line else 0
        out = self.enroll_out if "--recovery-key" in line and rc == 0 else ""
        if cmd[0] == "systemd-ask-password":
            ans = self.answers.pop(0) if self.answers else None
            rc, out = (1, "") if ans is None else (0, ans + "\n")
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
        self.assertEqual(de.classify("ntfs", False), "unknown")

    def test_ext4_btrfs_and_luks_are_recognised(self):
        self.assertEqual(de.classify("ext4", False), "ext4")
        self.assertEqual(de.classify("btrfs", False), "btrfs")        # a box without a TPM: plain btrfs, left alone
        self.assertEqual(de.classify("crypto_LUKS", False), "luks")

    def test_recovery_key_is_found_in_cryptenroll_output(self):
        self.assertEqual(de.parse_recovery_key(f"noise\n  {RECOVERY}\nmore"), RECOVERY)
        self.assertIsNone(de.parse_recovery_key("no key here"))
        self.assertIsNone(de.parse_recovery_key("aaaaaaaa-aaaaaaaa"))  # 'a' is not a modhex letter; too short anyway


class FounderRule(unittest.TestCase):
    """2026-11-22: TPM -> encrypted, unlocks by itself. No TPM -> unencrypted, unless the owner opts in to a
    passphrase typed at every restart (a home hub must come back by itself after a power cut)."""
    def test_a_tpm_means_encrypted_with_tpm2_unlock(self):
        self.assertEqual(de.plan(True, False), "tpm2")
        self.assertEqual(de.plan(True, True), "tpm2")              # the passphrase option is for boxes without a TPM

    def test_no_tpm_means_plain_unless_the_owner_asks(self):
        self.assertEqual(de.plan(False, False), "plain")
        self.assertEqual(de.plan(False, True), "passphrase")

    def test_a_tpm_the_firmware_announces_but_that_is_not_ready_is_never_plain(self):
        # Fail closed: plain btrfs is left alone on every later boot, so a late TPM driver must not mean "unencrypted".
        self.assertEqual(de.plan(False, False, firmware_tpm=True), "recovery-key")
        self.assertEqual(de.plan(False, True, firmware_tpm=True), "passphrase")
        self.assertEqual(de.plan(True, False, firmware_tpm=True), "tpm2")

    def test_the_firmware_tpm_check_reads_the_acpi_table_or_the_event_log(self):
        for present in de.FIRMWARE_TPM:
            with mock.patch.object(de.os.path, "exists", side_effect=lambda p: p == present):
                self.assertTrue(de.firmware_has_tpm(), present)
        with mock.patch.object(de.os.path, "exists", return_value=False):
            self.assertFalse(de.firmware_has_tpm())
        self.assertIn("/sys/firmware/acpi/tables/TPM2", de.FIRMWARE_TPM)

    def test_the_opt_in_is_one_kernel_command_line_word(self):
        self.assertTrue(de.wants_passphrase("quiet onemind.data_encrypt=passphrase console=ttyS0"))
        self.assertTrue(de.wants_passphrase("onemind.data_encrypt=passphrase\n"))
        for line in ("", "quiet", "onemind.data_encrypt=", "onemind.data_encrypt=yes", "xonemind.data_encrypt=passphrase",
                     "onemind.data_encrypt=passphrasex"):
            self.assertFalse(de.wants_passphrase(line), line)


class Passphrase(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(de, "say")
        self.say = p.start()
        self.addCleanup(p.stop)

    def test_asked_twice_and_returned_when_both_match(self):
        r = FakeRunner(answers=[PASSPHRASE, PASSPHRASE])
        self.assertEqual(de.ask_passphrase(r), PASSPHRASE)
        self.assertEqual([c[0] for c, _ in r.calls], ["systemd-ask-password"] * 2)
        self.assertIn("--timeout=0", r.lines()[0])

    def test_a_mismatch_or_a_short_one_asks_again_and_three_failures_give_up(self):
        r = FakeRunner(answers=[PASSPHRASE, PASSPHRASE + "x", "short", PASSPHRASE, PASSPHRASE])   # too short: no 2nd ask
        self.assertEqual(de.ask_passphrase(r), PASSPHRASE)
        r = FakeRunner(answers=["a" * 12, "b" * 12] * 3)
        self.assertIsNone(de.ask_passphrase(r))
        self.assertIsNone(de.ask_passphrase(FakeRunner(answers=[])))  # nobody at the console

    def test_the_passphrase_is_never_on_a_command_line_or_in_a_message(self):
        r = FakeRunner(answers=[PASSPHRASE, PASSPHRASE + "x", PASSPHRASE, PASSPHRASE])
        de.ask_passphrase(r)
        for line in r.lines():
            self.assertNotIn(PASSPHRASE, line)
        for call in self.say.call_args_list:
            self.assertNotIn(PASSPHRASE, " ".join(map(str, call.args)))


class FirstBoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(de, "KEYFILE", os.path.join(self.tmp, "vol.key")),
                        mock.patch.object(de, "MKFS_MNT", os.path.join(self.tmp, "mnt"))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def go(self, tpm, passphrase=None, **kw):
        r = FakeRunner(**kw)
        return r, de.first_boot_encrypt("/dev/vda7", tpm, r, rand=lambda n: b"\x07" * n, passphrase=passphrase)

    STEPS = ("luksFormat", "cryptsetup open", "mkfs.btrfs", "subvolume create", "set-default", "umount",
             "--recovery-key", "luksAddKey", "--tpm2-device=auto", "luksKillSlot", "mount")

    def step(self, line):
        return next(w for w in self.STEPS if w in line)

    def test_order_and_flags(self):
        r, res = self.go(True)
        L = r.lines()
        self.assertEqual([self.step(l) for l in L],
                         ["luksFormat", "cryptsetup open", "mkfs.btrfs", "mount", "subvolume create", "subvolume create",
                          "subvolume create", "set-default", "umount", "--recovery-key", "--tpm2-device=auto", "luksKillSlot"])
        fmt = L[0]
        self.assertIn("--type luks2", fmt)
        self.assertIn("aes-xts-plain64", fmt)
        self.assertTrue(fmt.endswith("/dev/vda7"))
        self.assertIn("--tpm2-pcrs=7", L[10])
        self.assertIn("-L onemind-data", L[2])
        self.assertTrue(L[2].endswith(" /dev/mapper/onemind-data"))
        self.assertFalse(any("mkfs.ext4" in l for l in L))
        self.assertEqual(res, {"recovery_key": RECOVERY, "tpm2": True, "passphrase": False})

    def test_btrfs_gets_the_three_subvolumes_and_at_is_what_data_mounts(self):
        r, _ = self.go(True)
        mnt = de.MKFS_MNT
        L = r.lines()
        self.assertIn(f"mount -t btrfs -o subvolid=5 /dev/mapper/onemind-data {mnt}", L)
        self.assertEqual([l.split()[-1] for l in L if "subvolume create" in l],
                         [f"{mnt}/@", f"{mnt}/@storage", f"{mnt}/@snapshots"])
        self.assertIn(f"btrfs subvolume set-default {mnt}/@", L)     # fstab mounts /data with no subvol= option
        self.assertIn(f"umount {mnt}", L)

    def test_the_random_volume_key_slot_is_killed_with_the_recovery_key_on_stdin(self):
        """cryptsetup luksKillSlot checks the key against the OTHER slots: the slot's own key is refused (checked with
        cryptsetup 2.7 on a file image), so the recovery key goes in on stdin."""
        r, _ = self.go(True)
        cmd, given = r.calls[-1]
        self.assertEqual(cmd, ["cryptsetup", "luksKillSlot", "--batch-mode", "--key-file", "-", "/dev/vda7", "0"])
        self.assertEqual(given, RECOVERY)

    def test_the_passphrase_goes_into_its_own_slot_on_stdin_only(self):
        r, res = self.go(False, passphrase=PASSPHRASE)
        add = [(c, i) for c, i in r.calls if "luksAddKey" in c]
        self.assertEqual(len(add), 1)
        cmd, given = add[0]
        self.assertEqual(given, PASSPHRASE)                           # no newline: what the boot prompt hands over
        self.assertEqual(cmd[-1], "-")
        self.assertIn("argon2id", cmd)                                # a person's passphrase gets the slow hash
        self.assertIn(de.KEYFILE, cmd)
        self.assertFalse(any("--tpm2" in l for l in r.lines()))
        self.assertTrue(any("--recovery-key" in l for l in r.lines()))  # the kit still gets a recovery key
        for line in r.lines():
            self.assertNotIn(PASSPHRASE, line)
        self.assertEqual(res, {"recovery_key": RECOVERY, "tpm2": False, "passphrase": True})

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
        self.assertTrue(all(i in (None, RECOVERY) for _, i in r.calls))

    def test_a_failure_wipes_the_partition_back_to_blank_and_removes_the_key(self):
        for step in ("luksFormat", "mkfs.btrfs", "subvolume create", "--recovery-key"):
            with self.subTest(step=step):
                r = FakeRunner(fail=step)
                with self.assertRaises(subprocess.CalledProcessError if step != "--recovery-key" else subprocess.CalledProcessError):
                    de.first_boot_encrypt("/dev/vda7", True, r)
                self.assertTrue(r.lines()[-1].startswith("wipefs --all --force /dev/vda7"), r.lines())
                self.assertFalse(os.path.exists(de.KEYFILE))
                if step != "luksFormat":
                    self.assertTrue(any(l.startswith("cryptsetup close onemind-data") for l in r.lines()))
                if step == "subvolume create":
                    self.assertIn(f"umount {de.MKFS_MNT}", r.lines())     # never left mounted

    def test_the_cleanup_leaves_a_head_that_classifies_as_blank(self):
        """Real file, not a call log: luksFormat leaves a header and keyslots far past the two magics that wipefs
        erases. After a failed first boot the next boot must see 'blank' again and retry."""
        node = os.path.join(self.tmp, "part.img")
        with open(node, "wb") as f:
            f.truncate(20 << 20)

        class Runner(FakeRunner):
            def __call__(self, cmd, input=None, check=True):
                if cmd[:2] == ["cryptsetup", "luksFormat"]:       # header + keyslot area, like real LUKS2
                    with open(node, "r+b") as f:
                        f.write(b"LUKS\xba\xbe" + b"\xa5" * ((2 << 20) - 6))
                        f.seek(0x4000)
                        f.write(b"SKUL\xba\xbe")
                if cmd[0] == "wipefs":                             # erases only the two magics
                    with open(node, "r+b") as f:
                        f.write(b"\0" * 6)
                        f.seek(0x4000)
                        f.write(b"\0" * 6)
                return super().__call__(cmd, input, check)

        r = Runner(fail="mkfs.btrfs")
        with self.assertRaises(subprocess.CalledProcessError):
            de.first_boot_encrypt(node, False, r)
        self.assertTrue(de.head_is_zero(node))
        self.assertEqual(de.classify("", de.head_is_zero(node)), "blank")
        with open(node, "rb") as f:
            self.assertFalse(any(f.read(de.SCRUB_BYTES)))

    def test_wipefs_alone_would_not_have_been_enough(self):
        node = os.path.join(self.tmp, "p2.img")
        with open(node, "wb") as f:
            f.write(b"\0" * 6 + b"\xa5" * 4096)
        self.assertFalse(de.head_is_zero(node))
        de.zero_head(node)
        self.assertTrue(de.head_is_zero(node))

    def test_no_recovery_key_in_the_output_is_a_failure_not_a_silent_success(self):
        r = FakeRunner(enroll_out="nothing useful")
        with self.assertRaises(RuntimeError):
            de.first_boot_encrypt("/dev/vda7", True, r)
        self.assertTrue(r.lines()[-1].startswith("wipefs"))


class Plain(unittest.TestCase):
    """No TPM and no opt-in: btrfs straight on the partition, no LUKS, no key of any kind."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.object(de, "MKFS_MNT", os.path.join(self.tmp, "mnt"))
        p.start()
        self.addCleanup(p.stop)

    def test_btrfs_with_subvolumes_and_nothing_else(self):
        r = FakeRunner()
        de.make_plain("/dev/vda7", r)
        L = r.lines()
        self.assertFalse(any(l.startswith("cryptsetup") or "cryptenroll" in l for l in L))
        mk = next(l for l in L if l.startswith("mkfs.btrfs"))
        self.assertTrue(mk.endswith(" /dev/vda7"))
        self.assertNotIn(" -f", mk)          # the raw partition: mkfs must refuse if anything appeared on it
        self.assertEqual(len([l for l in L if "subvolume create" in l]), 3)
        self.assertTrue(any("set-default" in l for l in L))

    def test_a_failure_puts_the_partition_back_to_blank(self):
        r = FakeRunner(fail="subvolume create")
        with mock.patch.object(de, "zero_head") as z, self.assertRaises(subprocess.CalledProcessError):
            de.make_plain("/dev/vda7", r)
        self.assertIn("wipefs --all --force /dev/vda7", r.lines())
        z.assert_called_once_with("/dev/vda7")


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
        with mock.patch.object(de, "say") as say:
            self.assertEqual(de.unlock("/dev/vda7", False, r), "recovery-key")
        self.assertEqual(len(r.calls), 1)
        self.assertIn("passphrase or the recovery key", say.call_args.args[0])   # an opted-in box has both

    def test_three_wrong_keys_leave_it_locked(self):
        self.assertIsNone(de.unlock("/dev/vda7", False, FakeRunner(fail="tries=3")))


class Main(unittest.TestCase):
    """main() with the disk faked: what it finds decides what it does."""
    def run_main(self, sig, zero, tpm=False, cmdline="quiet", pw=PASSPHRASE, firmware_tpm=False):
        r = FakeRunner()
        exists = lambda p: {"/dev/tpmrm0": tpm, "/sys/firmware/acpi/tables/TPM2": firmware_tpm}.get(p, False)
        self.plain = mock.patch.object(de, "make_plain").start()
        self.ask = mock.patch.object(de, "ask_passphrase", return_value=pw).start()
        mock.patch.object(de, "cmdline", return_value=cmdline).start()
        self.addCleanup(mock.patch.stopall)
        with mock.patch.object(de, "wait_for", return_value=True), \
             mock.patch.object(de.os.path, "realpath", return_value="/dev/vda7"), \
             mock.patch.object(de.os.path, "exists", side_effect=exists), \
             mock.patch.object(de, "signature", return_value=sig), \
             mock.patch.object(de, "head_is_zero", return_value=zero), \
             mock.patch.object(de, "say"), mock.patch.object(de, "write_state") as ws, \
             mock.patch.object(de, "keep_recovery_key") as keep, \
             mock.patch.object(de, "first_boot_encrypt", side_effect=lambda node, has_tpm, runner, passphrase=None:
                               {"recovery_key": RECOVERY, "tpm2": has_tpm, "passphrase": bool(passphrase)}) as fb, \
             mock.patch.object(de, "unlock", return_value="tpm2" if tpm else None) as ul:
            rc = de.main(r)
        return rc, r, ws, keep, fb, ul

    def test_ext4_boxes_are_left_alone(self):
        rc, r, ws, keep, fb, ul = self.run_main("ext4", False)
        self.assertEqual(rc, 0)
        fb.assert_not_called(); ul.assert_not_called(); keep.assert_not_called()
        self.assertEqual(ws.call_args.kwargs["state"], "plain")

    def test_unknown_data_is_never_formatted(self):
        for sig, zero in (("", False), ("xfs", True), ("ntfs", False)):
            rc, r, ws, keep, fb, ul = self.run_main(sig, zero)
            fb.assert_not_called(); ul.assert_not_called(); self.plain.assert_not_called()
            self.assertEqual(ws.call_args.kwargs["state"], "unknown")

    def test_a_plain_btrfs_box_is_left_alone(self):
        rc, r, ws, keep, fb, ul = self.run_main("btrfs", False)
        fb.assert_not_called(); ul.assert_not_called(); self.plain.assert_not_called()
        self.assertEqual(ws.call_args.kwargs["state"], "plain")

    def test_blank_with_a_tpm_is_encrypted_and_the_key_is_kept_in_ram(self):
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=True)
        fb.assert_called_once()
        self.assertTrue(fb.call_args.args[1])
        self.assertIsNone(fb.call_args.kwargs.get("passphrase"))
        keep.assert_called_once_with(RECOVERY)
        self.plain.assert_not_called(); self.ask.assert_not_called()
        self.assertEqual(ws.call_args.kwargs["state"], "encrypted")
        self.assertEqual(ws.call_args.kwargs["fs"], "btrfs")

    def test_blank_without_a_tpm_stays_unencrypted(self):
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=False)
        self.plain.assert_called_once()
        fb.assert_not_called(); keep.assert_not_called(); self.ask.assert_not_called()
        self.assertEqual(ws.call_args.kwargs["state"], "plain")
        self.assertEqual(ws.call_args.kwargs["fs"], "btrfs")

    def test_blank_on_a_tpm_box_whose_tpm_device_is_missing_is_encrypted_with_the_recovery_key_never_plain(self):
        # The firmware announces a TPM (ACPI TPM2 table) but the driver has not made /dev/tpmrm0: before #152 this
        # was LUKS + recovery key, and it must stay encrypted (a plain btrfs would be left alone for good).
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=False, firmware_tpm=True)
        self.plain.assert_not_called(); self.ask.assert_not_called()
        fb.assert_called_once()
        self.assertFalse(fb.call_args.args[1])                    # no TPM enrolment: the device is not there
        self.assertIsNone(fb.call_args.kwargs.get("passphrase"))
        keep.assert_called_once_with(RECOVERY)
        self.assertEqual(ws.call_args.kwargs["state"], "encrypted")
        self.assertEqual(ws.call_args.kwargs["unlock"], "recovery-key")
        self.assertEqual(rc, 0)

    def test_blank_without_a_tpm_but_opted_in_asks_for_a_passphrase(self):
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=False, cmdline="onemind.data_encrypt=passphrase")
        self.ask.assert_called_once()
        fb.assert_called_once()
        self.assertFalse(fb.call_args.args[1])
        self.assertEqual(fb.call_args.kwargs["passphrase"], PASSPHRASE)
        self.plain.assert_not_called()
        keep.assert_called_once_with(RECOVERY)
        self.assertEqual(ws.call_args.kwargs["unlock"], "passphrase")
        self.assertNotIn(PASSPHRASE, repr(ws.call_args))

    def test_opted_in_but_no_passphrase_chosen_formats_nothing(self):
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=False, cmdline="onemind.data_encrypt=passphrase", pw=None)
        fb.assert_not_called(); self.plain.assert_not_called(); keep.assert_not_called()
        self.assertEqual(rc, 0)
        self.assertEqual(ws.call_args.kwargs["state"], "blank")

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
        # A TPM whose driver probes late must not look like "no TPM": wait for systemd-tpm2-generator's target.
        self.assertRegex(u, r"(?m)^After=tpm2\.target$")
        self.assertRegex(u, r"(?m)^Wants=tpm2\.target$")
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

    def test_data_mounts_whatever_filesystem_the_partition_holds(self):
        """ext4 on boxes installed before #152, btrfs (its default subvolume @) on new ones: one fstab line for both."""
        line = next(l for l in rd("os/rootfs/layers/base/etc/fstab").splitlines() if l.startswith("PARTLABEL=onemind-data"))
        self.assertEqual(line.split()[1:3], ["/data", "auto"])
        self.assertNotIn("subvol", line)                              # ext4 would refuse the option

    def test_packages_for_every_tool_it_runs_are_in_the_debian_list(self):
        words = {w for line in rd("os/rootfs/packages/debian-common.txt").splitlines() for w in line.split("#")[0].split()}
        for pkg in ("cryptsetup-bin", "systemd-cryptsetup", "btrfs-progs", "util-linux",
                    "libtss2-esys-3.0.2-0t64", "libtss2-rc0t64", "libtss2-mu-4.0.1-0t64", "libtss2-tcti-device0t64"):
            self.assertIn(pkg, words)
        src = rd("os/rootfs/layers/base/usr/lib/onemind/data_encrypt.py")
        for tool in ("cryptsetup", "mkfs.btrfs", "btrfs", "mount", "umount", "wipefs", "blkid", "udevadm",
                     "systemd-cryptenroll", "systemd-ask-password"):
            self.assertIn(f'"{tool}"', src)
        self.assertNotIn('"mkfs.ext4"', src)

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
