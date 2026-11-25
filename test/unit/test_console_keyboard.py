# SPDX-License-Identifier: Apache-2.0
"""Step 3 lane "video and console": VA-API packages on the x86 boards only, and the console keyboard layout
kept on /data (os/rootfs/layers/base/usr/lib/onemind/onemind-console-keyboard). The QEMU proof is first-boot
checks F29-F31 (test/qemu/CRITERIA-FIRSTBOOT.md section 23); here, the script's behaviour with stub tools and the wiring."""
import hashlib, os, re, stat, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


BASE = os.path.join("os", "rootfs", "layers", "base")
SCRIPT = os.path.join(ROOT, BASE, "usr", "lib", "onemind", "onemind-console-keyboard")
DEFAULT = os.path.join(ROOT, BASE, "usr", "lib", "onemind", "console-keyboard.default")


def words(path):
    out = []
    for line in rd(path).splitlines():
        out += line.split("#")[0].split()
    return out


class Script(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.log = os.path.join(t, "calls")
        # ckbcomp prints its arguments (what the keymap would be built from); loadkeys records its own and what it read.
        self.stub("ckbcomp", 'echo "ckbcomp $*" >> "$LOG"; echo KEYMAP')
        self.stub("loadkeys", 'echo "loadkeys $*" >> "$LOG"; for f in "$@"; do [ -f "$f" ] && cat "$f" >> "$LOG"; done; exit 0')
        self.dir = os.path.join(t, "data", "console")

    def tearDown(self):
        self.tmp.cleanup()

    def stub(self, name, body):
        p = os.path.join(self.tmp.name, name)
        open(p, "w").write("#!/bin/sh\n" + body + "\n")
        os.chmod(p, 0o755)

    def run_script(self, default=DEFAULT, **env):
        e = dict(os.environ, LOG=self.log, ONEMIND_CONSOLE_DIR=self.dir,
                 ONEMIND_CKBCOMP=os.path.join(self.tmp.name, "ckbcomp"),
                 ONEMIND_LOADKEYS=os.path.join(self.tmp.name, "loadkeys"),
                 ONEMIND_CONSOLE_DEV="/dev/tty0", ONEMIND_CONSOLE_DEFAULT=default, ONEMIND_TMP=self.tmp.name)
        e.update(env)
        r = subprocess.run(["sh", SCRIPT], capture_output=True, text=True, env=e)
        calls = ""
        if os.path.exists(self.log):
            with open(self.log) as f:
                calls = f.read()
        return r, calls

    def test_script_is_executable_posix_sh(self):
        self.assertTrue(os.stat(SCRIPT).st_mode & stat.S_IXUSR)
        self.assertEqual(rd(BASE, "usr/lib/onemind/onemind-console-keyboard").splitlines()[0], "#!/bin/sh")
        self.assertEqual(subprocess.run(["sh", "-n", SCRIPT]).returncode, 0)

    def test_fresh_data_is_seeded_with_us_and_loaded(self):
        r, calls = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        seeded = rd(os.path.relpath(os.path.join(self.dir, "keyboard"), ROOT))
        self.assertIn('XKBLAYOUT="us"', seeded)
        self.assertIn("ckbcomp -model pc105 -layout us -variant  -option ", calls)
        self.assertRegex(calls, r"loadkeys -q -C /dev/tty0 \S+console-keymap\.")
        self.assertIn("KEYMAP", calls)   # the keymap really flows from ckbcomp into loadkeys

    def test_owner_layout_in_data_is_used_and_not_overwritten(self):
        os.makedirs(self.dir)
        path = os.path.join(self.dir, "keyboard")
        body = 'XKBMODEL="pc105"\nXKBLAYOUT="de"\nXKBVARIANT="nodeadkeys"\nXKBOPTIONS="caps:escape"\n'
        open(path, "w").write(body)
        r, calls = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ckbcomp -model pc105 -layout de -variant nodeadkeys -option caps:escape", calls)
        self.assertEqual(open(path).read(), body)

    def test_unquoted_and_commented_values_parse(self):
        os.makedirs(self.dir)
        open(os.path.join(self.dir, "keyboard"), "w").write("# note\nXKBLAYOUT=fr\n")
        _, calls = self.run_script()
        self.assertIn("-layout fr ", calls)

    def test_hostile_values_are_refused_and_fall_back_to_us(self):
        os.makedirs(self.dir)
        marker = os.path.join(self.tmp.name, "pwned")
        open(os.path.join(self.dir, "keyboard"), "w").write(f'XKBLAYOUT="de; touch {marker}"\nXKBOPTIONS="$(touch {marker})"\n')
        r, calls = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(marker))
        self.assertIn("refusing", r.stdout)
        self.assertIn("-layout us ", calls)

    def test_unwritable_data_still_loads_us_and_writes_nothing(self):
        blocker = os.path.join(self.tmp.name, "file")
        open(blocker, "w").write("x")
        self.dir = os.path.join(blocker, "console")   # a path below a regular file cannot be made
        r, calls = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("using the US default for this boot", r.stdout)
        self.assertIn("-layout us ", calls)

    def test_a_failing_keymap_build_fails_the_service(self):
        self.stub("ckbcomp", "exit 3")
        r, _ = self.run_script()
        self.assertNotEqual(r.returncode, 0)   # sh has no pipefail: the script must not pipe
        self.assertNotIn("loaded", r.stdout)

    def test_default_seed_is_us_pc105(self):
        seed = open(DEFAULT).read()
        for line in ('XKBMODEL="pc105"', 'XKBLAYOUT="us"', 'XKBVARIANT=""', 'XKBOPTIONS=""'):
            self.assertIn(line, seed)


