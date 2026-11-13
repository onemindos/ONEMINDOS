# SPDX-License-Identifier: Apache-2.0
"""Jetson board (os/boards/jetson-orin, brief 30 B4.7): gate decisions inside NVIDIA's validation
hook, the OneMind payload verifier and signer, the layout tool, and the NVIDIA pins."""
import datetime, importlib.util, json, os, re, shutil, subprocess, tempfile, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOARD = os.path.join(ROOT, "os", "boards", "jetson-orin")


def put(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


J = load("onemind_jetson", os.path.join(BOARD, "rootfs/usr/lib/onemind/jetson/onemind_jetson.py"))
LAY = load("jetson_layout", os.path.join(BOARD, "jetson_layout.py"))

DEVICE_LAYOUT = {"compatible": "onemind-jetson-orin", "target_board": "jetson-orin-nano-devkit", "rootfs_ab": True,
                 "external_device": "nvme0n1", "rootfs_size": "nvidia-default", "rootfs_enc": False,
                 "uefi_secure_boot": False, "l4t": "36.5.2"}


class FakeDevice:
    def __init__(self, slot="B", checks=(), slots=None, l4t="36.5.2", qspi="36.5.2"):
        self.slot, self.checks, self.calls = slot, list(checks), 0
        self.slots = slots or {"A": "normal", "B": "normal"}
        self._l4t, self._qspi = l4t, qspi

    def current_slot(self):
        if self.slot is None:
            raise RuntimeError("nvbootctrl failed")
        return self.slot

    def rootfs_slots(self):
        return self.slots

    def qspi_version(self):
        return self._qspi

    def l4t_version(self):
        return self._l4t

    def boot_id(self):
        return "boot-1"

    def check(self):
        self.calls += 1
        return self.checks.pop(0) if self.checks else (True, "ok (fresh)")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.p = J.Paths(self.root)
        os.makedirs(os.path.dirname(self.p.release))
        put(self.p.release, "ONEMIND_VERSION=0.2.0\n")
        put(self.p.image_layout, json.dumps(DEVICE_LAYOUT))
        os.makedirs(os.path.dirname(self.p.gate_defaults))
        put(self.p.gate_defaults, "ONEMIND_GATE_TIMEOUT=60\nONEMIND_GATE_STABLE=3\nONEMIND_GATE_INTERVAL=10\n")
        os.makedirs(os.path.dirname(self.p.console))
        self.clock = Clock()

    def gate(self, dev):
        return J.Gate(self.p, dev, sleep=self.clock.sleep, clock=self.clock)

    def pending(self, text):
        os.makedirs(self.p.state, exist_ok=True)
        put(self.p.pending, text)

    def bad(self):
        return J.read(self.p.bad)


class GateTests(Base):
    def test_committed_passes_and_records_layout(self):
        self.assertEqual(self.gate(FakeDevice()).run(), 0)
        self.assertTrue(J.read(self.p.passfile).startswith("boot-1 committed"))
        self.assertEqual(json.loads(J.read(self.p.device_layout)), DEVICE_LAYOUT)

    def test_device_layout_is_recorded_once(self):
        os.makedirs(os.path.dirname(self.p.device_layout))
        put(self.p.device_layout, '{"old": 1}')
        self.gate(FakeDevice()).run()
        self.assertEqual(J.read(self.p.device_layout), '{"old": 1}')

    def test_trial_good_after_three_fresh_passes(self):
        self.pending("B 0.2.0\n")
        dev = FakeDevice(slot="B")
        self.assertEqual(self.gate(dev).run(), 0)
        self.assertEqual(dev.calls, 3)
        self.assertFalse(os.path.exists(self.p.pending))
        self.assertIn("trial-good", J.read(self.p.passfile))

    def test_a_failure_resets_the_streak(self):
        self.pending("B 0.2.0\n")
        dev = FakeDevice(slot="B", checks=[(True, "ok"), (True, "ok"), (False, "fail G3: stale"), (True, "ok"), (True, "ok"), (True, "ok")])
        self.assertEqual(self.gate(dev).run(), 0)
        self.assertEqual(dev.calls, 6)

    def test_trial_deadline_rejects_image_bad(self):
        self.pending("B 0.2.0\n")
        dev = FakeDevice(slot="B", checks=[(False, "fail G1: no kubeconfig")] * 10)
        self.assertEqual(self.gate(dev).run(), 1)
        self.assertIn("version=0.2.0 verdict=image-bad", self.bad())
        self.assertTrue(os.path.exists(self.p.pending), "marker kept until NVIDIA falls back")
        self.assertFalse(os.path.exists(self.p.passfile))

    def test_core_pod_only_failure_is_environment_bad(self):
        self.pending("B 0.2.0\n")
        dev = FakeDevice(slot="B", checks=[(True, "ok"), (False, "fail G4: core pod starved")] * 5)
        self.assertEqual(self.gate(dev).run(), 1)
        self.assertIn("verdict=environment-bad", self.bad())

    def test_g7_version_mismatch(self):
        self.pending("B 0.3.0\n")
        dev = FakeDevice(slot="B")
        self.assertEqual(self.gate(dev).run(), 1)
        self.assertEqual(dev.calls, 0)
        self.assertIn("version=0.2.0 verdict=image-bad", self.bad())

    def test_retry_boot_of_a_judged_version_fails_fast(self):
        self.pending("B 0.2.0\n")
        os.makedirs(self.p.state, exist_ok=True)
        put(self.p.bad, "2026-11-12T00:00:00Z version=0.2.0 verdict=image-bad\n")
        dev = FakeDevice(slot="B")
        self.assertEqual(self.gate(dev).run(), 1)
        self.assertEqual(dev.calls, 0)
        self.assertEqual(self.bad().count("version=0.2.0"), 1)

    def test_fell_back_records_bad_and_passes(self):
        self.pending("B 0.3.0\n")
        self.assertEqual(self.gate(FakeDevice(slot="A")).run(), 0)
        self.assertIn("version=0.3.0 verdict=image-bad", self.bad())
        self.assertFalse(os.path.exists(self.p.pending))

    def test_unreadable_slot_with_marker_is_a_failed_trial(self):
        self.pending("B 0.2.0\n")
        self.assertEqual(self.gate(FakeDevice(slot=None)).run(), 1)
        self.assertIn("verdict=image-bad", self.bad())

    def test_no_fallback_slot_stays_and_alerts(self):
        self.pending("B 0.2.0\n")
        dev = FakeDevice(slot="B", checks=[(False, "fail G2: kubelet")] * 10, slots={"A": "unbootable", "B": "normal"})
        self.assertEqual(self.gate(dev).run(), 0)
        self.assertIn("unhealthy-no-fallback", J.read(self.p.passfile))

    def test_wait_pass_needs_this_boot(self):
        os.makedirs(self.p.run, exist_ok=True)
        put(self.p.passfile, "boot-0 committed\n")
        c = Clock()
        self.assertEqual(J.wait_pass(self.p, FakeDevice(), 10, sleep=c.sleep, clock=c), 1)
        put(self.p.passfile, "boot-1 committed\n")
        self.assertEqual(J.wait_pass(self.p, FakeDevice(), 10, sleep=c.sleep, clock=c), 0)


class ParseTests(unittest.TestCase):
    def test_nv_release(self):
        self.assertEqual(J.parse_nv_release("# R39 (release), REVISION: 2.1, GCID: 1, BOARD: generic, EABI: aarch64"), "39.2.1")
        self.assertIsNone(J.parse_nv_release("garbage"))

    def test_dump_slots_info(self):
        text = ("Current version: 39.2.0\nCapsule update status: 0\nCurrent bootloader slot: A\n"
                "num_slots: 2\nslot: 0,             retry_count: 3,             status: normal\n"
                "slot: 1,             retry_count: 0,             status: unbootable\n")
        self.assertEqual(J.parse_slots(text), {"version": "39.2.0", "A": "normal", "B": "unbootable"})


def manifest(**over):
    m = {"schema": J.SCHEMA, "version": "0.3.0", "compatible": "onemind-jetson-orin", "layout": J.layout_flags(DEVICE_LAYOUT),
         "l4t": {"from": "36.5.2", "to": "39.2.1"}, "bootloader": {"requires_qspi": "36.5.2", "installs": "39.2.1"},
         "files": {"ota_payload_package.tar.gz": {"sha256": "x"}, "ota_tools_R39.2.1_aarch64.tbz2": {"sha256": "y"}},
         "expires": "2099-01-01T00:00:00Z"}
    m.update(over)
    return m


def check(m, **over):
    kw = dict(device_layout=DEVICE_LAYOUT, image_layout=DEVICE_LAYOUT, l4t="36.5.2", qspi="36.5.2", bad=set(), running_version="0.2.0")
    kw.update(over)
    return J.check_manifest(m, **kw)


class ManifestTests(unittest.TestCase):
    def test_good(self):
        self.assertEqual(check(manifest()), [])

    def test_layout_flag_mismatch_refused(self):
        lay = dict(J.layout_flags(DEVICE_LAYOUT), rootfs_ab=False)
        self.assertTrue(any("rootfs_ab" in w for w in check(manifest(layout=lay))))

    def test_wrong_base_qspi_bad_running_expired(self):
        self.assertTrue(check(manifest(), l4t="36.4.4"))
        self.assertTrue(any("QSPI" in w for w in check(manifest(), qspi="39.2.1")))
        self.assertTrue(any("rolled back" in w for w in check(manifest(), bad={"0.3.0"})))
        self.assertTrue(any("already running" in w for w in check(manifest(), running_version="0.3.0")))
        self.assertTrue(any("expired" in w for w in check(manifest(expires="2020-01-01T00:00:00Z"))))
        self.assertTrue(any("compatible" in w for w in check(manifest(compatible="onemind-x86_64-efi"))))

    def test_file_names_must_be_plain(self):
        files = {"../etc/passwd": {}, "ota_payload_package.tar.gz": {}, "ota_tools_R39.2.1_aarch64.tbz2": {}}
        self.assertTrue(any("plain file name" in w for w in check(manifest(files=files))))


@unittest.skipUnless(shutil.which("openssl") and subprocess.run(["openssl", "cms", "-help"], capture_output=True).returncode in (0, 1),
                     "openssl cms not available")
class SignVerifyTests(Base):
    """Keys are generated here and deleted with the temp dir; none is committed."""

    def setUp(self):
        super().setUp()
        self.ca = os.path.join(self.root, "ca")
        os.makedirs(self.ca)
        r = subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                            "-days", "2", "-subj", "/CN=test", "-keyout", f"{self.ca}/k", "-out", f"{self.ca}/c"],
                           capture_output=True)
        if r.returncode != 0:
            self.skipTest("this openssl cannot make an EC test CA")
        shutil.copy(f"{self.ca}/c", self.p.keyring)
        os.makedirs(os.path.dirname(self.p.device_layout))
        put(self.p.device_layout, json.dumps(DEVICE_LAYOUT))
        self.bundle = os.path.join(self.root, "bundle")
        os.makedirs(self.bundle)
        put(f"{self.bundle}/ota_payload_package.tar.gz", b"payload")
        put(f"{self.bundle}/ota_tools_R39.2.1_aarch64.tbz2", b"tools")
        lay = os.path.join(self.root, "payload-layout.json")
        put(lay, json.dumps(DEVICE_LAYOUT))
        m = J.make_manifest(self.bundle, version="0.3.0", compatible="onemind-jetson-orin", layout=DEVICE_LAYOUT,
                            l4t_from="36.5.2", l4t_to="39.2.1", requires_qspi="36.5.2", days=30)
        put(f"{self.bundle}/manifest.json", json.dumps(m))
        self.dl = lay

    def sign(self, layouts):
        return J.sign_manifest(f"{self.bundle}/manifest.json", f"{self.bundle}/manifest.json.p7s", f"{self.ca}/c", f"{self.ca}/k", layouts)

    def verify(self):
        return J.verify_bundle(self.bundle, self.p, FakeDevice(slot="A"), J.Gate(self.p, FakeDevice()))[1]

    def test_signed_bundle_verifies(self):
        self.assertEqual(self.sign([self.dl]), 0)
        self.assertEqual(self.verify(), [])

    def test_sign_refuses_other_layout(self):
        other = os.path.join(self.root, "other.json")
        put(other, json.dumps(dict(DEVICE_LAYOUT, external_device="mmcblk0")))
        self.assertEqual(self.sign([other]), 2)
        self.assertEqual(self.sign([]), 2)
        self.assertFalse(os.path.exists(f"{self.bundle}/manifest.json.p7s"))

    def test_tampered_manifest_or_payload_refused(self):
        self.sign([self.dl])
        put(f"{self.bundle}/ota_payload_package.tar.gz", b"evil")
        self.assertTrue(any("sha256 mismatch" in w for w in self.verify()))
        m = json.loads(J.read(f"{self.bundle}/manifest.json"))
        m["version"] = "9.9.9"
        put(f"{self.bundle}/manifest.json", json.dumps(m))
        self.assertTrue(any("signature" in w for w in self.verify()))

    def test_apply_stages_marks_trial_then_runs_nvidia(self):
        import io, tarfile
        # A stand-in for NVIDIA's OTA tools: nv_ota_start.sh records that it ran and with which payload.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:bz2") as t:
            body = b"#!/bin/sh\necho \"$1\" > ran.txt\n"
            ti = tarfile.TarInfo("Linux_for_Tegra/tools/ota_tools/version_upgrade/nv_ota_start.sh")
            ti.size, ti.mode = len(body), 0o755
            t.addfile(ti, io.BytesIO(body))
        put(f"{self.bundle}/ota_tools_R39.2.1_aarch64.tbz2", buf.getvalue())
        m = J.make_manifest(self.bundle, version="0.3.0", compatible="onemind-jetson-orin", layout=DEVICE_LAYOUT,
                            l4t_from="36.5.2", l4t_to="39.2.1", requires_qspi="36.5.2", days=30)
        put(f"{self.bundle}/manifest.json", json.dumps(m))
        self.sign([self.dl])
        put(f"{self.bundle}/stray.sh", "#!/bin/sh\n")
        dev = FakeDevice(slot="A")
        self.assertEqual(J.apply_bundle(self.bundle, self.p, dev, J.Gate(self.p, dev)), 0)
        self.assertEqual(J.read(self.p.pending), "B 0.3.0\n")
        ran = os.path.join(self.p.ota_work, "Linux_for_Tegra/tools/ota_tools/version_upgrade/ran.txt")
        self.assertEqual(J.read(ran).strip(), os.path.join(self.p.ota_dir, "ota_payload_package.tar.gz"))
        self.assertFalse(os.path.exists(os.path.join(self.p.ota_work, "bundle", "stray.sh")), "only listed files staged")
        self.assertEqual(J.apply_bundle(self.bundle, self.p, dev, J.Gate(self.p, dev)), 2, "refused while a trial is pending")

    def test_other_ca_refused(self):
        self.sign([self.dl])
        subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes", "-days", "2",
                        "-subj", "/CN=other", "-keyout", f"{self.ca}/k2", "-out", self.p.keyring], capture_output=True, check=True)
        self.assertTrue(any("signature" in w for w in self.verify()))


