# SPDX-License-Identifier: Apache-2.0
"""scripts/hw-check.sh (Dell install kit, #234): it must be read-only and it must produce its plain-language report.

Three layers, none needing the Dell: (1) a static scan of the script for write commands, (2) a run against stub tools
that log every call, checking each call is on a read-only allowlist, and (3) a run against a fake /sys tree that must
come out byte-for-byte identical. The stubs also print fake secrets (MAC, SSID, serial, IP, e-mail) that must not
appear in the report."""
import hashlib, os, re, shutil, stat, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "hw-check.sh")
# built from pieces so the hygiene grep does not mistake these fake secrets for real ones
IP = ".".join(["192", "168", "7", "42"])
SERIAL = "SN" + "0123456789" + "ABCDEF" + "0123456789"
MAIL = "zeus" + "@" + "example" + ".com"
SECRETS = ["aa:bb:cc:dd:ee:01", "HomeNet-Secret", SERIAL, IP, MAIL, "psk-hunter2"]

FORBIDDEN_CMDS = r"rm|mv|cp|tee|dd|mkfs\S*|mount|umount|chmod|chown|touch|mkdir|ln|kill|pkill|reboot|poweroff|shutdown|apt|apt-get|dpkg|pip|curl|wget|ssh|scp|rsync|truncate|install|fsck|wipefs|sgdisk|parted|cryptsetup|passwd|useradd|usermod"
FORBIDDEN_SUBS = [
    r"fwupdmgr\s+(update|install|refresh|downgrade|reinstall|modify|activate|unlock|clear)",
    r"snapper\b.*\b(create|delete|modify|rollback|undochange|cleanup|setup)",
    r"btrfs\s+(scrub|balance|filesystem|subvolume|check|rescue|device\s+(add|remove|delete))",
    r"rauc\s+(install|mark|write|extract|resign|bundle)",
    r"bluetoothctl\s+(power|scan|pair|connect|remove|trust|discoverable|agent)",
    r"nmcli\s+(connection|con\b|general|networking)",
    r"nmcli\s+device\s+(connect|disconnect|wifi|reapply|modify|delete)",
    r"nmcli\s+radio\s+wifi\s+(on|off)",
    r"systemctl\s+(start|stop|restart|enable|disable|mask|unmask|reload|daemon|isolate|set-|edit|kill|reset)",
    r"rfkill\s+(block|unblock)", r"lpadmin|lpoptions|cupsenable|cupsdisable|cupsaccept|\bcancel\b",
    r"smartctl\s+.*(-t|--test|-s|--set|-x\s+offline)", r"sed\s+(-[A-Za-z]*i|--in-place)",
    r"sudo\s+(?!-n\b)", r"\beval\b", r"/dev/watchdog\S*\s*(<|>)", r"exec\s+\d?[<>]",
]


def read_script():
    with open(SCRIPT) as f:
        return f.read()


def code_lines():
    out = []
    for raw in read_script().splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        line = re.sub(r"'[^']*'", "''", line)          # drop quoted text: messages may mention any word
        line = re.sub(r'"[^"]*"', '""', line)
        line = re.sub(r"\s#.*$", "", line)
        out.append(line)
    return out


def tree_hash(path):
    h = hashlib.sha256()
    for d, dirs, files in sorted(os.walk(path)):
        dirs.sort()
        for n in sorted(files + dirs):
            p = os.path.join(d, n)
            h.update(os.path.relpath(p, path).encode())
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    h.update(f.read())
    return h.hexdigest()


