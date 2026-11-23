# SPDX-License-Identifier: Apache-2.0
"""iot-radio-detect (#732): the image names known USB radio dongles /dev/onemind/<kind><n> and gives them
to one group. Static checks on the udev rules, the group and the naming helper, and runs of the helper
against a fake sysfs (internal/detect checks the rules are what sdk/schema/onemind.radios.json renders).
Stdlib only."""
import json, os, re, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES = "os/rootfs/layers/onemind/usr/lib/udev/rules.d/70-onemind-radio.rules"
NAMER = "os/rootfs/layers/onemind/usr/lib/onemind/radio-name"
TABLE = "sdk/schema/onemind.radios.json"


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


class RadioRules(unittest.TestCase):
    def setUp(self):
        self.rules = rd(RULES)
        self.named = [l for l in self.rules.splitlines() if "SYMLINK+=" in l]
        self.table = json.loads(rd(TABLE))

    def test_every_known_dongle_has_one_rule_naming_it_under_dev_onemind(self):
        self.assertEqual(len(self.named), len(self.table["devices"]))
        for line, row in zip(self.named, self.table["devices"]):
            vid, pid = row["id"].split(":")
            self.assertIn(f'ATTRS{{idVendor}}=="{vid}", ATTRS{{idProduct}}=="{pid}"', line)
            self.assertIn(f'PROGRAM="/usr/lib/onemind/radio-name {row["kind"]}", SYMLINK+="onemind/%c"', line)
            self.assertIn('GROUP="onemind-radio", MODE="0660"', line)
            self.assertTrue(line.endswith('GOTO="onemind_radio_end"'), line)
            # A product row also needs its product string; only an id row (a generic chip) goes without.
            self.assertEqual('ATTRS{product}=="' in line, row["match"] == "product", line)

    def test_the_m2_ch340k_is_the_lora_row_and_asks_the_owner(self):
        lora = [r for r in self.table["devices"] if r["kind"] == "lora"]
        self.assertEqual([(r["id"], r["match"]) for r in lora], [("1a86:7522", "id")])
        self.assertEqual(self.table["confirm"]["lora"], {"profile": "meshcore-companion-usb", "label": "MeshCore companion (USB)"})

    def test_only_usb_serial_lines_are_touched_and_nothing_else_runs(self):
        self.assertIn('ACTION=="remove", GOTO="onemind_radio_end"', self.rules)
        self.assertIn('SUBSYSTEM!="tty", GOTO="onemind_radio_end"', self.rules)
        self.assertIn('KERNEL!="ttyUSB[0-9]*|ttyACM[0-9]*", GOTO="onemind_radio_end"', self.rules)
        body = "\n".join(l for l in self.rules.splitlines() if not l.startswith("#"))
        self.assertEqual(set(re.findall(r'PROGRAM="([^ "]+)', body)), {"/usr/lib/onemind/radio-name"})
        for word in ("RUN", "IMPORT", "dialout", "0666", "OWNER"):
            self.assertNotIn(word, body)

    def test_the_group_exists_in_the_image_with_its_own_gid(self):
        cf = rd("os/rootfs/Containerfile")
        self.assertIn("groupadd --system --gid 964 onemind-radio;", cf)
        self.assertEqual(len(re.findall(r"--gid 964\b", cf)), 1)
        self.assertEqual(self.table["group"], "onemind-radio")

    def test_the_helper_is_executable_and_knows_exactly_the_table_kinds(self):
        self.assertTrue(os.access(os.path.join(ROOT, NAMER), os.X_OK))
        src = rd(NAMER)
        case = re.search(r"^case \$kind in\n(.*)\) ;;$", src, re.M).group(1)
        self.assertEqual(set(case.replace(" ", "").split("|")), set(self.table["kinds"]))
        for word in ("stty", "cat /dev", "> /dev", "exec 3<", "/dev/tty"):
            self.assertNotIn(word, src)  # it never opens the device

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


@unittest.skipUnless(shutil.which("flock"), "flock (util-linux) not installed; Debian always has it")
class RadioNamer(unittest.TestCase):
    """The first LoRa radio is lora0; a radio keeps its name; a name frees when its line leaves /sys."""

    M2 = "/devices/pci0000:00/0000:00:14.0/usb1/1-1/1-1:1.0/ttyUSB0/tty/ttyUSB0"
    M2B = "/devices/pci0000:00/0000:00:14.0/usb1/1-3/1-3:1.0/ttyUSB1/tty/ttyUSB1"
    ZBT = "/devices/pci0000:00/0000:00:14.0/usb1/1-2/1-2:1.0/tty/ttyACM0"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = os.path.join(self.tmp.name, "run")
        self.sys = os.path.join(self.tmp.name, "sys")
        for p in (self.M2, self.M2B, self.ZBT):
            os.makedirs(self.sys + p)

    def tearDown(self):
        self.tmp.cleanup()

    def name(self, kind, devpath):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DEVPATH": devpath}
        return subprocess.run(["sh", os.path.join(ROOT, NAMER), kind, self.run_dir, self.sys],
                              capture_output=True, text=True, env=env)

    def test_first_radio_of_each_kind_gets_zero_and_keeps_it(self):
        self.assertEqual(self.name("lora", self.M2).stdout, "lora0\n")
        self.assertEqual(self.name("zigbee-thread", self.ZBT).stdout, "zigbee-thread0\n")
        self.assertEqual(self.name("lora", self.M2B).stdout, "lora1\n")
        self.assertEqual(self.name("lora", self.M2).stdout, "lora0\n")  # a change event: same name

    def test_an_unplugged_radio_frees_its_name(self):
        self.assertEqual(self.name("lora", self.M2).stdout, "lora0\n")
        shutil.rmtree(self.sys + "/devices/pci0000:00/0000:00:14.0/usb1/1-1")
        self.assertEqual(self.name("lora", self.M2B).stdout, "lora0\n")

    def test_refuses_an_unknown_kind_or_a_bad_devpath(self):
        for kind, dev in (("zwave", self.M2), ("", self.M2), ("lora", ""), ("lora", "/etc/passwd"),
                          ("lora", "/devices/../../etc"), ("lora", "/devices/x y"), ("lora", "/devices/a;b")):
            r = self.name(kind, dev)
            self.assertNotEqual(r.returncode, 0, (kind, dev))
            self.assertEqual(r.stdout, "", (kind, dev))

    def test_sixteen_names_per_kind_at_most(self):
        for i in range(16):
            p = f"/devices/usb1/1-{i}/tty/ttyUSB{i}"
            os.makedirs(self.sys + p)
            self.assertEqual(self.name("lora", p).stdout, f"lora{i}\n")
        os.makedirs(self.sys + "/devices/usb1/1-99/tty/ttyUSB99")
        r = self.name("lora", "/devices/usb1/1-99/tty/ttyUSB99")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