class Wiring(unittest.TestCase):
    def test_unit_runs_the_script_early_and_is_enabled(self):
        unit = rd(BASE, "usr/lib/systemd/system/onemind-console-keyboard.service")
        self.assertIn("ExecStart=/usr/lib/onemind/onemind-console-keyboard", unit)
        self.assertIn("Type=oneshot", unit)
        self.assertIn("After=local-fs.target onemind-data-layout.service", unit)
        self.assertIn("Before=sysinit.target getty.target", unit)
        link = os.path.join(ROOT, BASE, "usr/lib/systemd/system/sysinit.target.wants/onemind-console-keyboard.service")
        self.assertEqual(os.readlink(link), "../onemind-console-keyboard.service")

    def test_state_is_on_data_only(self):
        # The script and unit write only below /data (the root is read-only); nothing under /etc.
        s = rd(BASE, "usr/lib/onemind/onemind-console-keyboard")
        self.assertIn("/data/onemind/console", s)
        self.assertNotIn("setupcon", s.replace("# ", "#").split("set -eu")[1])
        self.assertNotIn("/etc/", s.split("set -eu")[1])

    def test_console_setup_units_that_write_etc_are_masked(self):
        cf = rd("os", "rootfs", "Containerfile")
        self.assertIn("systemctl mask console-setup.service keyboard-setup.service", cf)

    def test_packages_in_both_legs(self):
        for leg in ("debian", "ubuntu"):
            w = words(f"os/rootfs/packages/{leg}-common.txt")
            for p in ("console-setup", "keyboard-configuration"):
                self.assertIn(p, w, f"{p} missing from {leg}-common.txt")

    def test_va_api_only_on_the_x86_boards_not_on_cloud(self):
        va = {"intel-media-va-driver", "mesa-va-drivers", "vainfo"}
        for b in ("x86_64-efi", "x86_64-efi-nvidia"):
            self.assertTrue(va <= set(words(f"os/boards/{b}/packages-debian.txt")), b)
        self.assertTrue(va <= set(words("os/boards/x86_64-efi/packages-ubuntu.txt")))
        for b in sorted(os.listdir(os.path.join(ROOT, "os", "boards"))):
            if b.startswith("cloud") or b in ("vm", "vm-do", "arm64-efi", "rpi5", "jetson-orin"):
                for f in os.listdir(os.path.join(ROOT, "os", "boards", b)):
                    if f.startswith("packages-"):
                        self.assertFalse(va & set(words(f"os/boards/{b}/{f}")), f"{b}/{f}")
        for common in ("debian-common", "debian-amd64", "debian-arm64", "ubuntu-common", "ubuntu-amd64"):
            self.assertFalse(va & set(words(f"os/rootfs/packages/{common}.txt")), common)

    def test_only_free_packages_no_non_free_va_driver(self):
        for f in ("os/boards/x86_64-efi/packages-debian.txt", "os/boards/x86_64-efi-nvidia/packages-debian.txt"):
            self.assertNotIn("intel-media-va-driver-non-free", words(f))
            self.assertNotIn("i965-va-driver-shaders", words(f))


