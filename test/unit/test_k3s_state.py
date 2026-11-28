# SPDX-License-Identifier: Apache-2.0
"""onemind_k3s_state: durable writes and k3s settle (VM 501 bug 1, CRITERIA-FIRSTBOOT.md F26), against a temp root. Standard library only, no Docker or VM."""
import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
import onemind_k3s_state as ks  # noqa: E402

PEM = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


class Atomic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sub", "f.txt")

    def test_writes_content_mode_and_leaves_no_temp(self):
        ks.atomic_write(self.path, "hello\n", 0o640)
        self.assertEqual(open(self.path).read(), "hello\n")
        self.assertEqual(os.stat(self.path).st_mode & 0o7777, 0o640)
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["f.txt"])

    def test_accepts_bytes(self):
        ks.atomic_write(self.path, b"\x00\x01", 0o600)
        self.assertEqual(open(self.path, "rb").read(), b"\x00\x01")

    def test_order_is_file_fsync_then_rename_then_directory_fsync(self):
        import stat
        events = []
        real_fsync, real_replace = os.fsync, os.replace

        def fsync(fd):
            events.append("fsync-dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "fsync-file")
            real_fsync(fd)

        def replace(a, b):
            events.append("rename")
            real_replace(a, b)
        with mock.patch("os.fsync", side_effect=fsync), mock.patch("os.replace", side_effect=replace):
            ks.atomic_write(self.path, "x")
        self.assertEqual(events, ["fsync-file", "rename", "fsync-dir"])

    def test_failure_keeps_the_old_file_and_removes_the_temp(self):
        ks.atomic_write(self.path, "old")
        with mock.patch("os.replace", side_effect=OSError("disk gone")):
            with self.assertRaises(OSError):
                ks.atomic_write(self.path, "new")
        self.assertEqual(open(self.path).read(), "old")
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["f.txt"])

    def test_sync_fs_falls_back_to_sync(self):
        with mock.patch("ctypes.CDLL", side_effect=OSError("no libc")), mock.patch("os.sync") as s:
            self.assertTrue(ks.sync_fs(self.tmp.name))
        s.assert_called_once()

    def test_sync_fs_uses_syncfs_when_there(self):
        lib = mock.Mock()
        lib.syncfs.return_value = 0
        with mock.patch("ctypes.CDLL", return_value=lib), mock.patch("os.sync") as s:
            self.assertTrue(ks.sync_fs(self.tmp.name))
        lib.syncfs.assert_called_once()
        s.assert_not_called()


