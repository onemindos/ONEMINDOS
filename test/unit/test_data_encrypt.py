# SPDX-License-Identifier: Apache-2.0
"""IMG-LUKS-01 / IMG-05 (#152): /data as btrfs (subvolumes @ and @storage, with @storage/.snapshots for snapper), inside LUKS2 when the box has a TPM,
TPM2 + recovery-key unlock, and the founder's rule of 2026-11-22: no TPM means unencrypted unless the owner opts in to a
passphrase. data_encrypt.py decides everything; these tests run it with a fake command runner and check the command
sequence, the secrets handling and the 'never touch data that is already there' rules. The real boot (swtpm) is
test/qemu/dataenc.py, run in CI."""
import copy, hashlib, json, importlib.util, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib")
spec = importlib.util.spec_from_file_location("data_encrypt", os.path.join(BASE, "onemind", "data_encrypt.py"))
de = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de)
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))

RECOVERY = "cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd-cccccccd"
PASSPHRASE = "correct horse battery staple"
PARTUUID = "6f1d0000-0000-4000-8000-0000000000aa"
LUKS_UUID = "11110000-0000-4000-8000-00000000bbbb"


def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


class FakeRunner:
    """Records every command; `fail` is a substring of a command that should fail; `answers` are what
    systemd-ask-password returns, one per call (None = the person gave up)."""
    def __init__(self, fail=None, enroll_out=None, answers=(), partuuid=PARTUUID):
        self.calls, self.fail, self.answers, self.partuuid = [], fail, list(answers), partuuid
        self.enroll_out = f"A secret recovery key has been generated:\n\n    {RECOVERY}\n" if enroll_out is None else enroll_out

    def __call__(self, cmd, input=None, check=True):
        line = " ".join(cmd)
        self.calls.append((cmd, input))
        rc = 1 if self.fail and self.fail in line else 0
        out = self.enroll_out if "--recovery-key" in line and rc == 0 else ""
        if cmd[0] == "blkid" and "export" in cmd:
            out = f"UUID={LUKS_UUID.upper()}\nTYPE=crypto_LUKS\n" + (f"PART_ENTRY_UUID={self.partuuid}\n" if self.partuuid else "")
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

    def firmware(self, present, major):
        """firmware_has_tpm() with only the paths in `present` there and tpm_version_major reading `major`."""
        with mock.patch.object(de.os.path, "exists", side_effect=lambda p: p in present), \
             mock.patch.object(de, "read_sysfs", side_effect=lambda p: major if p == de.TPM_VERSION_MAJOR else None):
            return de.firmware_has_tpm()

    def test_the_firmware_tpm_check_reads_the_acpi_table_or_a_tpm2_event_log(self):
        self.assertEqual(de.ACPI_TPM2, "/sys/firmware/acpi/tables/TPM2")
        self.assertEqual(de.EVENT_LOG, "/sys/kernel/security/tpm0/binary_bios_measurements")
        self.assertEqual(de.TPM_VERSION_MAJOR, "/sys/class/tpm/tpm0/tpm_version_major")
        self.assertTrue(self.firmware({de.ACPI_TPM2}, None))       # the ACPI TPM2 table alone is a TPM 2.0
        self.assertTrue(self.firmware({de.EVENT_LOG}, "2"))
        self.assertFalse(self.firmware(set(), "2"))
        self.assertFalse(self.firmware(set(), None))

    def test_an_event_log_from_a_tpm_1_2_or_of_unknown_version_is_not_a_tpm2(self):
        # The kernel makes the event log for a TPM 1.2 too, and a TPM 1.2 never gets /dev/tpmrm0 (systemd's
        # efi_has_tpm2() checks tpm_version_major for the same reason).
        self.assertFalse(self.firmware({de.EVENT_LOG}, "1"))
        self.assertFalse(self.firmware({de.EVENT_LOG}, None))      # the version cannot be read: not a TPM2
        self.assertFalse(self.firmware({de.EVENT_LOG}, ""))

    def test_read_sysfs_strips_and_gives_none_when_the_file_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "tpm_version_major")
            with open(p, "w") as f:
                f.write("2\n")
            self.assertEqual(de.read_sysfs(p), "2")
            self.assertIsNone(de.read_sysfs(os.path.join(d, "missing")))

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

    STEPS = ("luksFormat", "cryptsetup open", "mkfs.btrfs", "subvolume create", "chmod", "set-default", "umount",
             "--recovery-key", "luksAddKey", "--tpm2-device=auto", "luksKillSlot", "mount", "blkid", "token import")

    def step(self, line):
        return next(w for w in self.STEPS if w in line)

    def test_order_and_flags(self):
        r, res = self.go(True)
        L = r.lines()
        self.assertEqual([self.step(l) for l in L],
                         ["luksFormat", "blkid", "token import", "cryptsetup open", "mkfs.btrfs", "mount", "subvolume create", "subvolume create",
                          "subvolume create", "chmod", "set-default", "umount", "--recovery-key", "--tpm2-device=auto",
                          "luksKillSlot"])
        self.assertEqual(len([l for l in L if "subvolume create" in l]), 3)      # @, @storage, @storage/.snapshots
        fmt = L[0]
        self.assertIn("--type luks2", fmt)
        self.assertIn("aes-xts-plain64", fmt)
        self.assertTrue(fmt.endswith("/dev/vda7"))
        self.assertIn("--tpm2-pcrs=7", next(l for l in L if "--tpm2-device=auto" in l))
        mk = next(l for l in L if l.startswith("mkfs.btrfs"))
        self.assertIn("-L onemind-data", mk)
        self.assertTrue(mk.endswith(" /dev/mapper/onemind-data"))
        self.assertFalse(any("mkfs.ext4" in l for l in L))
        self.assertEqual(res, {"recovery_key": RECOVERY, "tpm2": True, "passphrase": False})

    def test_the_luks2_header_gets_the_onemind_token_the_factory_reset_looks_for(self):
        """internal/host/reset.go lists a LUKS2 data partition only with token id 30 of type onemind-storage whose
        partuuid is the partition's own (ops.Candidates, ops.Choose); without it the reset refused every default box."""
        r, _ = self.go(True)
        L = r.lines()
        i = next(i for i, l in enumerate(L) if "token import" in l)
        cmd, stdin = r.calls[i]
        self.assertEqual(cmd, ["cryptsetup", "token", "import", "--token-id", "30", "/dev/vda7"])
        tok = json.loads(stdin)
        self.assertEqual(tok["type"], "onemind-storage")
        self.assertEqual(tok["partuuid"], PARTUUID)
        self.assertEqual(tok["member_uuid"], LUKS_UUID)
        self.assertEqual(tok["generation"], 1)
        self.assertEqual(tok["keyslots"], [])
        # the set id is also the btrfs UUID, and the token is written right after the format (before any unlock)
        mk = next(l for l in L if l.startswith("mkfs.btrfs"))
        self.assertIn(f"-U {tok['set_uuid']} ", mk)
        self.assertRegex(tok["set_uuid"], r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        self.assertLess(i, next(i for i, l in enumerate(L) if l.startswith("cryptsetup open")))
        self.assertNotIn(RECOVERY, json.dumps(r.calls[i]))

    def test_the_token_is_the_one_the_go_side_reads(self):
        src = rd("internal/storage/luks.go")
        self.assertIn(f"TokenID = {de.TOKEN_ID}", src)
        self.assertIn(f'TokenType = "{de.TOKEN_TYPE}"', src)
        for key in json.loads(de.onemind_token("s", "m", "p")):
            self.assertIn(f'json:"{key}"', src)

    def test_a_partition_without_a_gpt_id_still_encrypts_but_says_the_reset_will_refuse(self):
        r = FakeRunner(partuuid="")
        with mock.patch.object(de, "say") as say:
            de.first_boot_encrypt("/dev/vda7", False, r, rand=lambda n: b"\x07" * n, passphrase=None)
        self.assertFalse(any("token import" in l for l in r.lines()))
        self.assertTrue(any("refuse" in str(c.args[0]) for c in say.call_args_list))

    def test_btrfs_gets_at_and_storage_with_snapshots_inside_storage_and_at_is_what_data_mounts(self):
        r, _ = self.go(True)
        mnt = de.MKFS_MNT
        L = r.lines()
        self.assertIn(f"mount -t btrfs -o subvolid=5 /dev/mapper/onemind-data {mnt}", L)
        self.assertEqual([l.split()[-1] for l in L if "subvolume create" in l],
                         [f"{mnt}/@", f"{mnt}/@storage", f"{mnt}/@storage/.snapshots"])
        # never a top-level snapshots subvolume (it would be a sibling snapper does not look in), and @ is never a
        # place snapper could snapshot: the k3s data and the databases live in @
        self.assertFalse(any("@snapshots" in l for l in L))
        self.assertTrue(os.path.isdir(os.path.join(mnt, "@", "storage")))        # the mount point of data-storage.mount
        self.assertIn(f"chmod 0750 {mnt}/@storage/.snapshots", L)    # snapper wants its snapshot directory root-only
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
        self.assertTrue(all(i in (None, RECOVERY) for c, i in r.calls if c[:3] != ["cryptsetup", "token", "import"]))   # the token JSON holds ids, no secret

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
        self.assertEqual(len([l for l in L if "subvolume create" in l]), 3)      # @, @storage, @storage/.snapshots
        self.assertTrue(any("set-default" in l for l in L))

    def test_a_failure_puts_the_partition_back_to_blank(self):
        r = FakeRunner(fail="subvolume create")
        with mock.patch.object(de, "zero_head") as z, self.assertRaises(subprocess.CalledProcessError):
            de.make_plain("/dev/vda7", r)
        self.assertIn("wipefs --all --force /dev/vda7", r.lines())
        z.assert_called_once_with("/dev/vda7")


class Consoles(unittest.TestCase):
    """The recovery key and the prompts must reach a person during early boot, while the boot splash (plymouth) runs and
    swallows /dev/console (found booting E1: the key was in the journal's absence AND on no console)."""
    def test_the_active_consoles_come_from_sysfs(self):
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "active")
            open(f, "w").write("tty0 ttyS0\n")
            with mock.patch.object(de, "ACTIVE_CONSOLES", f):
                self.assertEqual(de.console_devices(), ["/dev/tty0", "/dev/ttyS0"])
                self.assertEqual(de.serial_consoles(), ["/dev/ttyS0"])        # the screen is not a serial port
            with mock.patch.object(de, "ACTIVE_CONSOLES", os.path.join(t, "missing")):
                self.assertEqual(de.console_devices(), [])

    def test_serial_ports_are_recognised_by_name(self):
        self.assertEqual(de.serial_consoles(["tty0", "ttyS0", "ttyS1", "ttyAMA0", "ttyUSB0", "tty1", "hvc0"]),
                         ["/dev/ttyS0", "/dev/ttyS1", "/dev/ttyAMA0", "/dev/ttyUSB0"])

    def test_a_line_goes_to_every_console_terminal_and_not_twice_to_dev_console(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = os.path.join(t, "tty0"), os.path.join(t, "ttyS0")
            for p in (a, b):
                open(p, "w").close()
            self.assertEqual(de.to_consoles("hello", [a, b]), 2)
            self.assertEqual(open(a, "rb").read(), b"hello\r\n")
            self.assertEqual(open(b, "rb").read(), b"hello\r\n")

    def test_dev_console_is_only_the_fallback(self):
        with tempfile.TemporaryDirectory() as t:
            fallback = os.path.join(t, "console")
            open(fallback, "w").close()
            real_open = os.open
            with mock.patch.object(de.os, "open", lambda path, *a, **k: real_open(fallback if path == "/dev/console" else path, *a, **k)):
                self.assertEqual(de.to_consoles("x", [os.path.join(t, "nope")]), 1)      # none took it: /dev/console did
                self.assertEqual(open(fallback, "rb").read(), b"x\r\n")
                open(fallback, "w").close()
                ok = os.path.join(t, "ttyS0")
                open(ok, "w").close()
                self.assertEqual(de.to_consoles("y", [ok]), 1)
                self.assertEqual(open(fallback, "rb").read(), b"")                           # a terminal took it: no second copy

    def test_writing_never_raises_and_never_takes_a_terminal(self):
        self.assertEqual(de.to_consoles("x", ["/nonexistent/tty"]) in (0, 1), True)      # missing devices are skipped
        flags = []
        real_open = os.open
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "tty")
            open(f, "w").close()
            with mock.patch.object(de.os, "open", lambda path, fl, *a: (flags.append(fl), real_open(path, fl, *a))[1]):
                de.to_consoles("x", [f])
        self.assertTrue(flags[0] & os.O_NOCTTY and flags[0] & os.O_NONBLOCK)

    def test_the_recovery_key_goes_to_the_consoles_and_never_to_stdout_or_the_journal(self):
        sent = []
        out = []
        with mock.patch.object(de, "to_consoles", lambda line, devices=None: sent.append(line) or 1), \
                mock.patch("builtins.print", lambda *a, **k: out.append(a)):
            de.say("RECOVERY KEY: " + RECOVERY, journal=False)
            de.say("something harmless")
        self.assertEqual(len(sent), 2)
        self.assertIn(RECOVERY, sent[0])
        self.assertEqual(out, [("ONEMIND-DATA-CRYPT: something harmless",)])

    def test_the_serial_agent_is_started_per_serial_port_and_always_stopped(self):
        started, killed = [], []

        class P:
            def __init__(self, cmd, **kw):
                started.append((cmd, kw))
                self.pid = 4242 + len(started)

            def wait(self, t=None):
                return 0
        with mock.patch.object(de.os, "killpg", lambda pid, sig: killed.append((pid, sig))):
            with de.serial_prompt_agent(["/dev/ttyS0", "/dev/ttyS1"], popen=P) as n:
                self.assertEqual(n, 2)
                self.assertEqual([c for c, _ in started],
                                 [[de.AGENT, "--watch", "--console=/dev/ttyS0"], [de.AGENT, "--watch", "--console=/dev/ttyS1"]])
                self.assertTrue(all(kw["start_new_session"] for _, kw in started))
            self.assertEqual(len(killed), 2)
            killed.clear()
            with self.assertRaises(RuntimeError), de.serial_prompt_agent(["/dev/ttyS0"], popen=P):
                raise RuntimeError("boom")
            self.assertEqual(len(killed), 1)                                              # stopped on failure too

    def test_no_serial_console_means_no_agent(self):
        with mock.patch.object(de, "serial_consoles", lambda names=None: []):
            with de.serial_prompt_agent(popen=lambda *a, **k: self.fail("started an agent")) as n:
                self.assertEqual(n, 0)

    def test_the_prompts_run_inside_the_agent(self):
        order = []

        class Ctx:
            def __enter__(self):
                order.append("agent on")

            def __exit__(self, *a):
                order.append("agent off")

        def runner(cmd, input=None, check=True):
            order.append(cmd[0].split("/")[-1] if "attach" not in cmd else "attach")
            return subprocess.CompletedProcess(cmd, 1 if "attach" in cmd else 0, stdout="longenoughpass\n", stderr="")
        with mock.patch.object(de, "serial_prompt_agent", lambda *a, **k: Ctx()), mock.patch.object(de, "say", lambda *a, **k: None):
            de.unlock("/dev/vda7", False, runner)
            self.assertEqual(order, ["agent on", "attach", "agent off"])
            order.clear()
            de.ask_passphrase(runner, tries=1)
            self.assertEqual(order[0], "agent on")
            self.assertEqual(order[-1], "agent off")
            self.assertIn("systemd-ask-password", order)

    def test_the_service_waits_for_the_serial_agent_tools(self):
        """The agent binary is in the systemd package (always installed); its path is the one the stock unit uses."""
        self.assertEqual(de.AGENT, "/usr/bin/systemd-tty-ask-password-agent")


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
    def run_main(self, sig, zero, tpm=False, cmdline="quiet", pw=PASSPHRASE, firmware_tpm=False, event_log=None):
        """`event_log` is None (no firmware event log) or what tpm_version_major reads ("1", "2")."""
        r = FakeRunner()
        exists = lambda p: {"/dev/tpmrm0": tpm, "/sys/firmware/acpi/tables/TPM2": firmware_tpm,
                            "/sys/kernel/security/tpm0/binary_bios_measurements": event_log is not None}.get(p, False)
        mock.patch.object(de, "read_sysfs", side_effect=lambda p: event_log
                          if p == "/sys/class/tpm/tpm0/tpm_version_major" else None).start()
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

    def test_blank_with_a_tpm2_event_log_but_no_tpm_device_is_encrypted_with_the_recovery_key(self):
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=False, event_log="2")
        self.plain.assert_not_called(); self.ask.assert_not_called()
        fb.assert_called_once()
        self.assertFalse(fb.call_args.args[1])
        keep.assert_called_once_with(RECOVERY)
        self.assertEqual(ws.call_args.kwargs["state"], "encrypted")
        self.assertEqual(ws.call_args.kwargs["unlock"], "recovery-key")

    def test_blank_on_a_tpm_1_2_box_stays_unencrypted_with_no_key_to_type(self):
        # An older office PC with a TPM 1.2: the kernel makes the event log, but there is no /dev/tpmrm0 and never
        # will be. The founder's rule: no usable TPM means plain unless the owner asks, so it comes back by itself.
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=False, event_log="1")
        self.plain.assert_called_once()
        fb.assert_not_called(); keep.assert_not_called(); self.ask.assert_not_called()
        self.assertEqual(ws.call_args.kwargs["state"], "plain")
        self.assertEqual(ws.call_args.kwargs["fs"], "btrfs")
        self.assertEqual(rc, 0)

    def test_a_tpm_1_2_box_can_still_opt_in_to_a_passphrase(self):
        rc, r, ws, keep, fb, ul = self.run_main("", True, tpm=False, event_log="1",
                                                cmdline="onemind.data_encrypt=passphrase")
        self.ask.assert_called_once(); self.plain.assert_not_called()
        self.assertEqual(fb.call_args.kwargs["passphrase"], PASSPHRASE)
        self.assertEqual(ws.call_args.kwargs["unlock"], "passphrase")

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

    def test_an_armed_factory_reset_leaves_the_data_disk_alone(self):
        """The wipe unit runs after this one and erases the disk: a LUKS disk must not be unlocked (a passphrase box
        would be asked for the passphrase of data being erased), and a blank one is formatted only on the restart."""
        for sig, zero in (("crypto_LUKS", False), ("", True), ("btrfs", False)):
            with mock.patch.object(de, "reset_armed", return_value=True):
                rc, r, ws, keep, fb, ul = self.run_main(sig, zero, tpm=True)
            self.assertEqual(rc, 0)
            fb.assert_not_called(); ul.assert_not_called(); self.plain.assert_not_called(); keep.assert_not_called()
            self.assertEqual(ws.call_args.kwargs["state"], "reset-pending")



