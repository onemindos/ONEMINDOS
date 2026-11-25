# SPDX-License-Identifier: Apache-2.0
"""onemind_k3s_state recover and the owner-approved reset (VM 501 bug 1, CRITERIA-FIRSTBOOT.md section 9 F14 and
the unsafe case, section 10 F15), against a temp root. Standard library only, no Docker or VM. The unsafe case of
section 9 (the datastore holds the owner's apps, so rebuilding the cluster state would lose them) must repair
nothing, log and alert: test_owner_apps_in_the_datastore_wait_for_approval and the tests after it."""
import json, os, sqlite3, subprocess, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_k3s_state import Box as StateBox, ks  # noqa: E402  (the fake /data of the durability tests)

NOW = 1_800_000_000.0


class Box(StateBox):
    """The durability tests' fake /data, plus k3s's datastore (kine's sqlite table) and the gateway's kubeconfig."""

    def mk(self):
        super().mk()
        p = self.p
        os.makedirs(os.path.dirname(p.db), exist_ok=True)
        self.db(["/registry/deployments/kube-system/coredns", "/registry/secrets/kube-system/x"])
        self.put(os.path.join(p.data, "onemind", "gateway", "kubeconfig"), "apiVersion: v1\n")

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

    def owner_data(self):
        out = {}
        for rel in (("k3s", "storage", "pvc-1_apps_db", "data"), ("onemind", "owner-file"), ("onemind", "gateway", "gateway.db")):
            with open(os.path.join(self.p.data, *rel), "rb") as f:
                out[rel] = f.read()
        return out