SAMPLE_XML = """<?xml version="1.0"?>
<!-- NVIDIA sample -->
<partition_layout version="01.00.0000">
    <device type="external" instance="0" sector_size="512" num_sectors="EXT_NUM_SECTORS" >
        <partition name="APP" id="1" type="data"><size> APPSIZE </size><allocation_attribute> 0x8 </allocation_attribute></partition>
        <partition name="APP_b" id="2" type="data"><size> APPSIZE </size><allocation_attribute> 0x8 </allocation_attribute></partition>
        <partition name="secondary_gpt" type="secondary_gpt"><size> 0xFFFFFFFFFFFFFFFF </size></partition>
    </device>
</partition_layout>
"""


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.src, self.dst = os.path.join(self.d, "ab.xml"), os.path.join(self.d, "om.xml")
        put(self.src, SAMPLE_XML)

    def test_data_partition_after_app_b_before_secondary_gpt(self):
        LAY.add_data(self.src, self.dst)
        names = re.findall(r'partition name="([^"]+)"', open(self.dst).read())
        self.assertEqual(names, ["APP", "APP_b", "onemind-data", "secondary_gpt"])
        self.assertIn("0x808", open(self.dst).read())
        self.assertIn("NVIDIA sample", open(self.dst).read(), "comments kept")
        self.assertEqual(open(self.src).read(), SAMPLE_XML, "NVIDIA's file untouched")

    def test_refuses_non_ab_and_double_add(self):
        put(self.src, SAMPLE_XML.replace('"APP_b"', '"APPX"'))
        with self.assertRaises(SystemExit):
            LAY.add_data(self.src, self.dst)
        put(self.src, SAMPLE_XML)
        LAY.add_data(self.src, self.dst)
        with self.assertRaises(SystemExit):
            LAY.add_data(self.dst, os.path.join(self.d, "again.xml"))

    def test_record_matches_gate_flags(self):
        out = os.path.join(self.d, "rec.json")
        LAY.main(["record", "--out", out, "--layout-xml", self.src, "--layout-xml-name", "x.xml", "--l4t", "39.2.1",
                  "--target-board", "jetson-orin-nano-devkit", "--external-device", "nvme0n1"])
        rec = json.load(open(out))
        self.assertEqual(J.layout_mismatch(rec, DEVICE_LAYOUT), [])