class RecoveryKit(unittest.TestCase):
    def test_handoff_stays_root_only_and_does_not_follow_links(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unrelated"
            target.write_text("untouched")
            key = Path(directory) / "data-recovery-key"
            key.symlink_to(target)
            with mock.patch.multiple(de, RUN=directory, RECOVERY_FILE=str(key)):
                de.keep_recovery_key(RECOVERY)
            self.assertEqual(target.read_text(), "untouched")
            self.assertFalse(key.is_symlink())
            self.assertEqual(key.stat().st_uid, os.geteuid())
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(key.read_text(), RECOVERY + "\n")
            self.assertCountEqual(Path(directory).iterdir(), [target, key])

    def test_lost_ram_handoff_is_recovered_using_existing_disk_unlock(self):
        actual_exists = os.path.exists
        for tpm, secret in ((True, None), (False, PASSPHRASE), (False, RECOVERY)):
            with self.subTest(tpm=tpm, passphrase=secret == PASSPHRASE), tempfile.TemporaryDirectory() as directory:
                key = Path(directory) / "data-recovery-key"
                runner = FakeRunner()
                answers = {"uuid": "CRYPT-LUKS2-test", "name": "onemind-data"}
                prompt = mock.Mock(return_value=secret)
                with mock.patch.multiple(de, RUN=directory, RECOVERY_FILE=str(key)), \
                     mock.patch.object(de.os, "geteuid", return_value=0), \
                     mock.patch.object(de.sys.stdin, "isatty", return_value=True), \
                     mock.patch.object(de.os.path, "exists", side_effect=lambda p: tpm if p == de.TPM_DEV
                                       else actual_exists(p)), \
                     mock.patch.object(de.os.path, "realpath", return_value="/dev/dm-0"), \
                     mock.patch.object(de, "read_sysfs", side_effect=lambda p: answers.get(p.split("/")[-1])), \
                     mock.patch.object(de.os, "listdir", return_value=["test-partition"]), \
                     mock.patch("builtins.print") as printed:
                    self.assertEqual(de.recover_kit(runner=runner, prompt=prompt), 0)
                self.assertEqual(key.read_text().strip(), RECOVERY)
                self.assertEqual(key.stat().st_mode & 0o777, 0o600)
                self.assertEqual(runner.lines()[-1], "systemctl restart onemind-gateway.service")
                if tpm:
                    self.assertIn("--unlock-tpm2-device=auto --recovery-key /dev/test-partition", runner.lines()[0])
                    prompt.assert_not_called()
                else:
                    method = "--unlock-key-file=/dev/stdin" if secret == PASSPHRASE else "--test-passphrase --key-file -"
                    self.assertIn(method + (" --recovery-key" if secret == PASSPHRASE else "") + " /dev/test-partition",
                                  runner.lines()[0])
                    self.assertEqual(runner.calls[0][1], secret)
                    prompt.assert_called_once()
                for secret in (RECOVERY, PASSPHRASE):
                    self.assertNotIn(secret, repr(printed.call_args_list))
                    self.assertNotIn(secret, repr(runner.lines()))


class Wiring(unittest.TestCase):
    def test_gateway_alone_gets_the_open_disk_key_descriptor(self):
        units = Path(ROOT, "os/rootfs/layers/onemind/usr/lib/systemd/system")
        gateway = units / "onemind-gateway.service"
        handoff = "OpenFile=/run/onemind/data-recovery-key:data-recovery-key:graceful"
        self.assertIn(handoff, gateway.read_text())
        self.assertIn("ONEMIND_IDENTITY_RECOVERY_DISK_STATE_FILE=/run/onemind/data-crypt.json", gateway.read_text())
        self.assertNotIn("gateway-recovery-key", gateway.read_text())
        for unit in units.glob("*.service"):
            if unit != gateway:
                self.assertNotIn("/run/onemind/data-recovery-key", unit.read_text())

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

    def test_storage_is_its_own_mount_unit_that_only_a_btrfs_box_runs(self):
        """@storage is mounted by a unit, not an fstab line: ext4 would refuse subvol=, and a failed mount must not fail
        local-fs.target. The unit is skipped unless data_encrypt.py made its mount point inside @."""
        unit = rd("os/rootfs/layers/base/usr/lib/systemd/system/data-storage.mount")
        self.assertIn("Where=/data/storage", unit)
        self.assertIn("subvol=@storage", unit)
        self.assertIn("ConditionPathExists=/data/storage", unit)
        self.assertIn("After=data.mount", unit)
        self.assertIn("ConditionPathIsMountPoint=/data", unit)
        self.assertNotRegex(unit, r"(?m)^(RequiresMountsFor|Requires|BindsTo)=")   # a missing disk skips it, never fails it
        self.assertIn("WantedBy=local-fs.target", unit)
        self.assertNotIn("RequiredBy", unit)
        link = os.path.join(ROOT, "os/rootfs/layers/base/usr/lib/systemd/system/local-fs.target.wants/data-storage.mount")
        self.assertEqual(os.readlink(link), "../data-storage.mount")
        fstab_lines = [l for l in rd("os/rootfs/layers/base/etc/fstab").splitlines() if not l.lstrip().startswith("#")]
        self.assertFalse(any("/data/storage" in l for l in fstab_lines))
        # nothing but data_encrypt.py makes /data/storage, so an ext4 box never gets the mount
        self.assertNotIn("/data/storage", rd("os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-layout.service"))

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

    def test_the_grow_service_knows_the_encrypted_volume(self):
        """It used to skip an encrypted volume ("not grown yet"); now it grows partition, LUKS2 and btrfs (E7)."""
        src = rd("os/rootfs/layers/base/usr/lib/onemind/data_extend.py")
        self.assertIn('startswith("dm-")', src)
        self.assertIn('"cryptsetup", "resize"', src)
        self.assertNotIn("not grown yet", src)

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

    def test_x86_64_efi_and_cloud_proxmox_ship_the_data_partition_blank_and_the_rest_stay_ext4(self):
        """D-020: the boards of plan PR 5 ship it blank (the box makes LUKS2 + btrfs, or plain btrfs without a TPM);
        every other board keeps ext4 until its own change, and only those two carry OneMind's own type GUID."""
        import yaml
        boards = os.path.join(ROOT, "os", "boards")
        blank = {"x86_64-efi", "x86_64-efi-nvidia", "cloud-proxmox"}   # nvidia is x86_64-efi with a GPU: the same layout
        seen = set()
        for b in sorted(os.listdir(boards)):
            f = os.path.join(boards, b, "layout.yaml")
            if os.path.exists(f):
                for p in yaml.safe_load(open(f))["partitions"]:
                    if p.get("label") != "onemind-data":
                        continue
                    seen.add(b)
                    self.assertEqual(p.get("fs", "ext4"), "luks2" if b in blank else "ext4", b)
                    self.assertEqual(p["type"], "data" if b in blank else p["type"], b)
                    if b not in blank:
                        self.assertNotEqual(p["type"], "data", b)
        self.assertTrue(blank <= seen)

    def test_the_data_partition_has_its_own_type_guid_not_the_generic_linux_one(self):
        import assemble, uuid
        self.assertNotEqual(assemble.GPT_TYPES["data"].upper(), "0FC63DAF-8483-4772-8E79-3D69D8477DE4")
        self.assertNotEqual(assemble.GPT_TYPES["data"], assemble.GPT_TYPES["linux"])
        self.assertEqual(assemble.GPT_TYPES["data"], str(uuid.uuid5(assemble.PU_NS, "onemind-data-partition-type")))
        # not a Discoverable Partitions Spec type: systemd-gpt-auto-generator must not mount it by itself
        dps = {"3b8f8425-20e0-4f3b-907f-1a25a76f98e8",   # /srv
               "773f91ef-66d4-49b5-bd83-d683bf40ad16",   # /var/tmp
               "4d21b016-b534-45c2-a9fb-5c16e091fd2d",   # /var
               "933ac7e1-2eb4-4f13-b844-0e14e2aef915",   # /home
               "0fc63daf-8483-4772-8e79-3d69d8477de4"}   # generic Linux data
        self.assertNotIn(assemble.GPT_TYPES["data"].lower(), dps)

    def test_sgdisk_accepts_the_guid_and_the_layout_validates(self):
        import assemble
        lay = assemble.load_board("x86_64-efi")["layout_data"]
        self.assertEqual(assemble.part(lay, "onemind-data")["type"], "data")
        self.assertEqual(assemble.part(lay, "onemind-data")["fs"], "luks2")

    def test_the_criteria_file_matches_its_preregistered_hash(self):
        want = [l.split()[0] for l in rd("test/qemu/PREREGISTRATION.sha256").splitlines() if "CRITERIA-DATAENC.md" in l]
        self.assertEqual(len(want), 1)
        have = hashlib.sha256(open(os.path.join(ROOT, "test", "qemu", "CRITERIA-DATAENC.md"), "rb").read()).hexdigest()
        self.assertEqual(have, want[0])

    def test_the_reset_criteria_are_preregistered_and_the_harness_runs_them(self):
        h = hashlib.sha256(open(os.path.join(ROOT, "test", "qemu", "CRITERIA-DATARESET.md"), "rb").read()).hexdigest()
        self.assertIn(f"{h}  CRITERIA-DATARESET.md", rd("test/qemu/PREREGISTRATION.sha256"))
        harness = rd("test/qemu/dataenc.py")
        self.assertIn("reset_tests(a, logf)", harness)
        for tid in ("R1", "R2"):
            self.assertIn(f'record("{tid}"', harness)


class ResetArmed(unittest.TestCase):
    """reset_armed: look at the ESP read-only for the marker, any doubt means a normal boot."""
    def probe(self, marker, mount_rc=0):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        node, probe = os.path.join(tmp, "esp-node"), os.path.join(tmp, "probe")
        open(node, "w").close()
        calls = []

        def runner(cmd, input=None, check=True):
            calls.append(cmd)
            if cmd[0] == "mount" and mount_rc == 0 and marker:
                os.makedirs(os.path.join(probe, "onemind"), exist_ok=True)
                open(os.path.join(probe, "onemind", "factory-reset"), "w").close()
            return subprocess.CompletedProcess(cmd, mount_rc if cmd[0] == "mount" else 0, stdout="", stderr="")
        return de.reset_armed(runner, node, probe), calls

    def test_armed_marker_is_seen_and_the_esp_is_unmounted_again(self):
        armed, calls = self.probe(True)
        self.assertTrue(armed)
        self.assertIn("ro", calls[0][2].split(","))
        self.assertEqual(calls[-1][0], "umount")

    def test_no_marker_or_no_esp_or_a_failed_mount_is_a_normal_boot(self):
        self.assertFalse(self.probe(False)[0])
        self.assertFalse(self.probe(True, mount_rc=32)[0])
        self.assertFalse(de.reset_armed(lambda *a, **k: self.fail("no ESP: nothing to mount"), "/nonexistent/esp", "/nonexistent/p"))


if __name__ == "__main__":
    unittest.main()
