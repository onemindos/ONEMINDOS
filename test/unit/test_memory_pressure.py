# SPDX-License-Identifier: Apache-2.0
"""Control plane protection under memory and disk pressure (image audit P0, refs #234). Static checks on the
files that ship in the image, and the parsers of test/qemu/memorypressure.py. Stdlib only."""
import hashlib, importlib.util, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = "os/rootfs/layers/base"
ONE = "os/rootfs/layers/onemind"


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def qemu_module():
    sp = importlib.util.spec_from_file_location("memorypressure", os.path.join(ROOT, "test/qemu/memorypressure.py"))
    m = importlib.util.module_from_spec(sp)
    try:
        sp.loader.exec_module(m)
    except ModuleNotFoundError as e:       # firstboot.py needs PyYAML only inside f0, not at import
        raise unittest.SkipTest(str(e))
    return m


class Units(unittest.TestCase):
    DROPINS = {
        BASE + "/usr/lib/systemd/system/k3s.service.d": "512M",
        ONE + "/usr/lib/systemd/system/onemind-gateway.service.d": "128M",
        ONE + "/usr/lib/systemd/system/onemind-nats.service.d": "32M",
        ONE + "/usr/lib/systemd/system/onemindd.service.d": "32M",
    }

    def test_every_control_plane_unit_is_protected(self):
        for d, memmin in self.DROPINS.items():
            t = rd(d, "10-onemind-memory.conf")
            self.assertRegex(t, r"(?m)^\[Service\]$", d)
            self.assertRegex(t, r"(?m)^OOMScoreAdjust=-900$", d)
            self.assertRegex(t, r"(?m)^MemoryMin=%s$" % memmin, d)
            # the unit the drop-in belongs to exists
            self.assertTrue(os.path.exists(os.path.join(ROOT, d[:-2])), d)

    def test_zram_is_configured_and_installed(self):
        c = rd(BASE, "etc/systemd/zram-generator.conf")
        self.assertIn("[zram0]", c)
        self.assertIn("compression-algorithm = zstd", c)
        self.assertRegex(c, r"(?m)^zram-size = min\(ram / 2, 4096\)$")
        for leg in ("debian", "ubuntu"):
            self.assertRegex(rd("os/rootfs/packages", leg + "-common.txt"), r"(?m)^systemd-zram-generator$", leg)
        self.assertRegex(rd(BASE, "etc/sysctl.d/90-onemind-memory.conf"), r"(?m)^vm\.swappiness = 100$")

    def test_kubelet_reserves_and_swap(self):
        y = rd(BASE, "etc/rancher/k3s/config.yaml.d/10-onemind-reserve.yaml")
        for want in ("system-reserved=", "kube-reserved=", "eviction-hard=memory.available<", "fail-swap-on=false"):
            self.assertIn(want, y)
        # the reserves are real memory, at least 1 GiB together (M0 asserts the same on the booted node)
        mem = [int(x) for x in re.findall(r"reserved=cpu=\w+,memory=(\d+)Mi", y)]
        self.assertEqual(len(mem), 2)
        self.assertGreaterEqual(sum(mem), 1024)

    def test_journal_cap_and_noatime(self):
        j = rd(BASE, "etc/systemd/journald.conf.d/10-onemind.conf")
        self.assertRegex(j, r"(?m)^SystemMaxUse=500M$")
        for f in (BASE + "/etc/fstab", "os/boards/rpi5/rootfs/etc/fstab"):
            line = [l for l in rd(f).splitlines() if re.match(r"PARTLABEL=onemind-data|PARTUUID=\S+\s+/data", l)]
            self.assertEqual(len(line), 1, f)
            opts = line[0].split()[3].split(",")
            self.assertIn("noatime", opts, f)
            self.assertIn("nofail", opts, f)    # a dead data disk must still not fail local-fs (recovery mode)


class Harness(unittest.TestCase):
    def test_criteria_hash_is_registered(self):
        h = hashlib.sha256(open(os.path.join(ROOT, "test/qemu/CRITERIA-MEMORY.md"), "rb").read()).hexdigest()
        self.assertIn(h + "  CRITERIA-MEMORY.md", rd("test/qemu/PREREGISTRATION.sha256"))

    def test_vm_memory_is_overridable_and_default_unchanged(self):
        s = rd("test/qemu/run-tests.py")
        self.assertIn('os.environ.get("ONEMIND_QEMU_MEM", "3072")', s)
        self.assertIn("ONEMIND_QEMU_MEM=8192", rd("Makefile"))

    def test_parsers(self):
        m = qemu_module()
        self.assertEqual(m.parse_probes("PROBE 1 200\nPROBE 3 200\nPROBE 5 000\nnoise\n"), (3, ["000"]))
        self.assertEqual(m.parse_probes(""), (0, []))
        st = m.unit_state("AFTER k3s pid=10 restarts=0\nAFTER onemindd pid=11 restarts=2\n", "AFTER")
        self.assertEqual(st, {"k3s": ("10", "0"), "onemindd": ("11", "2")})
        v = m.oom_victims("x\nOut of memory: Killed process 77 (k3s-server) total-vm:1kB\nOut of memory: Killed process 8 (python3)")
        self.assertEqual(v, ["k3s-server", "python3"])
        self.assertEqual(m.control_victims(v), ["k3s-server"])
        self.assertEqual(m.control_victims(["python3"]), [])

    def test_hog_is_six_gib(self):
        m = qemu_module()
        self.assertIn("n=6<<30", m.HOG)


if __name__ == "__main__":
    unittest.main()
