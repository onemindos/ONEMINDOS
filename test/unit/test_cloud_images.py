# SPDX-License-Identifier: Apache-2.0
"""Cloud images (docs/leap/core/CLOUD-IMAGES.md): boards, datasource order, layouts, and the
seeds and QEMU profiles of test/qemu/cloudboot.py (CRITERIA-CLOUD.md §3)."""
import importlib.util, os, re, stat, sys, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
sys.path.insert(0, os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind"))
import assemble  # noqa: E402
import onemind_firstboot as fb  # noqa: E402

_spec = importlib.util.spec_from_file_location("cloudboot", os.path.join(ROOT, "test", "qemu", "cloudboot.py"))
cb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cb)

BOARDS = os.path.join(ROOT, "os", "boards")
CLOUDS = sorted(d[len("cloud-"):] for d in os.listdir(BOARDS) if d.startswith("cloud-"))
# CRITERIA-CLOUD.md §3, copied here on purpose: the profile, the overlay and the criteria must agree.
EXPECTED = {"aws": ["Ec2", "NoCloud", "None"], "gcp": ["GCE", "NoCloud", "None"],
            "azure": ["Azure", "NoCloud", "None"], "hetzner": ["Hetzner", "NoCloud", "None"],
            "proxmox": ["NoCloud", "ConfigDrive", "None"]}
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOneMindTestKeyOnlyNotARealKeyAAAAAAAAAAAA onemind-test"


def load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def board_yaml(name):
    return load(os.path.join(BOARDS, name, "board.yaml"))


def overlay_dsl(cloud):
    p = os.path.join(BOARDS, f"cloud-{cloud}", "overlay", "etc", "cloud", "cloud.cfg.d", "90-onemind-datasource.cfg")
    return load(p)["datasource_list"]


class Boards(unittest.TestCase):
    def test_every_cloud_board_has_a_profile_and_back(self):
        self.assertEqual(CLOUDS, sorted(cb.PROFILES))
        self.assertEqual(CLOUDS, sorted(EXPECTED))

    def test_datasource_order_matches_criteria(self):
        for c in CLOUDS:
            self.assertEqual(overlay_dsl(c), EXPECTED[c], c)
            self.assertEqual(cb.PROFILES[c]["datasources"], EXPECTED[c], c)
            self.assertEqual(EXPECTED[c][-1], "None", c)

    def test_generic_cloud_list_covers_every_cloud(self):
        base = load(os.path.join(BOARDS, "cloud", "rootfs", "etc", "cloud", "cloud.cfg"))
        for c in CLOUDS:
            self.assertIn(EXPECTED[c][0], base["datasource_list"], c)
        self.assertEqual(base["system_info"]["default_user"]["name"], "admin")   # "onemind" is the gateway's user
        self.assertEqual(base["growpart"]["devices"], ["/data"])

    def test_boards_assemble_from_the_cloud_rootfs_with_own_compatible(self):
        seen = set()
        for c in CLOUDS:
            b = board_yaml(f"cloud-{c}")
            self.assertEqual(b["name"], f"cloud-{c}")
            self.assertEqual(b["rootfs_from"], "cloud")
            self.assertEqual(b["compatible"], f"onemind-cloud-{c}")
            self.assertTrue(os.path.isdir(os.path.join(BOARDS, f"cloud-{c}", b["overlay"])))
            self.assertFalse(os.path.exists(os.path.join(BOARDS, f"cloud-{c}", "rootfs")), "no rootfs of its own")
            seen.add(b["compatible"])
        self.assertEqual(len(seen), len(CLOUDS))
        self.assertEqual(board_yaml("cloud")["arch"], "amd64")

    def test_route_matches_firmware(self):
        for c in CLOUDS:
            b = assemble.load_board(f"cloud-{c}")
            bios = cb.PROFILES[c]["firmware"] == "seabios"
            self.assertEqual(b["route"], "grub-bios" if bios else "grub-efi", c)
            types = [p["type"] for p in b["layout_data"]["partitions"]]
            self.assertEqual(types[0] == "bios", bios, c)

    def test_layouts_fit_every_cloud(self):
        base = [p["label"] for p in assemble.load_board("cloud")["layout_data"]["partitions"]]
        for c in CLOUDS:
            lay = assemble.load_board(f"cloud-{c}")["layout_data"]
            labels = [p["label"] for p in lay["partitions"] if p["type"] != "bios"]
            self.assertEqual(labels, base, c)
            size = assemble.mib(lay["disk_size"])
            self.assertEqual(size % 1024, 0, f"{c}: GCE needs whole GiB")       # and so whole MiB for Azure
            self.assertLessEqual(size, 16 * 1024, f"{c}: fits the smallest disks (Hetzner 40 GB, EBS/PD/Azure any)")
            for s in ("onemind-system-a", "onemind-system-b"):
                self.assertGreaterEqual(assemble.mib(assemble.part(lay, s)["size"]), 4096, c)
            self.assertEqual(lay["partitions"][-1]["label"], "onemind-data", "data last, so growpart can grow it")

    def test_grub_cfg_renders(self):
        for c in CLOUDS:
            cfg = assemble.render_grub_cfg(assemble.load_board(f"cloud-{c}"))
            self.assertIsNone(re.search(r"@[A-Z_]+@", cfg), c)
            self.assertIn("console=ttyS0", cfg)                  # every cloud's serial console is ttyS0

    def test_scripts_are_executable(self):
        for f in ("cloud-image.sh", "package.sh", "aws-import.sh", "gcp-import.sh", "azure-import.sh",
                  "hetzner-snapshot.sh", "proxmox-template.sh"):
            m = os.stat(os.path.join(ROOT, "os", "cloud", f)).st_mode
            self.assertTrue(m & stat.S_IXUSR, f)


