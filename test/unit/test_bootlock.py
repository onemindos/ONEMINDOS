# SPDX-License-Identifier: Apache-2.0
"""GRUB boot menu lock (security review 2026-11-21, item 6): os/assemble/grub.cfg.in, ensure_boot_lock in
onemind_firstboot.py, and the QEMU criteria that judge them (test/qemu/CRITERIA-BOOTLOCK.md).
The boot test itself (bootlock.py) needs QEMU and runs in CI's image workflow."""
import hashlib, os, re, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind"))
import onemind_firstboot as fb  # noqa: E402

CFG = open(os.path.join(ROOT, "os", "assemble", "grub.cfg.in")).read()


class GrubCfg(unittest.TestCase):
    def test_every_entry_boots_without_a_password(self):
        entries = re.findall(r"^menuentry .*$", CFG, re.M)
        self.assertEqual(len(entries), 3)
        for e in entries:
            self.assertIn("--unrestricted", e, e)

    def test_superuser_is_set_before_the_first_entry_and_the_hash_is_not_in_the_file(self):
        self.assertLess(CFG.index('set superusers="onemind"'), CFG.index("menuentry "))
        self.assertLess(CFG.index("source ($esp)/EFI/BOOT/user.cfg"), CFG.index("menuentry "))
        self.assertNotIn("grub.pbkdf2", CFG)
        self.assertEqual(len(re.findall(r"^\s*password", CFG, re.M)), 0, "the password line belongs in user.cfg only")

    def test_user_cfg_is_sourced_only_when_it_exists_and_modules_are_loaded(self):
        self.assertRegex(CFG, r"if \[ -f \(\$esp\)/EFI/BOOT/user\.cfg \]; then\n\s+source")
        self.assertLess(CFG.index("insmod password_pbkdf2"), CFG.index("source ($esp)"))
        self.assertIn("insmod gcry_sha512", CFG)

    def test_the_superuser_is_never_blanked(self):
        self.assertNotIn("set superusers=\"\"", CFG)


class Hash(unittest.TestCase):
    def test_known_format_and_value(self):
        salt = bytes(range(64))
        line = fb.grub_pbkdf2("abc", salt, 1000)
        want = hashlib.pbkdf2_hmac("sha512", b"abc", salt, 1000, 64).hex().upper()
        self.assertEqual(line, f"grub.pbkdf2.sha512.1000.{salt.hex().upper()}.{want}")
        self.assertRegex(fb.grub_pbkdf2("x"), r"^grub\.pbkdf2\.sha512\.10000\.[0-9A-F]{128}\.[0-9A-F]{128}$")

    def test_salt_is_random_per_call(self):
        self.assertNotEqual(fb.grub_pbkdf2("same"), fb.grub_pbkdf2("same"))

    def test_password_shape_and_uniqueness(self):
        pws = {fb.boot_password() for _ in range(50)}
        self.assertEqual(len(pws), 50)
        for pw in pws:
            self.assertRegex(pw, r"^[a-hj-km-np-z2-9]{4}(-[a-hj-km-np-z2-9]{4}){4}$")


class EnsureBootLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = fb.Paths(self.tmp.name)

    def esp(self):
        os.makedirs(self.p.esp_boot)

    def test_writes_only_the_hash_and_the_password_verifies(self):
        self.esp()
        pw = fb.ensure_boot_lock(self.p)
        text = open(self.p.esp_user_cfg).read()
        self.assertEqual(len(text.splitlines()), 1)
        self.assertNotIn(pw, text)
        m = re.fullmatch(r"password_pbkdf2 onemind grub\.pbkdf2\.sha512\.(\d+)\.([0-9A-F]+)\.([0-9A-F]+)\n", text)
        self.assertTrue(m, text)
        again = hashlib.pbkdf2_hmac("sha512", pw.encode(), bytes.fromhex(m.group(2)), int(m.group(1)), 64).hex().upper()
        self.assertEqual(again, m.group(3))
        self.assertEqual(os.stat(self.p.esp_user_cfg).st_mode & 0o777, 0o600)

    def test_second_call_keeps_the_first_password(self):
        self.esp()
        fb.ensure_boot_lock(self.p)
        before = open(self.p.esp_user_cfg).read()
        self.assertIsNone(fb.ensure_boot_lock(self.p))
        self.assertEqual(open(self.p.esp_user_cfg).read(), before)

    def test_two_boxes_get_different_passwords_and_hashes(self):
        self.esp()
        a = fb.ensure_boot_lock(self.p)
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        q = fb.Paths(other.name)
        os.makedirs(q.esp_boot)
        b = fb.ensure_boot_lock(q)
        self.assertNotEqual(a, b)
        self.assertNotEqual(open(self.p.esp_user_cfg).read(), open(q.esp_user_cfg).read())

    def test_no_grub_esp_means_nothing_is_written(self):
        self.assertIsNone(fb.ensure_boot_lock(self.p))
        self.assertFalse(os.path.exists(self.p.esp_user_cfg))

    def test_an_unwritable_esp_does_not_break_first_boot(self):
        self.esp()
        orig = fb.write
        fb.write = lambda *a, **k: (_ for _ in ()).throw(OSError("read-only file system"))
        self.addCleanup(setattr, fb, "write", orig)
        self.assertIsNone(fb.ensure_boot_lock(self.p))


