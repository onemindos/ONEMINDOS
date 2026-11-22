# SPDX-License-Identifier: Apache-2.0
"""iot-radio-detect (#732): the image names known USB radio dongles and gives them to one group.
Static checks on the udev rules and the group; internal/detect checks the rules are what
sdk/schema/onemind.radios.json renders. Stdlib only."""
import json, os, re, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES = "os/rootfs/layers/onemind/usr/lib/udev/rules.d/70-onemind-radio.rules"


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


class RadioRules(unittest.TestCase):
    def setUp(self):
        self.rules = rd(RULES)
        self.named = [l for l in self.rules.splitlines() if "SYMLINK+=" in l]

    def test_every_known_dongle_has_one_rule_naming_it_under_dev_onemind(self):
        table = json.loads(rd("sdk/schema/onemind.radios.json"))
        self.assertEqual(len(self.named), len(table["devices"]))
        for line in self.named:
            self.assertRegex(line, r'SYMLINK\+="onemind/[a-z-]+-\$attr\{busnum\}-\$attr\{devpath\}"')
            self.assertIn('ATTRS{product}=="', line)     # never by vendor and product id alone
            self.assertIn('GROUP="onemind-radio", MODE="0660"', line)
            self.assertTrue(line.endswith('GOTO="onemind_radio_end"'), line)

    def test_only_usb_serial_lines_are_touched_and_nothing_runs(self):
        self.assertIn('KERNEL!="ttyUSB[0-9]*|ttyACM[0-9]*", GOTO="onemind_radio_end"', self.rules)
        self.assertIn('SUBSYSTEM!="tty", GOTO="onemind_radio_end"', self.rules)
        for word in ("RUN", "PROGRAM", "IMPORT", "dialout", "0666", "OWNER"):
            self.assertNotIn(word, self.rules)

    def test_the_group_exists_in_the_image_with_its_own_gid(self):
        cf = rd("os/rootfs/Containerfile")
        self.assertIn("groupadd --system --gid 964 onemind-radio;", cf)
        self.assertEqual(len(re.findall(r"--gid 964\b", cf)), 1)
        self.assertEqual(json.loads(rd("sdk/schema/onemind.radios.json"))["group"], "onemind-radio")

    @unittest.skipUnless(shutil.which("udevadm"), "udevadm not installed")
    def test_udev_accepts_the_rules(self):
        help_text = subprocess.run(["udevadm", "--help"], capture_output=True, text=True).stdout
        if "verify" not in help_text:
            self.skipTest("this udevadm has no verify (systemd < 254)")
        # The group exists only inside the image, so the build host checks a copy that names root.
        with tempfile.TemporaryDirectory() as d:
            copy = os.path.join(d, "70-onemind-radio.rules")
            with open(copy, "w", encoding="utf-8") as f:
                f.write(self.rules.replace('GROUP="onemind-radio"', 'GROUP="root"'))
            r = subprocess.run(["udevadm", "verify", "--no-style", copy], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