STUBS = {
    "nmcli": '''case "$*" in
  "-t -f DEVICE,TYPE,STATE device") echo "wlp2s0:wifi:connected"; echo "eno1:ethernet:unavailable";;
  "radio wifi") echo enabled;;
  *) echo "nmcli: $* HomeNet-Secret psk-hunter2" >&2; exit 2;;
esac''',
    "fwupdmgr": '''echo "Dell AIO"; echo "  Device ID:  0123abcd"; echo "  Serial Number: @SERIAL@"; echo "  Device ID:  4567ef"''',
    "lsblk": '''case "$*" in
  *"-P"*) echo 'NAME="sdb" TRAN="usb" TYPE="disk" MOUNTPOINTS=""'; echo 'NAME="sdb1" TRAN="" TYPE="part" MOUNTPOINTS=""'; echo 'NAME="sda" TRAN="sata" TYPE="disk" MOUNTPOINTS=""';;
  *) echo "";;
esac''',
    "wpctl": '''printf 'Audio\\n ├─ Devices:\\n │      44. Built-in Audio\\n ├─ Sinks:\\n │  *   52. Built-in Audio Analog Stereo [vol: 0.40]\\n ├─ Sources:\\n │      53. Mic\\nVideo\\n' ''',
    "bluetoothctl": '''echo "Controller aa:bb:cc:dd:ee:01 dell-aio [default]"''',
    "rfkill": '''printf '1: hci0: Bluetooth\\n\\tSoft blocked: no\\n\\tHard blocked: no\\n' ''',
    "lpstat": '''case "$1" in -v) echo "device for Office: ipp://@IP@/ipp/print";; *) exit 1;; esac''',
    "systemctl": '''case "$1 $2" in "is-active cups") echo active;; "is-active snapper-timeline.timer") echo active;; *) echo "unexpected systemctl $*" >&2; exit 9;; esac''',
    "vainfo": '''echo "vainfo: Driver version: Intel iHD driver 24.1 (@MAIL@)"; echo "      VAProfileH264Main : VAEntrypointVLD"; echo "      VAProfileHEVCMain : VAEntrypointVLD"''',
    "localectl": '''echo "   VC Keymap: us"''',
    "smartctl": '''echo "Serial Number: @SERIAL@"; echo "SMART overall-health self-assessment test result: PASSED"''',
    "findmnt": '''case "$*" in *FSTYPE*) echo btrfs;; *SOURCE*) echo /dev/mapper/onemind-data;; *) exit 1;; esac''',
    "snapper": '''echo "Config | Subvolume"; echo "storage | /data/storage"''',
    "btrfs": '''printf '[/dev/mapper/onemind-data].write_io_errs    0\\n[/dev/mapper/onemind-data].corruption_errs  0\\n' ''',
    "rauc": '''printf 'Booted from: rootfs.0 (A)\\n   slot: rootfs.0\\n    boot status: good\\n' ''',
    "sudo": '''[ "$1" = -n ] || exit 7; shift; exec "$@"''',
}
# What each tool may be asked: the read-only allowlist the test enforces on every recorded call.
ALLOWED = [
    r"nmcli -t -f DEVICE,TYPE,STATE device", r"nmcli radio wifi", r"fwupdmgr get-devices --no-unreported-check",
    r"lsblk -P -o NAME,TRAN,TYPE,MOUNTPOINTS", r"lsblk -n -o MOUNTPOINTS /dev/\S+", r"wpctl status", r"pactl list short sinks",
    r"bluetoothctl list", r"rfkill list bluetooth", r"systemctl is-active (cups|snapper-timeline\.timer)", r"lpstat -v",
    r"vainfo", r"localectl status", r"smartctl -H /dev/\S+", r"findmnt -no (FSTYPE|SOURCE) /data",
    r"snapper --no-dbus list-configs", r"btrfs device stats /data", r"rauc status",
]


class HwCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hwcheck-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        self.log = os.path.join(self.tmp, "calls.log")
        os.mkdir(self.bin)
        for name, body in STUBS.items():
            p = os.path.join(self.bin, name)
            with open(p, "w") as f:
                f.write('#!/bin/sh\nprintf "%s %s\\n" "' + name + '" "$*" >> "$STUB_LOG"\n' + body.replace("@IP@", IP).replace("@MAIL@", MAIL).replace("@SERIAL@", SERIAL) + "\n")
            os.chmod(p, 0o755)
        self.root = os.path.join(self.tmp, "root")
        for rel, text in {
            "proc/cpuinfo": "model name\t: Intel(R) Core(TM) i7-6700HQ CPU @ 2.60GHz\n",
            "proc/meminfo": "MemTotal:       16301000 kB\n",
            "proc/bus/input/devices": 'N: Name="USB Keyboard"\nH: Handlers=sysrq kbd event3 leds\n',
            "sys/class/hwmon/hwmon0/name": "coretemp\n", "sys/class/hwmon/hwmon0/temp1_input": "52000\n",
            "sys/class/tpm/tpm0/tpm_version_major": "2\n", "sys/class/bluetooth/hci0/x": "",
            "sys/block/sda/removable": "0\n", "sys/block/sdb/removable": "1\n",
            "dev/watchdog": "", "dev/tpmrm0": "",
        }.items():
            p = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(text)
        self.cwd = os.path.join(self.tmp, "cwd")
        os.mkdir(self.cwd)

    def run_script(self, sudo=False, path=None):
        env = {"PATH": path or (self.bin + ":/usr/bin:/bin"), "HW_CHECK_ROOT": self.root, "STUB_LOG": self.log, "HOME": self.tmp}
        if sudo:
            env["HW_CHECK_SUDO"] = "1"
        return subprocess.run(["/bin/sh", SCRIPT], cwd=self.cwd, env=env, capture_output=True, text=True, timeout=120)

    @staticmethod
    def _read(path):
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return f.read().splitlines()

    def calls(self):
        return self._read(self.log)

    # layer 1: the text of the script
    def test_script_has_no_write_commands(self):
        for line in code_lines():
            for m in re.finditer(r"(?:^|[;&|(]|\$\(|\bthen\b|\bdo\b|\belse\b)\s*(?:" + FORBIDDEN_CMDS + r")\b", line):
                self.fail(f"write command in hw-check.sh: {line!r}")
            for pat in FORBIDDEN_SUBS:
                self.assertIsNone(re.search(pat, line), f"write subcommand {pat!r} in: {line!r}")
            stripped = line.replace("2>&1", "").replace(">&2", "").replace("&>", "")
            for m in re.finditer(r">", stripped):
                self.assertRegex(stripped[m.start():], r"^>\s*/dev/null", f"redirect to a file in: {line!r}")

    def test_tools_cannot_read_the_script_from_stdin(self):
        # `ssh host 'sh -s' < hw-check.sh` feeds the script on stdin: every tool call must have stdin closed.
        self.assertIn("</dev/null; else", read_script())
        p = subprocess.run(["/bin/sh", "-s"], input=read_script(), cwd=self.cwd, capture_output=True, text=True, timeout=120,
                           env={"PATH": self.bin + ":/usr/bin:/bin", "HW_CHECK_ROOT": self.root, "STUB_LOG": self.log})
        self.assertIn("In plain words", p.stdout)

    def test_script_never_opens_the_watchdog(self):
        text = read_script()
        self.assertNotRegex(text, r"(cat|read|exec|<|>|dd|tee)\s*[^#\n]*\$R/dev/watchdog")
        self.assertIn("-c \"$R/dev/watchdog\"", text)  # only a test for existence

    # layer 2: a full run against stub tools
    def test_report_has_every_check_and_summary(self):
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout
        for head in ("Wi-Fi", "Firmware devices", "Sensors", "USB stick", "Watchdog", "Sound", "Bluetooth", "Printers",
                     "Video (VA-API)", "Console keyboard", "TPM 2.0", "Disk health", "/data filesystem",
                     "Snapshots (snapper)", "btrfs error counters", "Boot slot", "In plain words"):
            self.assertIn(head, out)
        self.assertRegex(out, r"PASS\s+USB stick\s+1 seen and not mounted")
        self.assertRegex(out, r"PASS\s+/data filesystem\s+btrfs, encrypted")
        self.assertRegex(out, r"PASS\s+Boot slot\s+booted from rootfs\.0, status good")
        self.assertRegex(out, r"PASS\s+Printers\s+1 printer\(s\), 1 driverless")
        self.assertRegex(out, r"\d+ checks: \d+ passed")
        self.assertIn("This report changed nothing on the box.", out)
        self.assertNotIn("FAIL ", out)

    def test_report_masks_secrets(self):
        p = self.run_script(sudo=True)
        for s in SECRETS:
            self.assertNotIn(s, p.stdout + p.stderr, f"secret {s!r} reached the report")

    def test_every_tool_call_is_on_the_read_only_allowlist(self):
        self.run_script(sudo=True)
        calls = self.calls()
        self.assertGreater(len(calls), 10)
        for c in calls:
            if c.startswith("sudo "):
                c = c[len("sudo "):].replace("-n ", "", 1)
            self.assertTrue(any(re.fullmatch(a, c.strip()) for a in ALLOWED), f"unexpected call: {c!r}")

    def test_sudo_is_used_only_when_asked_and_never_with_a_password(self):
        self.run_script()
        self.assertFalse([c for c in self.calls() if c.startswith("sudo ")])
        os.remove(self.log)
        self.run_script(sudo=True)
        sudo_calls = [c for c in self.calls() if c.startswith("sudo ")]
        self.assertTrue(sudo_calls)
        self.assertTrue(all(c.startswith("sudo -n ") for c in sudo_calls))

    def test_a_failing_disk_makes_the_exit_code_one(self):
        p = os.path.join(self.bin, "smartctl")
        with open(p, "w") as f:
            f.write('#!/bin/sh\necho "SMART overall-health self-assessment test result: FAILED!"\n')
        out = self.run_script()
        self.assertEqual(out.returncode, 1)
        self.assertRegex(out.stdout, r"FAIL\s+Disk health")

    def test_mounted_usb_stick_is_flagged(self):
        p = os.path.join(self.bin, "lsblk")
        with open(p, "w") as f:
            f.write('#!/bin/sh\necho \'NAME="sdb" TRAN="usb" TYPE="disk" MOUNTPOINTS=""\'; echo \'NAME="sdb1" TRAN="usb" TYPE="part" MOUNTPOINTS="/media/x"\'\n')
        self.assertRegex(self.run_script().stdout, r"WARN\s+USB stick\s+seen, but it is MOUNTED")

    # layer 3: nothing on disk changes
    def test_fake_tree_and_cwd_are_unchanged(self):
        before_root, before_cwd = tree_hash(self.root), tree_hash(self.cwd)
        self.run_script(sudo=True)
        self.assertEqual(tree_hash(self.root), before_root)
        self.assertEqual(tree_hash(self.cwd), before_cwd)

    def test_with_no_tools_every_check_is_skipped_not_failed(self):
        empty = os.path.join(self.tmp, "empty")
        os.mkdir(empty)
        for t in ("sed", "grep", "cut", "awk", "date", "id", "uname", "cat", "ls", "head", "printf"):
            src = shutil.which(t)
            if src:
                os.symlink(src, os.path.join(empty, t))
        p = self.run_script(path=empty)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout, r"SKIP\s+Wi-Fi\s+nmcli")
        self.assertRegex(p.stdout, r"SKIP\s+Boot slot\s+rauc is not installed")
        self.assertNotIn("FAIL ", p.stdout)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
