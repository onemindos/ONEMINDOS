# SPDX-License-Identifier: Apache-2.0
"""S-5: the GPU image variant. No GPU is needed: these check that the variant exists only when its board is
selected, that every closed package has a licence row, that the pins equal os/versions.lock.yaml, and that the
files the build runs are well formed. The first real test is test/gpu/gpu-lab-kit.sh on a GPU machine."""
import os, re, subprocess, sys, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
import assemble  # noqa: E402

BOARD = "x86_64-efi-nvidia"
BD = os.path.join(ROOT, "os", "boards", BOARD)
LOCK = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))["gpu"]
read = lambda *p: open(os.path.join(ROOT, *p)).read()


def rows(path):
    return [ln.split("|") for ln in read(path).splitlines() if ln.strip() and not ln.startswith("#")]


def words(path):
    out = []
    for ln in read(path).splitlines():
        out += ln.split("#")[0].split()
    return out


class Selection(unittest.TestCase):
    def test_the_board_loads_and_is_its_own_update_channel(self):
        b = assemble.load_board(BOARD)
        plain = assemble.load_board("x86_64-efi")
        self.assertEqual(b["name"], BOARD)
        self.assertEqual(b["arch"], "amd64")
        self.assertNotEqual(b["compatible"], plain["compatible"])   # RAUC refuses a cross-variant update
        self.assertEqual(b["layout_data"]["partitions"], plain["layout_data"]["partitions"])

    def test_nothing_nvidia_is_in_the_default_build(self):
        # every file the default x86 image is built from; boards other than the GPU board and Jetson (NVIDIA L4T, D-007)
        files = ["os/rootfs/Containerfile", "os/rootfs/sources/configure-apt.sh"]   # the Makefile mentions Jetson, not this build
        for d in ("os/rootfs/packages", "os/boards/x86_64-efi", "os/boards/vm", "os/boards/arm64-efi", "os/boards/vm-do"):
            for dp, _, fs in os.walk(os.path.join(ROOT, d)):
                files += [os.path.relpath(os.path.join(dp, f), ROOT) for f in fs]
        for f in files:
            self.assertIsNone(re.search(r"nvidia|cuda", read(f).lower()), f)

    def test_non_free_is_only_enabled_by_the_gpu_board(self):
        self.assertIn("non-free", read("os/boards/x86_64-efi-nvidia/post-install.sh"))
        self.assertNotRegex(read("os/rootfs/sources/configure-apt.sh"), r"Components: .*non-free(?!-firmware)")

    def test_the_build_scripts_parse(self):
        for f in ("os/boards/x86_64-efi-nvidia/post-install.sh", "test/gpu/gpu-lab-kit.sh",
                  "os/boards/x86_64-efi-nvidia/rootfs/usr/lib/onemind/gpu/onemind-nvidia-setup"):
            subprocess.run(["sh", "-n", os.path.join(ROOT, f)], check=True)


class Licences(unittest.TestCase):
    def test_every_package_has_a_licence_row(self):
        have = {r[0] for r in rows("os/boards/x86_64-efi-nvidia/gpu/licences.txt")}
        for p in words("os/boards/x86_64-efi-nvidia/gpu/packages.txt"):
            self.assertIn(p, have, p)
        for f in LOCK["toolkit"]["files"]:
            self.assertIn(f.split("_")[0], have, f)

    def test_each_row_has_four_columns_and_a_licence(self):
        for r in rows("os/boards/x86_64-efi-nvidia/gpu/licences.txt"):
            self.assertEqual(len(r), 4, r)
            self.assertTrue(all(c.strip() for c in r), r)


class Pins(unittest.TestCase):
    def test_toolkit_files_equal_the_lock(self):
        got = {a: b for a, b in rows("os/boards/x86_64-efi-nvidia/gpu/toolkit.txt")}
        self.assertEqual(got, LOCK["toolkit"]["files"])
        for f, sha in got.items():
            self.assertRegex(sha, r"^[0-9a-f]{64}$")
            self.assertIn(f"_{LOCK['toolkit']['version']}_", f)

    def test_the_downloader_checks_every_hash(self):
        s = read("os/boards/x86_64-efi-nvidia/post-install.sh")
        self.assertIn("sha256sum -c", s)
        self.assertIn(LOCK["toolkit"]["base_url"], s)

    def test_device_plugin_is_pinned_by_digest(self):
        s = read("os/boards/x86_64-efi-nvidia/rootfs/usr/lib/onemind/gpu/onemind-gpu.yaml")
        self.assertIn(f"{LOCK['device_plugin']['image']}@{LOCK['device_plugin']['digest']}", s)
        docs = list(yaml.safe_load_all(s))
        self.assertEqual([d["kind"] for d in docs], ["RuntimeClass", "DaemonSet"])
        self.assertEqual(docs[0]["metadata"]["name"], "nvidia")
        self.assertEqual(docs[0]["handler"], "nvidia")
        self.assertEqual(docs[1]["spec"]["template"]["spec"]["runtimeClassName"], "nvidia")

    def test_driver_branch_is_from_the_debian_snapshot_not_a_download(self):
        self.assertNotIn("developer.download.nvidia.com", read("os/boards/x86_64-efi-nvidia/post-install.sh"))
        self.assertRegex(LOCK["driver"]["version"], r"^550\.")


class NoGpuBox(unittest.TestCase):
    def test_setup_unit_runs_before_k3s_and_only_acts_on_an_nvidia_card(self):
        unit = read("os/boards/x86_64-efi-nvidia/rootfs/usr/lib/systemd/system/onemind-nvidia-setup.service")
        self.assertIn("Before=k3s.service", unit)
        script = read("os/boards/x86_64-efi-nvidia/rootfs/usr/lib/onemind/gpu/onemind-nvidia-setup")
        self.assertIn("0x10de", script)
        self.assertRegex(script, r"else\n\s+rm -f \"\$DEST\"")   # no card: the plugin manifest is removed, exit 0

    def test_nouveau_is_blacklisted(self):
        self.assertIn("blacklist nouveau", read("os/boards/x86_64-efi-nvidia/rootfs/etc/modprobe.d/onemind-nvidia.conf"))


if __name__ == "__main__":
    unittest.main()