class Checks(unittest.TestCase):
    FB = rd("test", "qemu", "firstboot.py")
    CRIT = rd("test", "qemu", "CRITERIA-FIRSTBOOT.md")

    def test_f29_runs_only_on_the_va_api_boards(self):
        # arm64-efi, vm and vm-do carry no VA-API packages, so F29 there would always fail.
        m = re.search(r"VAAPI_BOARDS = \(([^)]*)\)", self.FB)
        boards = re.findall(r'"([^"]+)"', m.group(1))
        self.assertIn("x86_64-efi", boards)
        for b in ("arm64-efi", "vm", "vm-do"):
            self.assertNotIn(b, boards)
        for b in boards:
            self.assertIn("vainfo", words(f"os/boards/{b}/packages-debian.txt"), b)
        self.assertRegex(self.FB, r"if a\.board in VAAPI_BOARDS:\n\s+vm\.mark\(\"F29[^\n]*f29\(vm\)")

    def test_console_keyboard_unit_drops_unneeded_capabilities(self):
        u = rd(BASE, "usr/lib/systemd/system/onemind-console-keyboard.service")
        self.assertIn("CapabilityBoundingSet=CAP_SYS_TTY_CONFIG CAP_DAC_OVERRIDE\n", u)
        self.assertNotIn("CAP_CHOWN", u)
        self.assertNotIn("CAP_FOWNER", u)

    def test_checks_are_preregistered_with_a_recorded_hash(self):
        h = hashlib.sha256(self.CRIT.encode()).hexdigest()
        lines = [l.split() for l in rd("test", "qemu", "PREREGISTRATION.sha256").splitlines() if "CRITERIA-FIRSTBOOT.md" in l]
        self.assertIn(h, [l[0] for l in lines])
        for t in ("| F29 |", "| F30 |", "| F31 |"):
            self.assertIn(t, self.CRIT)

    def test_checks_are_wired_in_the_right_order(self):
        i = self.FB.index
        self.assertLess(i("f29(vm)"), i("pre30 = f30_before(vm)"))
        self.assertLess(i("pre30 = f30_before(vm)"), i('vm.mark("F3 reboot keeps state")'))
        self.assertLess(i('vm.mark("F3 reboot keeps state")'), i("f30_after(vm, pre30)"))
        self.assertLess(i("f30_after(vm, pre30)"), i('vm.mark("F4 A/B update keeps /data")'))
        self.assertLess(i('vm.mark("F4 A/B update keeps /data")'), self.FB.rindex("f31(vm)"))
        for rec in ('record("F29"', 'record("F30"', 'record("F31"'):
            self.assertIn(rec, self.FB)

    def test_f29_says_no_gpu_in_qemu(self):
        self.assertIn("no GPU in QEMU", self.FB[self.FB.index("def f29("):self.FB.index("def console_state(")])


if __name__ == "__main__":
    unittest.main()