class PinsTests(unittest.TestCase):
    def test_pins_sh_equals_lock(self):
        lock = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))["jetson"]
        pins = open(os.path.join(BOARD, "pins.sh")).read()
        for ver in ("39.2.1", "36.5.2"):
            rel = lock["l4t"][ver]
            self.assertIn(rel["url"].rstrip("/"), pins)
            for key in ("bsp", "sample_rootfs", "ota_tools"):
                self.assertIn(rel[key]["file"], pins, f"{ver} {key}")
                self.assertIn(rel[key]["sha256"], pins, f"{ver} {key}")

    def test_board_yaml_matches_lock(self):
        lock = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))["jetson"]
        board = yaml.safe_load(open(os.path.join(BOARD, "board.yaml")))
        self.assertEqual(str(board["l4t"]), lock["target"])
        self.assertEqual(str(board["l4t_base_for_ota"]), lock["ota_base"])
        self.assertFalse(board["published"])


class HookFilesTests(unittest.TestCase):
    def test_hook_execs_gate_and_drop_ins_block_verify(self):
        r = os.path.join(BOARD, "rootfs")
        self.assertIn("onemind-jetson gate", open(f"{r}/usr/sbin/user_rootfs_validation.sh").read())
        self.assertTrue(os.access(f"{r}/usr/sbin/user_rootfs_validation.sh", os.X_OK))
        for u in ("nv-rootfs-validation-config", "l4t-rootfs-validation-config"):
            self.assertIn("Type=oneshot", open(f"{r}/etc/systemd/system/{u}.service.d/50-onemind-gate.conf").read())
        self.assertIn("ExecStartPre=/usr/lib/onemind/jetson/onemind-jetson wait-pass",
                      open(f"{r}/etc/systemd/system/nv-l4t-bootloader-config.service.d/50-onemind-require-gate.conf").read())


if __name__ == "__main__":
    unittest.main()
