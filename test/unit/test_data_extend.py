# SPDX-License-Identifier: Apache-2.0
"""IMG-02 (#149): the data partition grows to the disk the image was written to, and never does anything else
to it. plan() is the whole decision; the sfdisk test applies it to a real GPT in a sparse file (Linux)."""
import copy, importlib.util, json, os, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib")
spec = importlib.util.spec_from_file_location("data_extend", os.path.join(BASE, "onemind", "data_extend.py"))
de = importlib.util.module_from_spec(spec)
spec.loader.exec_module(de)

GIB = 2 * 1024 * 1024            # sectors per GiB


def table(disk_gib=32, data_gib=None, label="gpt", extra=None):
    """The x86 layout of os/boards/x86_64-efi/layout.yaml, data last, as `sfdisk --json` prints it."""
    parts, start = [], 2048
    for n, (name, mib) in enumerate([("onemind-esp", 1024), ("onemind-boot-a", 512), ("onemind-boot-b", 512),
                                     ("onemind-system-a", 10240), ("onemind-system-b", 10240), ("onemind-recovery", 1024)], 1):
        size = mib * 2048
        parts.append({"node": f"/dev/vda{n}", "start": start, "size": size, "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                      "uuid": f"0000000{n}-0000-4000-8000-000000000000", "name": name})
        start += size
    last = (disk_gib * GIB - 34 - start) if data_gib is None else data_gib * GIB
    parts.append({"node": "/dev/vda7", "start": start, "size": last, "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                  "uuid": "0000000A-0000-4000-8000-000000000000", "name": "onemind-data"})
    parts += extra or []
    return {"partitiontable": {"label": label, "device": "/dev/vda", "unit": "sectors", "firstlba": 34,
                               "lastlba": 32 * GIB - 34, "sectorsize": 512, "partitions": parts}}


class Plan(unittest.TestCase):
    def test_a_bigger_disk_grows_only_the_data_partition(self):
        todo, _ = de.plan(table(32), 256 * GIB)
        self.assertEqual(todo["node"], "/dev/vda7")
        self.assertEqual(todo["number"], 7)
        self.assertGreater(todo["free_mib"], 200 * 1024)
        # same start, same type, same GUID, same name; only the size is the maximum
        self.assertIn("start=%d," % table(32)["partitiontable"]["partitions"][-1]["start"], todo["script"])
        self.assertIn("size=+", todo["script"])
        self.assertIn("uuid=0000000A-0000-4000-8000-000000000000", todo["script"])
        self.assertIn("name=onemind-data", todo["script"])

    def test_a_disk_the_image_already_fills_is_left_alone(self):
        todo, why = de.plan(table(32), 32 * GIB)
        self.assertIsNone(todo)
        self.assertIn("fills", why)

    def test_a_few_spare_sectors_are_rounding_not_space(self):
        self.assertIsNone(de.plan(table(32), 32 * GIB + 4000)[0])

    def test_never_when_the_data_partition_is_not_last(self):
        after = [{"node": "/dev/vda8", "start": 31 * GIB, "size": 1 * GIB, "type": "x", "uuid": "y", "name": "other"}]
        t = table(30, data_gib=2, extra=after)
        todo, why = de.plan(t, 256 * GIB)
        self.assertIsNone(todo)
        self.assertIn("not the last", why)

    def test_never_on_a_non_gpt_or_odd_sector_disk(self):
        self.assertIsNone(de.plan(table(32, label="dos"), 256 * GIB)[0])
        t = table(32)
        t["partitiontable"]["sectorsize"] = 4096
        self.assertIsNone(de.plan(t, 256 * GIB)[0])

    def test_never_unless_exactly_one_data_partition(self):
        t = table(32)
        t["partitiontable"]["partitions"].pop()
        self.assertIsNone(de.plan(t, 256 * GIB)[0])
        t = table(32)
        twin = copy.deepcopy(t["partitiontable"]["partitions"][-1])
        twin["node"], twin["start"] = "/dev/vda8", twin["start"] + twin["size"]
        t["partitiontable"]["partitions"].append(twin)
        self.assertIsNone(de.plan(t, 512 * GIB)[0])

    def test_never_shrinks_when_the_disk_is_smaller_than_the_table(self):
        self.assertIsNone(de.plan(table(32), 16 * GIB)[0])

    def test_nvme_style_node_names(self):
        t = table(32)
        for p in t["partitiontable"]["partitions"]:
            p["node"] = p["node"].replace("vda", "nvme0n1p")
        self.assertEqual(de.plan(t, 256 * GIB)[0]["number"], 7)


@unittest.skipUnless(shutil.which("sfdisk"), "needs util-linux sfdisk (Linux)")
class RealTable(unittest.TestCase):
    """The decision applied to a real GPT: the partition grows, nothing else moves, the backup header follows."""

    def test_growing_in_a_sparse_disk_file(self):
        with tempfile.TemporaryDirectory() as t:
            disk = os.path.join(t, "disk.img")
            with open(disk, "wb") as f:
                f.truncate(2 * 1024**3)                              # the "build" disk: 2 GiB
            spec = ("label: gpt\nunit: sectors\n\n"
                    "start=2048, size=64MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name=onemind-esp\n"
                    "size=512MiB, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name=onemind-system-a\n"
                    "type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name=onemind-data, uuid=0000000A-0000-4000-8000-000000000000\n")
            subprocess.run(["sfdisk", "--quiet", disk], input=spec, text=True, check=True, capture_output=True)
            before = json.loads(subprocess.run(["sfdisk", "--json", disk], text=True, check=True, capture_output=True).stdout)
            with open(disk, "r+b") as f:
                f.truncate(8 * 1024**3)                              # the same image written to an 8 GiB disk
            todo, _ = de.plan(json.loads(subprocess.run(["sfdisk", "--json", disk], text=True, check=True,
                                                        capture_output=True).stdout), 8 * 1024**3 // 512)
            self.assertIsNotNone(todo)
            subprocess.run(["sfdisk", "--quiet", "--no-reread", "--no-tell-kernel", "-N", str(todo["number"]), disk],
                           input=todo["script"], text=True, check=True, capture_output=True)
            after = json.loads(subprocess.run(["sfdisk", "--json", disk], text=True, check=True, capture_output=True).stdout)
            b, a = before["partitiontable"]["partitions"], after["partitiontable"]["partitions"]
            self.assertEqual(a[:2], b[:2])                           # the other partitions did not move or change
            self.assertEqual((a[2]["start"], a[2]["uuid"], a[2]["name"], a[2]["type"]),
                             (b[2]["start"], b[2]["uuid"], b[2]["name"], b[2]["type"]))
            self.assertGreater(a[2]["size"], b[2]["size"] * 3)       # 2 GiB -> 8 GiB disk
            self.assertEqual(after["partitiontable"]["lastlba"], 8 * 1024**3 // 512 - 34)
            check = subprocess.run(["sfdisk", "--verify", disk], text=True, capture_output=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIsNone(de.plan(after, 8 * 1024**3 // 512)[0])  # and the next boot has nothing to do


class NeverFailsTheBoot(unittest.TestCase):
    """Growing is a convenience: every way it can go wrong ends in exit 0 and a log line (CI run 43801035540:
    a failed unit is fatal to the health gate)."""

    def run_with(self, boom):
        saved = (de.main, de.say)
        lines = []
        de.say = lines.append
        def main():
            raise boom
        de.main = main
        try:
            return de.safe_main(), lines
        finally:
            de.main, de.say = saved

    def test_a_failed_command_is_logged_and_exits_zero(self):
        rc, lines = self.run_with(subprocess.CalledProcessError(2, ["blkid", "/dev/x"], stderr="boom"))
        self.assertEqual(rc, 0)
        self.assertIn("blkid", lines[0])

    def test_a_missing_tool_exits_zero(self):
        self.assertEqual(self.run_with(FileNotFoundError("sfdisk"))[0], 0)

    def test_an_odd_table_exits_zero(self):
        self.assertEqual(self.run_with(KeyError("uuid"))[0], 0)

    def test_the_unit_ignores_a_failed_start(self):
        unit = open(os.path.join(BASE, "systemd", "system", "onemind-data-extend.service")).read()
        self.assertRegex(unit, r"(?m)^ExecStart=-/usr/lib/onemind/data-extend$")


class PausesUdevWhileTheTableChanges(unittest.TestCase):
    """Issue 391: udev must not read the table while it is rewritten. Without the pause, systemd saw the
    data partition's device names vanish and unmounted /data on about one cloud first boot in fifty."""

    def run_rewrite(self, fail_at=None, udevadm_ok=True):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd[0])
            if cmd[0] == fail_at:
                raise subprocess.CalledProcessError(1, cmd, "", "boom")
            return ""

        def fake_subprocess_run(cmd, **kw):
            calls.append(" ".join(cmd[:3]))
            return subprocess.CompletedProcess(cmd, 0 if udevadm_ok or cmd[2] != "--stop-exec-queue" else 1)

        old_run, old_sub = de.run, de.subprocess.run
        de.run, de.subprocess.run = fake_run, fake_subprocess_run
        try:
            try:
                de.rewrite_entry(7, "/dev/vda", "script", "/dev/vda7")
            except subprocess.CalledProcessError:
                pass
        finally:
            de.run, de.subprocess.run = old_run, old_sub
        return calls

    def test_queue_is_paused_around_both_table_steps_and_settled_after(self):
        calls = self.run_rewrite()
        self.assertEqual(calls, ["udevadm control --stop-exec-queue", "sfdisk", "partx",
                                 "udevadm control --start-exec-queue", "udevadm settle --timeout=30", "resize2fs"])

    def test_queue_is_started_again_when_a_step_fails(self):
        for failing in ("sfdisk", "partx"):
            calls = self.run_rewrite(fail_at=failing)
            self.assertIn("udevadm control --start-exec-queue", calls, failing)
            self.assertNotIn("resize2fs", calls, failing)

    def test_no_start_when_the_pause_did_not_happen(self):
        calls = self.run_rewrite(udevadm_ok=False)
        self.assertNotIn("udevadm control --start-exec-queue", calls)
        self.assertIn("resize2fs", calls)


class ToolsAreInTheImage(unittest.TestCase):
    """The first CI boot failed because sfdisk was not installed: Debian 13 ships it in `fdisk`, not util-linux.
    Every tool data_extend.py runs must come from a package the image lists."""
    PACKAGE = {"lsblk": "util-linux", "blkid": "util-linux", "blockdev": "util-linux", "partx": "util-linux",
               "sfdisk": "fdisk", "resize2fs": "e2fsprogs", "udevadm": "udev", "df": None}     # None: coreutils, always there

    def test_every_tool_it_runs_is_mapped_to_a_package(self):
        with open(os.path.join(BASE, "onemind", "data_extend.py")) as f:
            src = f.read()
        import re
        tools = set(re.findall(r'run\(\["([a-z0-9]+)"', src))
        self.assertTrue({"sfdisk", "resize2fs", "lsblk"} <= tools, tools)
        self.assertEqual(tools - set(self.PACKAGE), set(), "a new tool: add its package to PACKAGE and the package lists")

    def test_those_packages_are_in_both_package_lists(self):
        for leg in ("debian", "ubuntu"):
            with open(os.path.join(ROOT, "os", "rootfs", "packages", f"{leg}-common.txt")) as f:
                words = {w for line in f for w in line.split("#")[0].split()}
            for tool, pkg in self.PACKAGE.items():
                if pkg:
                    self.assertIn(pkg, words, f"{tool} needs package {pkg} in {leg}-common.txt")


class Wiring(unittest.TestCase):
    def read(self, *p):
        with open(os.path.join(ROOT, *p)) as f:
            return f.read()

    def test_service_runs_after_data_is_mounted_and_before_what_fills_it(self):
        unit = self.read("os", "rootfs", "layers", "base", "usr", "lib", "systemd", "system", "onemind-data-extend.service")
        self.assertIn("ConditionPathIsMountPoint=/data", unit)
        self.assertIn("After=local-fs.target", unit)
        self.assertRegex(unit, r"Before=.*k3s\.service")
        # First-boot setup must never wait for the grow: when it did, setup sometimes finished after the
        # health gate and smoke F1 failed (main after #318).
        before = [l for l in unit.splitlines() if l.startswith("Before=")]
        self.assertEqual(len(before), 1)
        self.assertNotIn("onemind-firstboot", before[0])
        self.assertIn("DefaultDependencies=no", unit)
        self.assertIn("Conflicts=shutdown.target", unit)
        self.assertNotIn("Requires", unit)                          # a failed /data must not fail boot (nofail, recovery mode)

    def test_it_is_enabled_by_a_wants_symlink_and_the_script_is_executable(self):
        link = os.path.join(BASE, "systemd", "system", "multi-user.target.wants", "onemind-data-extend.service")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), "../onemind-data-extend.service")
        self.assertTrue(os.access(os.path.join(BASE, "onemind", "data-extend"), os.X_OK))

    def test_it_runs_with_the_gateway_python_because_the_image_has_no_system_python(self):
        self.assertIn("/usr/lib/onemind/gateway/venv/bin/python3 -I /usr/lib/onemind/data_extend.py",
                      self.read("os", "rootfs", "layers", "base", "usr", "lib", "onemind", "data-extend"))

    def test_the_data_partition_is_the_last_one_on_every_gpt_board_layout(self):
        import yaml
        for board in ("x86_64-efi", "arm64-efi", "vm"):
            parts = yaml.safe_load(self.read("os", "boards", board, "layout.yaml"))["partitions"]
            self.assertEqual(parts[-1]["label"], "onemind-data", board)
            self.assertEqual(parts[-1]["fs"], "ext4", board)


if __name__ == "__main__":
    unittest.main()