class Criteria(unittest.TestCase):
    def test_criteria_file_matches_a_preregistered_hash(self):
        q = os.path.join(ROOT, "test", "qemu")
        digest = hashlib.sha256(open(os.path.join(q, "CRITERIA-BOOTLOCK.md"), "rb").read()).hexdigest()
        self.assertIn(f"{digest}  CRITERIA-BOOTLOCK.md", open(os.path.join(q, "PREREGISTRATION.sha256")).read())

    def test_harness_compiles_and_covers_every_criterion(self):
        src = open(os.path.join(ROOT, "test", "qemu", "bootlock.py")).read()
        compile(src, "bootlock.py", "exec")
        for tid in ("B1", "B2", "B3", "B4", "B5", "B6"):
            self.assertIn(f'record("{tid}"', src)


def _load_harness():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bootlock_harness", os.path.join(ROOT, "test", "qemu", "bootlock.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeVM:
    """The parts of run-tests.py's VM the GRUB login uses: a serial buffer and the keyboard. After the password's
    Enter, GRUB's answer arrives `delay` seconds later, as GRUB's growing refusal sleep does."""

    def __init__(self, answer, delay):
        import threading
        self.buf, self.lock, self.typed = "", threading.Lock(), []
        self.answer, self.delay, self.timers = answer, delay, []
        vm = self

        class Stdin:
            def write(self, b):
                vm.typed.append(b.decode())
                if len(vm.typed) == 3:          # Ctrl-U, the username, then the password: GRUB starts checking
                    t = threading.Timer(vm.delay, vm.emit, (vm.answer,))
                    t.start()
                    vm.timers.append(t)

            def flush(self):
                pass

        self.proc = type("P", (), {"stdin": Stdin()})()

    def emit(self, text):
        with self.lock:
            self.buf += text

    def here(self):
        with self.lock:
            return len(self.buf)

    def since(self, i):
        with self.lock:
            return self.buf[i:]


class Harness(unittest.TestCase):
    """bootlock.py's own checks (CI run 45547568838 failed B1 and B5 on a correctly locked image)."""

    @classmethod
    def setUpClass(cls):
        cls.h = _load_harness()

    def count(self, text):
        import subprocess
        with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
            f.write(text)
        self.addCleanup(os.unlink, f.name)
        r = subprocess.run(["grep", "-c", "-E", self.h.CFG_PASSWORD_ERE, f.name], capture_output=True, text=True)
        return int(r.stdout.strip())

    def test_b1_grub_cfg_check_ignores_the_module_load(self):
        # The image's grub.cfg loads the password_pbkdf2 module; loading it sets no password (was hash_in_grub_cfg=1).
        self.assertIn("insmod password_pbkdf2", CFG)
        self.assertEqual(self.count(CFG), 0)

    def test_b1_grub_cfg_check_still_catches_a_password_in_the_image(self):
        line = fb.grub_pbkdf2("x")
        self.assertEqual(self.count(CFG + f"password_pbkdf2 onemind {line}\n"), 1)
        self.assertEqual(self.count(CFG + "    password onemind clear-text\n"), 1)
        self.assertEqual(self.count(CFG + f"set hidden={line}\n"), 1)
        self.assertEqual(self.count(CFG + f"\tpassword_pbkdf2 root {line}\n"), 1)

    def test_login_waits_for_grub_s_doubled_refusal(self):
        # B5 is GRUB's second refusal in a row: it sleeps 2 s, longer than the old fixed 1.5 s wait.
        vm = FakeVM("\nerror: access denied.\n", 2.2)
        start, t0 = vm.here(), time.time()
        self.h.login(vm, "onemind", "wrong-password", f"{self.h.DENIED}|grub> ")
        self.assertTrue(self.h.seen(vm, start, self.h.DENIED))
        self.assertLess(time.time() - t0, 10, "login returns once GRUB answers, not after the full timeout")
        self.assertEqual(vm.typed, ["\x15", "onemind\r", "wrong-password\r"])

    def test_login_waits_for_the_editor_after_the_right_password(self):
        vm = FakeVM("Minimum Emacs-like screen editing is supported.", 1.8)
        start = vm.here()
        self.h.login(vm, "onemind", "pw", f"{self.h.EDITOR}|{self.h.DENIED}")
        self.assertTrue(self.h.seen(vm, start, self.h.EDITOR))

    def test_no_answer_gives_up_after_the_timeout(self):
        vm = FakeVM("", 0)
        t0 = time.time()
        self.assertFalse(self.h.answered(vm, 0, "access denied", timeout=0.5))
        self.assertLess(time.time() - t0, 5)

    def test_the_wait_fits_the_criteria_prompt_timeout(self):
        self.assertLessEqual(self.h.ANSWER_TIMEOUT, 60)   # CRITERIA-BOOTLOCK.md §1: each GRUB prompt 60 s


