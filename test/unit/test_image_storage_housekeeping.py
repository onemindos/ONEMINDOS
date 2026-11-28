# SPDX-License-Identifier: Apache-2.0
"""P-10, storage housekeeping: static checks on the files that put smartd (unmasked, with a configuration that feeds
Notifications) and its warnings feed on the image, with the state on /data. Stdlib only. The booted proof is
first-boot check F25 (test/qemu/CRITERIA-FIRSTBOOT.md section 19)."""
import hashlib, os, re, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = "os/rootfs/layers/base"
NOTIFY = os.path.join(ROOT, BASE, "usr/lib/onemind/smartd-notify")


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


class Image(unittest.TestCase):
    c = rd("os/rootfs/Containerfile")

    def test_smartd_is_enabled_and_no_longer_masked(self):
        self.assertIn("systemctl enable smartmontools.service", self.c)
        self.assertNotRegex(self.c, r"systemctl mask [^\n]*smart")
        self.assertIn("test -x /usr/lib/onemind/smartd-notify", self.c)

    def test_smartd_config_mails_nobody_and_runs_our_script(self):
        conf = [l for l in rd(BASE + "/etc/smartd.conf").splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual(len(conf), 1)
        self.assertTrue(conf[0].startswith("DEVICESCAN "))
        for want in ("-m <nomailer>", "-M exec /usr/lib/onemind/smartd-notify", "-n standby,q", "-W 4,60,70"):
            self.assertIn(want, conf[0])

    def test_smartd_with_no_smart_disk_exits_cleanly_not_failed(self):
        opts = [l for l in rd(BASE + "/etc/default/smartmontools").splitlines() if l.startswith("smartd_opts=")]
        self.assertEqual(len(opts), 1)
        self.assertIn("-q nodev0", opts[0])

    def test_script_is_executable_and_posix_sh(self):
        self.assertTrue(os.access(NOTIFY, os.X_OK))
        self.assertTrue(rd(BASE + "/usr/lib/onemind/smartd-notify").startswith("#!/bin/sh\n"))

    def test_package_is_installed_on_both_legs(self):
        for leg in ("debian", "ubuntu"):
            self.assertIn("smartmontools", re.sub(r"#.*", "", rd(f"os/rootfs/packages/{leg}-common.txt")).split(), leg)


class State(unittest.TestCase):
    SRC, DST = "var-lib-smartmontools", "/var/lib/smartmontools"

    def test_bound_from_data_on_every_board_with_a_fstab(self):
        for f in (BASE + "/etc/fstab", "os/boards/rpi5/rootfs/etc/fstab"):
            self.assertRegex(rd(f), r"(?m)^/data/state/%s\s+%s\s+none bind,nofail,x-systemd\.requires=onemind-data-layout\.service 0 0$"
                             % (self.SRC, re.escape(self.DST)), f)

    def test_layout_creates_the_source_and_recovery_waits_for_the_mount(self):
        self.assertRegex(rd(BASE + "/usr/lib/systemd/system/onemind-data-layout.service"),
                         r"for d in [^;]*\b%s\b[^;]*; do mkdir -p" % self.SRC)
        after = re.search(r"(?m)^After=(.*)$", rd("os/recovery/onemind-data-check.service")).group(1).split()
        self.assertIn("var-lib-smartmontools.mount", after)

    def test_mount_point_exists_in_the_image(self):
        self.assertIn(self.DST, rd("os/rootfs/Containerfile"))


@unittest.skipUnless(shutil.which("jq") and shutil.which("sh"), "needs jq and sh")
class Script(unittest.TestCase):
    def run_notify(self, feed, **env):
        e = {"PATH": os.environ["PATH"], "ONEMIND_SMARTD_FEED": feed, **env}
        return subprocess.run(["sh", NOTIFY], env=e, capture_output=True, text=True, timeout=20)

    def test_one_line_per_problem_and_only_for_plain_device_nodes(self):
        with tempfile.TemporaryDirectory() as d:
            feed = os.path.join(d, "sub", "alerts.jsonl")
            good = dict(SMARTD_DEVICE="/dev/sda", SMARTD_FAILTYPE="FailedHealthCheck", SMARTD_MESSAGE='Device: /dev/sda, "bad" \x1b[31m', SMARTD_TFIRSTEPOCH="1700000000")
            self.assertEqual(self.run_notify(feed, **good).returncode, 0)
            self.assertEqual(self.run_notify(feed, **good).returncode, 0)   # the daily reminder of the same problem
            self.run_notify(feed, **{**good, "SMARTD_DEVICE": "/dev/disk/by-id/x"})
            self.run_notify(feed, **{**good, "SMARTD_DEVICE": "/dev/sda; rm -rf /"})
            lines = rd_abs(feed).splitlines()
            self.assertEqual(len(lines), 1, lines)
            import json
            row = json.loads(lines[0])
            self.assertEqual((row["id"], row["device"], row["kind"]), ("1700000000-sda-FailedHealthCheck", "/dev/sda", "FailedHealthCheck"))
            self.assertNotIn("\x1b", row["message"])
            self.run_notify(feed, **{**good, "SMARTD_TFIRSTEPOCH": "1700000099"})   # a later, different problem
            self.assertEqual(len(rd_abs(feed).splitlines()), 2)

    def test_the_feed_is_capped(self):
        with tempfile.TemporaryDirectory() as d:
            feed = os.path.join(d, "alerts.jsonl")
            with open(feed, "w") as f:
                f.write("".join('{"id":"old-%d"}\n' % i for i in range(250)))
            self.run_notify(feed, SMARTD_DEVICE="/dev/nvme0n1", SMARTD_FAILTYPE="Temperature", SMARTD_MESSAGE="hot", SMARTD_TFIRSTEPOCH="1700000001")
            lines = rd_abs(feed).splitlines()
            self.assertEqual(len(lines), 200)
            self.assertIn("1700000001-nvme0n1-Temperature", lines[-1])


def rd_abs(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class Battery(unittest.TestCase):
    def test_f25_is_preregistered_and_implemented(self):
        crit = rd("test/qemu/CRITERIA-FIRSTBOOT.md")
        for tid in ("F25", "F25b", "F25c"):
            self.assertIn("| %s |" % tid, crit)
        h = hashlib.sha256(crit.encode()).hexdigest()
        self.assertIn(h + "  CRITERIA-FIRSTBOOT.md", rd("test/qemu/PREREGISTRATION.sha256"))
        fb = rd("test/qemu/firstboot.py")
        for tid in ("F25", "F25b", "F25c"):
            self.assertIn('"%s"' % tid, fb)
        self.assertIn("def f25(", fb)

    def test_f13_no_longer_demands_masked_smartd(self):
        fb = rd("test/qemu/firstboot.py")
        self.assertNotIn("smartd_masked", fb)


if __name__ == "__main__":
    unittest.main()
