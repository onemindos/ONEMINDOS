# SPDX-License-Identifier: Apache-2.0
"""LoRa link-check kit (test/lora/link-check/, #853): the MeshCore companion codec, the no-transmit verdict and
the whole run against a simulated radio on a pty. No real radio: this proves the kit, not the radio. The
founder's run fills test/lora/link-check/RESULTS.md."""
import importlib.util, json, os, pty, shutil, stat, struct, subprocess, sys, tempfile, threading, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIT = os.path.join(ROOT, "test", "lora", "link-check")
SCRIPT = os.path.join(KIT, "link_check.py")
SHELL = os.path.join(KIT, "link-check.sh")
DOC_FRAMES = os.path.join(KIT, "testdata", "doc-frames.json")


def load_kit():
    spec = importlib.util.spec_from_file_location("link_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def doc_frames():
    with open(DOC_FRAMES) as f:
        return {fr["name"]: fr for fr in json.load(f)["frames"]}


class Codec(unittest.TestCase):
    def setUp(self):
        self.lc = load_kit()

    def test_handshake_and_stats_commands_are_the_documented_bytes(self):
        lc = self.lc
        self.assertEqual(lc.device_query(), bytes([0x16, 0x03]))
        self.assertEqual(lc.app_start()[:8], bytes([0x01, 0, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(lc.get_stats("core"), bytes([0x38, 0x00]))
        self.assertEqual(lc.get_stats("packets"), bytes([0x38, 0x02]))
        self.assertEqual(lc.frame(lc.device_query()), b"<\x02\x00\x16\x03")

    def test_the_codec_refuses_every_command_outside_the_allowlist(self):
        lc = self.lc
        # SEND_TXT_MSG, SEND_CHANNEL_TXT_MSG, SEND_SELF_ADVERT, SET_RADIO_PARAMS, SET_RADIO_TX_POWER,
        # EXPORT_PRIVATE_KEY, SEND_RAW_DATA, SET_CHANNEL, FACTORY_RESET, REBOOT, SYNC_NEXT_MESSAGE.
        for op in (0x02, 0x03, 0x07, 0x0B, 0x0C, 0x17, 0x19, 0x20, 0x33, 0x13, 0x0A):
            with self.assertRaises(lc.RefusedCommand, msg=hex(op)):
                lc.frame(bytes([op, 0, 0, 0]))
        for bad in (bytes([0x38, 0x09]), bytes([0x38]), bytes([0x16, 0x03, 0x00]), b""):
            with self.assertRaises(lc.RefusedCommand, msg=bad.hex()):
                lc.frame(bad)
        self.assertEqual(sorted(lc.ALLOWED_COMMANDS), [0x01, 0x16, 0x38])

    def test_deframer_skips_junk_and_joins_split_frames(self):
        lc = self.lc
        a, b = bytes([0x0A]), bytes([0x01, 0x02])
        wire = b"junk" + b">" + struct.pack("<H", 1) + a + b">" + struct.pack("<H", 2) + b
        d = lc.Deframer()
        out = []
        for i in range(len(wire)):
            out += d.feed(wire[i:i + 1])
        self.assertEqual(out, [a, b])
        self.assertEqual(d.feed(b">\xff\xff" + b">\x01\x00\x0a"), [a])  # an oversize length is dropped

    def test_documented_frames_decode_to_their_fields(self):
        for name, fr in doc_frames().items():
            with self.subTest(name):
                self.assertEqual(self.lc.decode(bytes.fromhex(fr["hex"])), fr["decoded"])

    def test_short_frames_are_errors_and_unknown_codes_are_counted(self):
        lc = self.lc
        with self.assertRaises(ValueError):
            lc.decode(bytes.fromhex(doc_frames()["self_info_us_preset"]["hex"])[:40])
        self.assertEqual(lc.decode(bytes([0x83])), {"kind": "UNKNOWN", "code": 0x83})

    def test_redaction_replaces_key_name_location_and_pin(self):
        lc = self.lc
        fr = doc_frames()
        raw = bytes.fromhex(fr["self_info_us_preset"]["hex"])
        red = lc.decode(lc.redact(raw))
        self.assertEqual(red["public_key"], lc.TEST_PUBLIC_KEY.hex())
        self.assertEqual(red["name"], lc.TEST_NAME)
        self.assertEqual((red["lat"], red["lon"]), (0.0, 0.0))
        self.assertEqual(red["freq_mhz"], 910.525)  # radio settings are kept
        self.assertNotIn(fr["self_info_us_preset"]["decoded"]["public_key"], lc.redact(raw).hex())
        dev = lc.decode(lc.redact(bytes.fromhex(fr["device_info_v10"]["hex"])))
        self.assertEqual(dev["ble_pin"], lc.TEST_PIN)
        self.assertEqual(dev["model"], "Elecrow ThinkNode M2")

    def test_preset_report_reads_the_us_band_and_power(self):
        lc = self.lc
        fr = doc_frames()
        ok = lc.preset_report(fr["self_info_us_preset"]["decoded"])
        self.assertEqual(ok["state"], "works")
        eu = lc.preset_report(fr["self_info_firmware_default_eu"]["decoded"])
        self.assertEqual(eu["state"], "fails")
        self.assertTrue(any("902-928" in r for r in eu["reasons"]))
        self.assertTrue(any("19 dBm" in r for r in eu["reasons"]))


class Verdict(unittest.TestCase):
    def setUp(self):
        self.lc = load_kit()

    def reads(self, sents, uptimes):
        return [{"label": l, "core": {"uptime_s": u}, "packets": {"sent": s, "flood_tx": 0, "direct_tx": 0}}
                for l, s, u in zip(("before", "after", "idle"), sents, uptimes)]

    def test_no_rise_works_a_rise_fails_a_restart_is_partial(self):
        v = self.lc.no_transmit_verdict
        self.assertEqual(v(self.reads([3, 3, 3], [10, 12, 612]))["state"], "works")
        self.assertEqual(v(self.reads([3, 4, 4], [10, 12, 612]))["state"], "fails")
        self.assertEqual(v(self.reads([3, 3, 3], [10, 2, 602]))["state"], "partial")
        self.assertEqual(v(self.reads([3, 3], [10, 12]))["state"], "partial")  # missing idle read
        missing = self.reads([3, 3, 3], [10, 12, 612])
        missing[1]["packets"] = None
        self.assertEqual(v(missing)["state"], "partial")


class FakeRadio(threading.Thread):
    """Speaks MeshCore companion framing on the master side of a pty, from the documented frames."""

    def __init__(self, master, frames, sent_after_start=0, reboot_after_start=False):
        super().__init__(daemon=True)
        self.master, self.frames, self.received = master, frames, []
        self.sent, self.uptime = 0, 100
        self.sent_after_start, self.reboot_after_start = sent_after_start, reboot_after_start
        self.stop = False

    def reply(self, payload):
        os.write(self.master, b">" + struct.pack("<H", len(payload)) + payload)

    def run(self):
        buf = b""
        while not self.stop:
            try:
                chunk = os.read(self.master, 512)
            except OSError:
                return
            buf += chunk
            while len(buf) >= 3 and buf[0:1] == b"<":
                n = struct.unpack("<H", buf[1:3])[0]
                if len(buf) < 3 + n:
                    break
                cmd, buf = buf[3:3 + n], buf[3 + n:]
                self.received.append(cmd)
                self.handle(cmd)

    def handle(self, cmd):
        self.uptime += 1
        if cmd[0] == 0x01:
            self.reply(bytes([0x83]))  # a push frame arrives first; the kit must skip it
            self.reply(bytes.fromhex(self.frames["self_info_us_preset"]["hex"]))
            self.sent += self.sent_after_start
            if self.reboot_after_start:
                self.uptime = 1
        elif cmd[0] == 0x16:
            self.reply(bytes.fromhex(self.frames["device_info_v10"]["hex"]))
        elif cmd == bytes([0x38, 0x00]):
            self.reply(struct.pack("<BBHIHB", 0x18, 0, 4100, self.uptime, 0, 0))
        elif cmd == bytes([0x38, 0x02]):
            self.reply(struct.pack("<BBIIIIIII", 0x18, 2, 7, self.sent, self.sent, 0, 7, 0, 0))
        else:
            self.reply(bytes([0x01, 0x01]))


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.lc = load_kit()
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.out = t.name
        self.frames = doc_frames()

    def run_kit(self, **radio):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        port = os.ttyname(slave)
        fake = FakeRadio(master, self.frames, **radio)
        fake.start()
        try:
            report = self.lc.run(port, self.out, idle_seconds=0.2, timeout=3.0)
        finally:
            fake.stop = True
            os.close(slave)
        return report, fake

    def test_passive_run_sends_only_reads_and_writes_redacted_vectors(self):
        report, fake = self.run_kit()
        ops = [c[0] for c in fake.received]
        self.assertTrue(set(ops) <= {0x01, 0x16, 0x38}, [hex(o) for o in ops])
        self.assertIn(0x01, ops)
        self.assertIn(0x16, ops)
        self.assertEqual(report["checks"]["handshake"]["state"], "works")
        self.assertEqual(report["checks"]["no_transmit"]["state"], "works")
        self.assertEqual(report["checks"]["preset"]["state"], "works")
        self.assertEqual(report["radio"]["firmware"], "v1.12.0")
        self.assertEqual(report["radio"]["freq_mhz"], 910.525)
        self.assertEqual(report["push_frames_seen"], {"0x83": 1})
        cap_path = os.path.join(self.out, "captured-frames.json")
        with open(cap_path) as f:
            text = f.read()
        real_key = self.frames["self_info_us_preset"]["decoded"]["public_key"]
        self.assertNotIn(real_key, text)
        self.assertNotIn("Example Radio", text)
        self.assertNotIn("654321", text)
        names = [fr["name"] for fr in json.loads(text)["frames"]]
        self.assertIn("self_info", names)
        self.assertIn("device_info", names)
        self.assertIn("stats_packets_idle", names)
        self.assertEqual(self.lc.verify_capture(cap_path), [])
        with open(os.path.join(self.out, "report.json")) as f:
            self.assertNotIn(real_key, f.read())

    def test_a_sent_count_that_rises_fails_the_no_transmit_check(self):
        report, _ = self.run_kit(sent_after_start=1)
        self.assertEqual(report["checks"]["no_transmit"]["state"], "fails")

    def test_a_radio_restart_makes_the_no_transmit_check_partial(self):
        report, _ = self.run_kit(reboot_after_start=True)
        self.assertEqual(report["checks"]["no_transmit"]["state"], "partial")

    def test_decode_command_catches_a_tampered_capture(self):
        self.run_kit()
        cap_path = os.path.join(self.out, "captured-frames.json")
        with open(cap_path) as f:
            cap = json.load(f)
        cap["frames"][0]["decoded"]["kind"] = "WRONG"
        with open(cap_path, "w") as f:
            json.dump(cap, f)
        self.assertNotEqual(self.lc.verify_capture(cap_path), [])
        r = subprocess.run([sys.executable, "-I", SCRIPT, "decode", cap_path], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        r = subprocess.run([sys.executable, "-I", SCRIPT, "decode", DOC_FRAMES], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def fake_tree(root, driver="ch341", vid="1a86", pid="7522"):
    usb = os.path.join(root, "sys", "devices", "usb1", "1-1")
    intf = os.path.join(usb, "1-1:1.0")
    os.makedirs(os.path.join(intf, "ttyUSB0"))
    os.makedirs(os.path.join(root, "sys", "bus", "usb-serial", "drivers", driver))
    for name, val in (("idVendor", vid), ("idProduct", pid)):
        with open(os.path.join(usb, name), "w") as f:
            f.write(val + "\n")
    os.symlink(os.path.join(root, "sys", "bus", "usb-serial", "drivers", driver),
               os.path.join(intf, "ttyUSB0", "driver"))
    os.makedirs(os.path.join(root, "sys", "class", "tty", "ttyUSB0"))
    os.symlink(os.path.join(intf, "ttyUSB0"), os.path.join(root, "sys", "class", "tty", "ttyUSB0", "device"))


class Preflight(unittest.TestCase):
    """link-check.sh --preflight-only against a fake /sys and a fake modinfo on PATH."""

    def setUp(self):
        if not shutil.which("bash"):
            self.skipTest("bash not installed")
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.t = t.name
        os.makedirs(os.path.join(self.t, "bin"))

    def modinfo(self, ok=True):
        path = os.path.join(self.t, "bin", "modinfo")
        body = ("#!/bin/sh\ncase \"$*\" in\n  *alias*) echo 'usb:v1A86p7523d*dc*'; echo 'usb:v1A86p7522d*dc*';;\n"
                "  *) echo 'filename: /lib/modules/x/ch341.ko';;\nesac\nexit 0\n") if ok else \
            "#!/bin/sh\necho \"modinfo: ERROR: Module ch341 not found.\" >&2\nexit 1\n"
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def preflight(self):
        env = dict(os.environ, PATH=os.path.join(self.t, "bin") + os.pathsep + os.environ["PATH"],
                   LINKCHECK_SYSFS=os.path.join(self.t, "sys"), OUT=os.path.join(self.t, "out"))
        return subprocess.run(["bash", SHELL, "--preflight-only"], capture_output=True, text=True, env=env)

    def test_finds_the_m2_bound_to_ch341(self):
        self.modinfo()
        fake_tree(self.t)
        r = self.preflight()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ch341 module: works", r.stdout)
        self.assertIn("ttyUSB0 bound to ch341: works", r.stdout)

    def test_missing_module_or_wrong_driver_fails(self):
        self.modinfo(ok=False)
        fake_tree(self.t, driver="cp210x")
        r = self.preflight()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ch341 module: fails", r.stdout)


class KitFiles(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(KIT, name)) as f:
            return f.read()

    def test_readme_has_the_founder_steps_and_the_kit_never_sets_rf(self):
        readme = self.read("README.md")
        for need in ("https://flasher.meshcore.io", "Companion (USB)", "910.525", "62.5", "SF7", "19 dBm",
                     "never transmits"):
            self.assertIn(need, readme)
        src = self.read("link_check.py") + self.read("link-check.sh")
        for forbidden in ("0x0B", "0x0b", "0x0C", "0x0c", "SET_RADIO", "set_radio", "tx_power(", "advert("):
            self.assertNotIn(forbidden, src)

    def test_results_template_has_every_check(self):
        res = self.read("RESULTS.md")
        for need in ("Date", "Firmware version", "ch341", "APP_START", "DEVICE_QUERY", "GET_STATS",
                     "10 min idle", "works / fails / partial", "frames.json", "Companion (Bluetooth)",
                     "6E400001-B5A3-F393-E0A9-E50E24DCCA9E", "VM"):
            self.assertIn(need, res)


if __name__ == "__main__":
    unittest.main()