class Healthy(Box):
    def test_a_healthy_box_is_left_alone(self):
        self.assertIsNone(ks.recover(self.p, now=NOW))
        self.assertFalse(os.path.exists(self.p.recovery))


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

    def test_waiting_for_approval_is_said_once_not_on_every_restart(self):
        self.db(["/registry/deployments/apps/jellyfin"])
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks, "say") as say:
            ks.recover(self.p, now=NOW)
            ks.recover(self.p, now=NOW + 5)
            ks.recover(self.p, now=NOW + 10)
        self.assertEqual(say.call_count, 1)
        self.assertEqual(self.last()["action"], "needs-approval")

    def test_deleted_and_system_workloads_do_not_count(self):
        self.db(["/registry/deployments/kube-system/coredns", "/registry/statefulsets/onemind-system/core"],
                deleted=["/registry/deployments/apps/gone"])
        self.assertEqual(ks.owner_workloads(self.p), ("none", []))
        self.db(["/registry/persistentvolumeclaims/apps/data"])
        self.assertEqual(ks.owner_workloads(self.p)[0], "found")

    def test_unreadable_datastore_waits_for_approval(self):
        # kine runs sqlite in WAL mode; a datastore sqlite cannot read after a power cut may still hold the
        # owner's apps, so nothing is moved without the owner (PR #1155 review, CHANGES 1).
        self.put(self.p.db, b"this is not sqlite at all, a torn first write " * 50)
        self.assertEqual(ks.owner_workloads(self.p)[0], "unreadable")
        self.truncate(self.everything_k3s())
        before = [(f, os.path.getsize(f)) for f in self.everything_k3s()]
        rec = ks.recover(self.p, now=NOW)
        self.assertEqual(rec["action"], "needs-approval")
        self.assertEqual(rec["datastore"], "unreadable")
        self.assertIn("could not be read", rec["reason"])
        self.assertEqual([(f, os.path.getsize(f)) for f in self.everything_k3s()], before)   # nothing moved
        self.assertTrue(os.path.isfile(self.p.db))
        self.assertFalse([d for d in os.listdir(self.p.recovery) if d != "last.json"])
        # the owner's approval still resets it
        self.assertEqual(ks.recover(self.p, force=True, now=NOW + 60)["action"], "reset")
        self.assertFalse(os.path.lexists(self.p.db))

    def test_empty_datastore_with_a_write_ahead_log_is_not_called_empty(self):
        self.put(self.p.db, b"")
        self.assertEqual(ks.owner_workloads(self.p), ("none", []))
        self.put(self.p.db + "-wal", b"wal frames that sqlite could not replay")
        self.assertEqual(ks.owner_workloads(self.p), ("unreadable", []))
        self.assertEqual(os.path.getsize(self.p.db + "-wal"), 39)    # the check never opened it (sqlite would drop the log)
        self.truncate(self.everything_k3s())
        self.assertEqual(ks.recover(self.p, now=NOW)["action"], "needs-approval")

    def test_apps_still_in_the_write_ahead_log_are_found_and_the_log_is_kept(self):
        # kine's WAL mode: a writer that dies (power cut) before a checkpoint leaves the newest rows in -wal only
        os.unlink(self.p.db)
        code = ("import os, sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute('pragma journal_mode=wal'); "
                "c.execute('pragma wal_autocheckpoint=0'); c.execute('create table kine (id INTEGER PRIMARY KEY "
                "AUTOINCREMENT, name TEXT, deleted INTEGER)'); c.commit(); c.execute(\"insert into kine (name, deleted) "
                "values ('/registry/deployments/apps/jellyfin', 0)\"); c.commit(); os._exit(0)")
        subprocess.run([sys.executable, "-I", "-c", code, self.p.db], check=True)
        wal = os.path.getsize(self.p.db + "-wal")
        self.assertGreater(wal, 0)
        self.assertEqual(ks.owner_workloads(self.p), ("found", ["/registry/deployments/apps/jellyfin"]))
        self.assertEqual(os.path.getsize(self.p.db + "-wal"), wal)

    def test_empty_datastore_is_repaired(self):
        self.put(self.p.db, b"")
        self.truncate(self.everything_k3s())
        self.assertEqual(ks.recover(self.p, now=NOW)["action"], "repaired")

    def test_only_a_hub_is_repaired(self):
        self.truncate(self.everything_k3s())
        for role in ("worker\n", "leaf\n", ""):
            self.put(self.p.role, role)
            self.assertIsNone(ks.recover(self.p, now=NOW), role)
        os.unlink(self.p.role)
        self.assertIsNone(ks.recover(self.p, now=NOW))
        self.assertFalse(os.path.exists(self.p.recovery))

    def test_two_repairs_in_the_same_second_get_their_own_folders(self):
        self.truncate([self.p.node_password])
        first = ks.recover(self.p, now=NOW)["quarantine"]
        self.put(self.p.node_password, b"")
        second = ks.recover(self.p, now=NOW)["quarantine"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.last()["action"], "repaired")
        self.assertTrue(os.path.isfile(os.path.join(self.p.data, first, "state", "etc-rancher-node", "password")))
        self.assertTrue(os.path.isfile(os.path.join(self.p.data, second, "state", "etc-rancher-node", "password")))

    def test_a_move_that_fails_half_way_is_recorded(self):
        self.truncate(self.everything_k3s())
        real = os.rename
        calls = []

        def flaky(src, dst):
            calls.append(src)
            if len(calls) == 3:
                raise OSError(28, "No space left on device")
            return real(src, dst)

        with mock.patch.object(ks.os, "rename", side_effect=flaky):
            rec = ks.recover(self.p, now=NOW)
        self.assertEqual(rec["action"], "partial")
        last = self.last()
        self.assertEqual(last["action"], "partial")
        self.assertEqual(len(last["moved"]), 2)
        self.assertGreater(len(last["planned"]), 2)
        self.assertIn("No space left", last["error"])
        for rel in last["moved"]:                       # what moved is kept, nothing deleted
            self.assertTrue(os.path.lexists(os.path.join(self.p.data, last["quarantine"], rel)), rel)

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


if __name__ == "__main__":
    unittest.main()