class Seeds(unittest.TestCase):
    def test_user_data_gives_hub_to_firstboot(self):
        for c in CLOUDS:
            f = cb.seed_files(c, KEY, cb.instance_id(c, bytes(range(16))))
            cfg = fb.validate(fb.parse_userdata(f["user-data"]))
            self.assertEqual(cfg["role"], "hub", c)
            self.assertEqual(cfg["name"], f"OneMind {c}")

    def test_no_role_seed_leaves_firstboot_to_the_wizard(self):
        for c in CLOUDS:
            f = cb.seed_files(c, KEY, "x", role=False)
            self.assertIsNone(fb.parse_userdata(f["user-data"]), c)

    def test_key_where_the_cloud_puts_it(self):
        for c in CLOUDS:
            f = cb.seed_files(c, KEY, "x")
            md, ud = yaml.safe_load(f["meta-data"]), yaml.safe_load(f["user-data"])
            if cb.PROFILES[c]["key_in"] == "meta-data":
                self.assertEqual(md["public-keys"], [KEY], c)
                self.assertNotIn("ssh_authorized_keys", ud, c)
            else:
                self.assertEqual(ud["ssh_authorized_keys"], [KEY], c)
                self.assertNotIn("public-keys", md, c)
            self.assertEqual(md["instance-id"], "x")

    def test_network_configs(self):
        gcp = yaml.safe_load(cb.seed_files("gcp", KEY, "x")["network-config"])
        self.assertEqual(gcp["ethernets"]["nic0"]["mtu"], 1460)
        het = yaml.safe_load(cb.seed_files("hetzner", KEY, "x")["network-config"])["config"][0]
        self.assertEqual(het["name"], "eth0")
        self.assertIn({"type": "static", "address": cb.HETZNER_V6, "gateway": "fe80::1", "ipv6": True}, het["subnets"])
        self.assertTrue(cb.HETZNER_V6.startswith("2001:db8:"))   # documentation prefix only
        pve = yaml.safe_load(cb.seed_files("proxmox", KEY, "x")["network-config"])["config"][0]
        self.assertEqual(pve["mac_address"], cb.MAC)
        for c in ("aws", "azure"):
            self.assertNotIn("network-config", cb.seed_files(c, KEY, "x"))

    def test_instance_id_formats(self):
        rnd = bytes(range(16))
        self.assertRegex(cb.instance_id("aws", rnd), r"^i-[0-9a-f]{17}$")
        self.assertRegex(cb.instance_id("gcp", rnd), r"^[1-9][0-9]{18}$")
        self.assertRegex(cb.instance_id("azure", rnd), r"^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$")
        self.assertRegex(cb.instance_id("hetzner", rnd), r"^[1-9][0-9]{7}$")
        self.assertRegex(cb.instance_id("proxmox", rnd), r"^[0-9a-f]{40}$")


class Qemu(unittest.TestCase):
    PORTS = {"ssh": 2222, "http": 8888}

    def cmd(self, c):
        return " ".join(cb.qemu_cmd(c, "d.qcow2", "seed.img", ["b.img"], self.PORTS, "tcg", "max"))

    def test_disk_bus_and_boot_order(self):
        self.assertIn("nvme,drive=root,serial=onemindroot,bootindex=0", self.cmd("aws"))
        for c in ("gcp", "azure", "hetzner", "proxmox"):
            self.assertIn("scsi-hd,drive=root,bus=scsi0.0,bootindex=0", self.cmd(c), c)
        for c in CLOUDS:
            s = self.cmd(c)
            self.assertEqual(s.count("bootindex"), 1, c)          # the seed's FAT boot sector is never booted
            self.assertIn("restrict=on", s)
            self.assertIn("hostfwd=tcp:127.0.0.1:2222-:22", s)
            self.assertIn("hostfwd=tcp:127.0.0.1:8888-:8080", s)
            self.assertIn("file=seed.img", s)

    def test_machine(self):
        self.assertIn("-machine pc ", self.cmd("hetzner"))
        self.assertIn("-machine q35 ", self.cmd("aws"))

    def test_default_tests_follow_criteria(self):
        self.assertEqual(cb.default_tests("aws"), ["C0", "C1", "C2", "C3", "C4", "C6"])
        self.assertEqual(cb.default_tests("hetzner"), ["C0", "C1", "C2", "C3", "C4", "C5"])
        self.assertEqual(cb.default_tests("gcp"), ["C0", "C1", "C2", "C3", "C4"])


if __name__ == "__main__":
    unittest.main()