class Box(unittest.TestCase):
    """A fake /data with what k3s makes on its first start, plus the owner's data."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = ks.Paths(self.tmp.name)
        self.mk()
        for t in ("os.sync",):
            m = mock.patch(t)
            m.start()
            self.addCleanup(m.stop)

    def put(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode())

    def mk(self):
        p = self.p
        self.put(os.path.join(p.server, "token"), "K10abc::server:def\n")
        self.put(os.path.join(p.server, "agent-token"), "K10abc::node:ghi\n")
        for n in ("server-ca.crt", "server-ca.key", "client-admin.crt", "client-admin.key"):
            self.put(os.path.join(p.server, "tls", n), PEM)
        self.put(os.path.join(p.server, "cred", "passwd"), "pw,admin,admin,system:masters\n")
        self.put(os.path.join(p.server, "cred", "encryption-config.json"), "{}\n")
        for n in ("client-kubelet.crt", "client-kubelet.key", "serving-kubelet.crt"):
            self.put(os.path.join(p.agent, n), PEM)
        self.put(os.path.join(p.agent, "kubelet.kubeconfig"), "apiVersion: v1\n")
        self.put(os.path.join(p.agent, "etc", "containerd", "config.toml"), "version = 2\n")
        self.put(p.node_password, "s3cret\n")
        self.put(os.path.join(p.server, "manifests", "coredns.yaml"), "kind: x\n")
        self.put(os.path.join(p.agent, "containerd", "blob"), "image layers\n")
        self.put(os.path.join(p.k3s, "storage", "pvc-1_apps_db", "data"), "the app's data\n")
        self.put(os.path.join(p.data, "onemind", "owner-file"), "owner data\n")
        self.put(os.path.join(p.data, "onemind", "gateway", "gateway.db"), "gateway database\n")
        self.put(p.role, "hub\n")

    def truncate(self, files):
        for f in files:
            open(f, "wb").close()

    def everything_k3s(self):
        return ks.k3s_files(self.p)


class Detect(Box):
    def test_a_healthy_box_is_not_damaged(self):
        self.assertEqual(ks.find_damaged(self.p), [])

    def test_files_cover_the_criteria_set(self):
        names = {os.path.relpath(f, self.p.data) for f in self.everything_k3s()}
        for want in ("k3s/server/token", "k3s/server/tls/server-ca.crt", "k3s/server/tls/server-ca.key",
                     "k3s/agent/client-kubelet.key", "k3s/agent/kubelet.kubeconfig", "state/etc-rancher-node/password",
                     "k3s/agent/etc/containerd/config.toml"):
            self.assertIn(want, names)
        self.assertNotIn("k3s/storage/pvc-1_apps_db/data", names)
        self.assertNotIn("k3s/server/manifests/coredns.yaml", names)

    def test_empty_and_torn_pem_are_damage(self):
        self.truncate([os.path.join(self.p.server, "token")])
        self.put(os.path.join(self.p.agent, "client-kubelet.crt"), b"-----BEG")
        why = dict((os.path.basename(f), w) for f, w in ks.find_damaged(self.p))
        self.assertEqual(why, {"token": "empty", "client-kubelet.crt": "not PEM"})


class Settle(Box):
    def go(self, **kw):
        syncs = []
        rc = ks.settle(self.p, sleep=lambda s: None, sync=lambda: syncs.append(1) or True, **kw)
        return rc, len(syncs)

    def test_syncs_while_waiting_then_marks_done_after_the_last_sync(self):
        answers = iter([False, False, True])
        order = []
        rc = ks.settle(self.p, sleep=lambda s: None, ready=lambda: next(answers),
                       sync=lambda: order.append("sync") or True)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(order.count("sync"), 4)     # every poll, plus the final one after k3s answered
        self.assertTrue(os.path.isfile(self.p.settled))

    def test_marker_only_after_final_sync(self):
        seen = []
        def sync():
            seen.append(os.path.exists(self.p.settled))
            return True
        ks.settle(self.p, sleep=lambda s: None, ready=lambda: True, sync=sync)
        self.assertEqual(seen, [False, False])
        self.assertTrue(os.path.exists(self.p.settled))

    def test_already_settled_does_nothing(self):
        self.put(self.p.settled, "x\n")
        rc, n = self.go(ready=lambda: True)
        self.assertEqual((rc, n), (0, 0))

    def test_not_a_hub_does_nothing(self):
        self.put(self.p.role, "leaf\n")
        rc, n = self.go(ready=lambda: True)
        self.assertEqual((rc, n), (0, 0))
        self.assertFalse(os.path.exists(self.p.settled))

    def test_timeout_syncs_and_does_not_mark(self):
        rc, n = self.go(ready=lambda: False, timeout=10)
        self.assertEqual(rc, 1)
        self.assertGreaterEqual(n, 5)
        self.assertFalse(os.path.exists(self.p.settled))

    def test_damaged_files_after_k3s_answers_are_not_marked_done(self):
        self.truncate([self.p.node_password])
        rc, _ = self.go(ready=lambda: True)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.p.settled))


def pod(ns, phase="Running", ready=True):
    return {"metadata": {"namespace": ns, "name": "x"},
            "status": {"phase": phase, "conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}}


class FirstSetupDone(unittest.TestCase):
    """settle marks the first setup done only once the OS's own pods are up (their images unpacked and started):
    the VM 501 F13 runs (F26 now) showed coredns and helm crash with SIGSEGV after a cut that came after /readyz but before
    their images were on the disk."""

    def test_api_ready_but_system_pods_starting_is_not_done(self):
        self.assertFalse(ks.system_pods_ready({"items": []}))
        self.assertFalse(ks.system_pods_ready({"items": [pod("kube-system"), pod("kube-system", "Pending", False)]}))
        self.assertFalse(ks.system_pods_ready({"items": [pod("onemind-system", ready=False)]}))

    def test_ready_and_finished_system_pods_are_done_and_apps_never_count(self):
        items = [pod("kube-system"), pod("kube-system", "Succeeded", False), pod("onemind-system"),
                 pod("apps", "Pending", False), pod("apps", ready=False)]
        self.assertTrue(ks.system_pods_ready({"items": items}))
        self.assertFalse(ks.system_pods_ready({"items": [pod("apps")]}))     # only apps: the OS's own are missing

    def test_k3s_ready_needs_readyz_and_the_pods(self):
        with tempfile.TemporaryDirectory() as d:
            p = ks.Paths(d)
            self.assertFalse(ks.k3s_ready(p))                                # no kubeconfig on this boot yet
            os.makedirs(os.path.dirname(p.kubeconfig))
            open(p.kubeconfig, "w").close()
            ok = mock.Mock(returncode=0, stdout=json.dumps({"items": [pod("kube-system")]}).encode())
            starting = mock.Mock(returncode=0, stdout=json.dumps({"items": [pod("kube-system", ready=False)]}).encode())
            with mock.patch.object(ks.subprocess, "run", side_effect=[mock.Mock(returncode=1)]) as run:
                self.assertFalse(ks.k3s_ready(p))
                self.assertEqual(run.call_count, 1)                           # /readyz failed: pods not asked
            with mock.patch.object(ks.subprocess, "run", side_effect=[mock.Mock(returncode=0), starting]):
                self.assertFalse(ks.k3s_ready(p))
            with mock.patch.object(ks.subprocess, "run", side_effect=[mock.Mock(returncode=0), ok]) as run:
                self.assertTrue(ks.k3s_ready(p))
                self.assertIn("--raw=/readyz", run.call_args_list[0].args[0])
                self.assertEqual(run.call_args_list[1].args[0][-4:], ["pods", "-A", "-o", "json"])


class DataMountedWithoutDelayedAllocation(unittest.TestCase):
    """/data never uses delayed allocation: with it a power cut leaves files whose metadata reached the disk but whose
    data did not (0-byte certificates, torn image binaries; VM 501 bug 1). The ext4-only boards say nodelalloc in their
    fstab. The x86 and cloud /data line is "auto" (ext4 before #152, btrfs since): an option the filesystem does not
    know makes the mount fail, so data-durable sets nodelalloc (ext4) or flushoncommit (btrfs) once the type is known."""
    EXT4_FSTABS = ("os/boards/rpi5/rootfs/etc/fstab", "os/boards/jetson-orin/rootfs/etc/onemind/jetson-fstab")
    AUTO_FSTAB = "os/rootfs/layers/base/etc/fstab"
    SCRIPT = os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib", "onemind", "data-durable")
    DROPIN = os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib", "systemd", "system",
                          "onemind-data-layout.service.d", "20-durable.conf")

    @staticmethod
    def data_line(rel):
        lines = [l.split() for l in open(os.path.join(ROOT, rel)) if l.strip() and not l.startswith("#")]
        data = [f for f in lines if len(f) >= 4 and f[1] == "/data"]
        return data

    def test_ext4_boards_have_nodelalloc_in_fstab(self):
        for rel in self.EXT4_FSTABS:
            data = self.data_line(rel)
            self.assertEqual(len(data), 1, rel)
            self.assertEqual(data[0][2], "ext4", rel)
            opts = data[0][3].split(",")
            self.assertIn("nodelalloc", opts, rel)
            self.assertNotIn("delalloc", opts, rel)
            self.assertFalse([o for o in opts if o.startswith("data=") and o != "data=ordered"], rel)

    def test_the_btrfs_board_has_no_ext4_only_option(self):
        lines = [l.split() for l in open(os.path.join(ROOT, "os/rootfs/layers/base/etc/fstab")) if l.strip() and not l.startswith("#")]
        data = [f for f in lines if len(f) >= 4 and f[1] == "/data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0][2], "auto")
        self.assertNotIn("nodelalloc", data[0][3].split(","))

    def test_auto_line_carries_no_filesystem_specific_option(self):
        data = self.data_line(self.AUTO_FSTAB)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0][2], "auto")
        opts = data[0][3].split(",")
        # btrfs refuses nodelalloc and ext4 refuses flushoncommit: either would leave /data unmounted on the other
        for o in ("nodelalloc", "delalloc", "flushoncommit", "noflushoncommit"):
            self.assertNotIn(o, opts)
        self.assertFalse([o for o in opts if o.startswith("data=")])

    def test_data_layout_runs_it_before_the_folders_and_never_fails_the_boot(self):
        text = open(self.DROPIN).read()
        self.assertIn("ExecStartPre=-/usr/lib/onemind/data-durable /data", text)
        self.assertTrue(os.access(self.SCRIPT, os.X_OK))

    def run_script(self, fstype, opts, mount_rc=0):
        """data-durable with fake findmnt and mount on PATH; returns (exit code, output, mount's arguments or None)."""
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "mount.args")
            with open(os.path.join(d, "findmnt"), "w") as f:
                f.write("#!/bin/sh\ncase \"$*\" in *FSTYPE*) printf '%s\\n' \"$FAKE_FSTYPE\" ;; *OPTIONS*) printf '%s\\n' "
                        "\"$FAKE_OPTS\" ;; esac\n[ -n \"$FAKE_FSTYPE\" ]\n")
            with open(os.path.join(d, "mount"), "w") as f:
                f.write(f"#!/bin/sh\necho \"$*\" > {log}\nexit {mount_rc}\n")
            for n in ("findmnt", "mount"):
                os.chmod(os.path.join(d, n), 0o755)
            env = dict(os.environ, PATH=d + os.pathsep + "/usr/bin:/bin", FAKE_FSTYPE=fstype, FAKE_OPTS=opts)
            r = subprocess.run(["/bin/sh", self.SCRIPT, "/data"], env=env, capture_output=True, text=True, check=False)
            args = None
            if os.path.exists(log):
                with open(log) as f:
                    args = f.read().strip()
            return r.returncode, r.stdout + r.stderr, args

    def test_ext4_is_remounted_with_nodelalloc(self):
        rc, out, args = self.run_script("ext4", "rw,noatime")
        self.assertEqual((rc, args), (0, "-o remount,nodelalloc /data"), out)

    def test_btrfs_is_remounted_with_flushoncommit(self):
        rc, out, args = self.run_script("btrfs", "rw,noatime,ssd,space_cache=v2,subvolid=256,subvol=/@")
        self.assertEqual((rc, args), (0, "-o remount,flushoncommit /data"), out)

    def test_nothing_to_do_when_the_option_is_there_or_data_is_not_mounted(self):
        self.assertIsNone(self.run_script("ext4", "rw,noatime,nodelalloc")[2])
        self.assertIsNone(self.run_script("btrfs", "rw,flushoncommit,subvol=/@")[2])
        self.assertIsNone(self.run_script("", "")[2])
        self.assertIsNone(self.run_script("xfs", "rw")[2])

    def test_a_failed_remount_only_logs(self):
        rc, out, args = self.run_script("btrfs", "rw", mount_rc=32)
        self.assertEqual(rc, 0)
        self.assertIn("could not remount", out)


class FirstbootUsesIt(unittest.TestCase):
    def test_firstboot_write_is_durable_and_atomic(self):
        import onemind_firstboot as fb
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "etc", "role")
            with mock.patch.object(fb.durable, "atomic_write", wraps=fb.durable.atomic_write) as aw:
                self.assertTrue(fb.write(path, "hub\n", 0o644))
                self.assertFalse(fb.write(path, "hub\n", 0o644))     # unchanged: nothing written again
            aw.assert_called_once()
            self.assertEqual(open(path).read(), "hub\n")

    def test_hub_starts_the_settle_unit_on_every_boot(self):
        import onemind_firstboot as fb
        self.assertIn("onemind-k3s-settle.service", fb.ROLE_UNITS["hub"])
        self.assertIn("onemind-k3s-settle.service", fb.LEGACY_ROLE_UNITS["hub"])
        for role in ("worker", "leaf"):
            self.assertNotIn("onemind-k3s-settle.service", fb.ROLE_UNITS[role])


if __name__ == "__main__":
    unittest.main()
