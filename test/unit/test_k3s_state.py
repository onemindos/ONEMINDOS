# SPDX-License-Identifier: Apache-2.0
"""onemind_k3s_state: durable writes, k3s settle and recover (VM 501 bug 1, CRITERIA-FIRSTBOOT.md F13/F14), against a
temp root. Standard library only, no Docker or VM."""
import json, os, sqlite3, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
import onemind_k3s_state as ks  # noqa: E402

PEM = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
NOW = 1_800_000_000.0


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
        os.makedirs(os.path.dirname(p.db), exist_ok=True)
        self.db(["/registry/deployments/kube-system/coredns", "/registry/secrets/kube-system/x"])
        self.put(os.path.join(p.data, "onemind", "gateway", "kubeconfig"), "apiVersion: v1\n")
        self.put(p.role, "hub\n")

    def db(self, names, deleted=()):
        con = sqlite3.connect(self.p.db)
        con.execute("DROP TABLE IF EXISTS kine")
        con.execute("CREATE TABLE kine (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created INTEGER, deleted INTEGER, "
                    "create_revision INTEGER, prev_revision INTEGER, lease INTEGER, value BLOB, old_value BLOB)")
        for n in names:
            con.execute("INSERT INTO kine (name, created, deleted) VALUES (?, 1, 0)", (n,))
        for n in deleted:
            con.execute("INSERT INTO kine (name, created, deleted) VALUES (?, 1, 0)", (n,))
            con.execute("INSERT INTO kine (name, created, deleted) VALUES (?, 1, 1)", (n,))
        con.commit()
        con.close()

    def last(self):
        with open(self.p.last) as f:
            return json.load(f)

    def truncate(self, files):
        for f in files:
            open(f, "wb").close()

    def owner_data(self):
        out = {}
        for rel in (("k3s", "storage", "pvc-1_apps_db", "data"), ("onemind", "owner-file"), ("onemind", "gateway", "gateway.db")):
            out[rel] = open(os.path.join(self.p.data, *rel), "rb").read()
        return out

    def everything_k3s(self):
        return ks.k3s_files(self.p)


class Detect(Box):
    def test_a_healthy_box_is_not_damaged(self):
        self.assertEqual(ks.find_damaged(self.p), [])
        self.assertIsNone(ks.recover(self.p, now=NOW))
        self.assertFalse(os.path.exists(self.p.recovery))

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


class Recover(Box):
    def test_everything_zeroed_is_rebuilt_without_touching_owner_data(self):
        before = self.owner_data()
        self.truncate(self.everything_k3s())
        rec = ks.recover(self.p, now=NOW)
        self.assertEqual(rec["action"], "repaired")
        self.assertEqual(self.owner_data(), before)
        # the damaged state is gone from where k3s looks and kept, empty, in the quarantine
        for sub in ("server/tls", "server/cred", "server/db", "server/token", "server/agent-token", "agent/etc"):
            self.assertFalse(os.path.lexists(os.path.join(self.p.k3s, sub)), sub)
        self.assertFalse(os.path.lexists(self.p.node_password))
        q = os.path.join(self.p.data, rec["quarantine"])
        self.assertTrue(os.path.isfile(os.path.join(q, "state", "etc-rancher-node", "password")))
        self.assertEqual(os.path.getsize(os.path.join(q, "k3s", "server", "token")), 0)
        # what the unit or k3s itself keeps stays
        self.assertTrue(os.path.isfile(os.path.join(self.p.server, "manifests", "coredns.yaml")))
        self.assertTrue(os.path.isfile(os.path.join(self.p.agent, "containerd", "blob")))
        self.assertEqual(self.last()["action"], "repaired")
        # the gateway's kubeconfig belongs to the replaced cluster: moved, so onemind-gateway-kube makes a new one
        self.assertFalse(os.path.lexists(self.p.gw_kubeconfig))
        self.assertTrue(os.path.isfile(os.path.join(q, "onemind", "gateway", "kubeconfig")))
        self.assertEqual(self.p.last, os.path.join(self.p.recovery, "last.json"))

    def test_marker_is_removed_so_settle_syncs_the_new_state(self):
        self.put(self.p.settled, "x\n")
        self.truncate([self.p.node_password])
        ks.recover(self.p, now=NOW)
        self.assertFalse(os.path.exists(self.p.settled))

    def test_only_agent_config_damaged_moves_only_that(self):
        self.truncate([os.path.join(self.p.agent, "etc", "containerd", "config.toml")])
        rec = ks.recover(self.p, now=NOW)
        self.assertEqual(rec["moved"], ["k3s/agent/etc"])
        self.assertTrue(os.path.isfile(os.path.join(self.p.server, "token")))
        self.assertTrue(os.path.isfile(self.p.db))
        self.assertTrue(os.path.isfile(self.p.gw_kubeconfig))

    def test_owner_apps_in_the_datastore_wait_for_approval(self):
        self.db(["/registry/deployments/kube-system/coredns", "/registry/deployments/apps/jellyfin"])
        self.truncate(self.everything_k3s())
        before = [(f, os.path.getsize(f)) for f in self.everything_k3s()]
        rec = ks.recover(self.p, now=NOW)
        self.assertEqual(rec["action"], "needs-approval")
        self.assertEqual(rec["datastore"], "found")
        self.assertEqual([(f, os.path.getsize(f)) for f in self.everything_k3s()], before)   # nothing moved
        self.assertTrue(os.path.isfile(self.p.db))
        self.assertEqual(self.last()["action"], "needs-approval")
        self.assertFalse([d for d in os.listdir(self.p.recovery) if d != "last.json"])

    def test_deleted_and_system_workloads_do_not_count(self):
        self.db(["/registry/deployments/kube-system/coredns", "/registry/statefulsets/onemind-system/core"],
                deleted=["/registry/deployments/apps/gone"])
        self.assertEqual(ks.owner_workloads(self.p), ("none", []))
        self.db(["/registry/persistentvolumeclaims/apps/data"])
        self.assertEqual(ks.owner_workloads(self.p)[0], "found")

    def test_unreadable_or_empty_datastore_is_repaired(self):
        self.put(self.p.db, b"this is not sqlite at all, a torn first write " * 50)
        self.assertEqual(ks.owner_workloads(self.p)[0], "unreadable")
        self.truncate(self.everything_k3s())
        self.assertEqual(ks.recover(self.p, now=NOW)["action"], "repaired")
        self.put(self.p.db, b"")
        self.assertEqual(ks.owner_workloads(self.p), ("none", []))

    def test_force_resets_even_with_apps_and_nothing_damaged(self):
        self.db(["/registry/deployments/apps/jellyfin"])
        before = self.owner_data()
        rec = ks.recover(self.p, force=True, now=NOW)
        self.assertEqual(rec["action"], "reset")
        self.assertFalse(os.path.lexists(self.p.db))
        self.assertEqual(self.owner_data(), before)

    def test_repair_loop_stops_and_waits_for_the_owner(self):
        for i in range(ks.REPEAT_LIMIT):
            os.makedirs(os.path.join(self.p.recovery, f"old{i}"))
        self.truncate(self.everything_k3s())
        rec = ks.recover(self.p)
        self.assertEqual(rec["action"], "needs-approval")
        self.assertTrue(os.path.isfile(os.path.join(self.p.server, "token")))

    def test_main_never_raises_into_k3s_start(self):
        self.truncate([self.p.node_password])
        with mock.patch.object(ks, "recover", side_effect=OSError("read-only")):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)

    def test_main_recover_repairs(self):
        self.truncate([self.p.node_password])
        self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)
        self.assertEqual(self.last()["action"], "repaired")


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