GATE_LINE = "HEALTH-GATE: onemind-health-gate RESULT committed-boot slot=A version=1\n"
ALREADY_LINE = "ONEMIND-FIRSTBOOT: already configured role=hub node_id=0123456789ab\n"


def reboot_vm(h, after_reboot):
    """run-tests.py's real VM (expect, wait_gate) with no QEMU: B1's boot is in the buffer and already read;
    "systemctl reboot" makes the next boot's lines arrive 0.1 s later, in the order given."""
    import threading
    vm = h.battery.VM.__new__(h.battery.VM)
    vm.buf = "boot one\n" + GATE_LINE + "ONEMIND-FIRSTBOOT: configured role=hub source=nocloud\nroot@onemind:~# __RC=0__\n"
    vm.pos, vm.lock, vm.failfast, vm._watch = len(vm.buf), threading.Lock(), False, None

    def emit():
        with vm.lock:
            vm.buf += after_reboot

    class Stdin:
        def write(self, b):
            if b.decode().strip() == "systemctl reboot":
                threading.Timer(0.1, emit).start()

        def flush(self):
            pass
    vm.proc = type("P", (), {"stdin": Stdin(), "returncode": None, "poll": lambda self: None})()
    return vm


class B2Reboot(unittest.TestCase):
    """B2's reboot (#1150, #1159): the committed-boot gate line can come before "already configured"."""

    @classmethod
    def setUpClass(cls):
        cls.h = _load_harness()

    def test_gate_line_before_already_is_found(self):
        vm = reboot_vm(self.h, "reboot\n" + GATE_LINE + ALREADY_LINE)
        t0 = time.time()
        seg, al, gate = self.h.reboot_and_wait(vm, timeout=5, gate_timeout=5)
        self.assertEqual(gate, ("committed-boot", "A", "1"))
        self.assertTrue(al.startswith("ONEMIND-FIRSTBOOT: already configured role=hub"))
        self.assertLess(time.time() - t0, 4)

    def test_gate_line_after_already_is_found(self):
        vm = reboot_vm(self.h, "reboot\n" + ALREADY_LINE + GATE_LINE)
        self.assertEqual(self.h.reboot_and_wait(vm, timeout=5, gate_timeout=5)[2], ("committed-boot", "A", "1"))

    def test_the_old_order_of_waits_misses_an_early_gate_line(self):
        vm = reboot_vm(self.h, "reboot\n" + GATE_LINE + ALREADY_LINE)
        vm.send("systemctl reboot")
        vm.expect(self.h.fb.ALREADY, 5)
        with self.assertRaises(TimeoutError):
            vm.wait_gate(1)

    def test_b1_s_gate_line_does_not_count_for_b2(self):
        vm = reboot_vm(self.h, "reboot\n" + ALREADY_LINE)
        with self.assertRaises(TimeoutError):
            self.h.reboot_and_wait(vm, timeout=5, gate_timeout=1)

    def test_already_configured_is_still_required(self):
        vm = reboot_vm(self.h, "reboot\n" + GATE_LINE)
        with self.assertRaises(TimeoutError):
            self.h.reboot_and_wait(vm, timeout=1, gate_timeout=1)

    def test_b2_uses_the_helper(self):
        with open(os.path.join(ROOT, "test", "qemu", "bootlock.py")) as f:
            src = f.read()
        b2 = src[src.index('vm.mark("B2 a normal boot needs nothing")'):src.index('record("B2"')]
        self.assertIn("reboot_and_wait(vm)", b2)
        self.assertNotIn("fb.ALREADY", b2)


if __name__ == "__main__":
    unittest.main()
