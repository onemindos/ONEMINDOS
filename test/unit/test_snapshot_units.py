# SPDX-License-Identifier: Apache-2.0
"""BAK-04 (#241): the local file versions schedule ships in the image, runs the binary the image has, and
stays inert until an administrator opts in.

The first draft installed the units from deploy/systemd with ExecStart=/usr/local/bin/onemindd, which the
image does not have (it ships /usr/bin/onemindd), so nothing ran on a real box.
"""
import os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNITS = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system")


def rd(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


class SnapshotUnits(unittest.TestCase):
    def test_service_runs_the_image_binary_only_after_opt_in(self):
        svc = rd(UNITS, "onemind-snapshots.service")
        self.assertIn("ExecStart=/usr/bin/onemindd snapshots-tick", svc)
        self.assertNotIn("/usr/local/bin", svc)
        self.assertIn("ExecStart=/usr/bin/onemindd\n", rd(UNITS, "onemindd.service"))
        self.assertIn("ConditionPathExists=/data/onemind/snapshots.json", svc)
        self.assertIn("User=root", svc)
        self.assertIn("ProtectSystem=strict", svc)
        self.assertIn('"snapshots-tick": runSnapshots', rd("cmd", "onemindd", "registry.go"))

    def test_timer_is_enabled_in_the_image(self):
        link = os.path.join(UNITS, "timers.target.wants", "onemind-snapshots.timer")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), "../onemind-snapshots.timer")
        tm = rd(UNITS, "onemind-snapshots.timer")
        self.assertIn("Unit=onemind-snapshots.service", tm)
        self.assertIn("OnCalendar=hourly", tm)
        self.assertIn("Persistent=yes", tm)

    def test_no_unused_copy_in_the_deploy_bundle(self):
        for name in ("onemind-snapshots.service", "onemind-snapshots.timer"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, "deploy", "systemd", name)), name)


if __name__ == "__main__":
    unittest.main()
