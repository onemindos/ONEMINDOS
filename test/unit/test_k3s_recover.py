# SPDX-License-Identifier: Apache-2.0
"""onemind_k3s_state recover and the owner-approved reset (VM 501 bug 1, CRITERIA-FIRSTBOOT.md section 21 F27 and
the unsafe case, section 22 F28), against a temp root. Standard library only, no Docker or VM. The unsafe case of
section 21 (the datastore holds the owner's apps, so rebuilding the cluster state would lose them) must repair
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
        # only a copy of the datastore was made (never a move), in a folder of its own
        extra = [d for d in os.listdir(self.p.recovery) if d != "last.json"]
        self.assertEqual(len(extra), 1)
        self.assertTrue(extra[0].endswith(ks.COPY_SUFFIX))
        self.assertEqual(rec["datastore_copy"], os.path.join("onemind", "k3s-recovery", extra[0]))
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
        for exc in (OSError("read-only"), ValueError("bug"), KeyError("bug")):
            with mock.patch.object(ks, "recover", side_effect=exc):
                self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0, exc)

    def test_main_recover_repairs(self):
        self.truncate([self.p.node_password])
        self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)
        self.assertEqual(self.last()["action"], "repaired")


class HoldWhileWaiting(Box):
    """PR #1155 review (head 9d92f776): waiting for the owner must keep k3s from starting. recover is k3s.service's
    ExecCondition; it exits HOLD (3), so systemd skips k3s and does not restart it, and kine never opens the old
    datastore (opening a 0-byte state.db with a write-ahead log, even to read it, deletes the log)."""

    def empty_db_with_wal(self):
        os.unlink(self.p.db)
        code = ("import os, sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute('pragma journal_mode=wal'); "
                "c.execute('pragma wal_autocheckpoint=0'); c.execute('create table kine (id INTEGER PRIMARY KEY "
                "AUTOINCREMENT, name TEXT, deleted INTEGER)'); c.commit(); c.execute(\"insert into kine (name, deleted) "
                "values ('/registry/deployments/apps/jellyfin', 0)\"); c.commit(); os._exit(0)")
        subprocess.run([sys.executable, "-I", "-c", code, self.p.db], check=True)
        with open(self.p.db, "wb"):
            pass                                        # the power cut left the main file empty, the log is not
        with open(self.p.db + "-wal", "rb") as f:
            return f.read()

    def test_owner_apps_hold_k3s(self):
        self.db(["/registry/deployments/apps/jellyfin"])
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks, "say"):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)     # every start, said once
        self.assertIn("k3s is held", self.reasons_said())

    def reasons_said(self):
        with mock.patch.object(ks, "console") as console, mock.patch.object(ks, "log"):
            os.unlink(self.p.last)
            ks.recover(self.p, now=NOW + 100)
        return " ".join(c.args[1] for c in console.call_args_list)

    def test_a_repair_does_not_hold_k3s(self):
        self.truncate([self.p.node_password])
        self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)
        self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)      # healthy now: nothing to do

    def test_empty_datastore_with_a_log_is_held_copied_and_kept(self):
        wal = self.empty_db_with_wal()
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks, "say"):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)
        rec = self.last()
        self.assertEqual((rec["action"], rec["datastore"]), ("needs-approval", "unreadable"))
        # the original is where it was, untouched: the main file still empty, the log byte-identical
        self.assertEqual(os.path.getsize(self.p.db), 0)
        with open(self.p.db + "-wal", "rb") as f:
            self.assertEqual(f.read(), wal)
        # and a copy of both is kept, which sqlite can read: the owner's app is in it
        copy = os.path.join(self.p.data, rec["datastore_copy"], "k3s", "server", "db")
        with open(os.path.join(copy, "state.db-wal"), "rb") as f:
            self.assertEqual(f.read(), wal)
        self.assertEqual(os.path.getsize(os.path.join(copy, "state.db")), 0)
        # a copy is not a repair: it never counts toward the repeat limit, and it is made once, not on every start
        self.assertEqual(ks._recent_repairs(self.p, NOW), 0)
        with mock.patch.object(ks, "say"):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)
        self.assertEqual(len([d for d in os.listdir(self.p.recovery) if d.endswith(ks.COPY_SUFFIX)]), 1)
        # the owner approves: the datastore folder moves (rename, so the log goes with it) and k3s may start
        rec = ks.recover(self.p, force=True, now=NOW + 60)
        self.assertEqual(rec["action"], "reset")
        with open(os.path.join(self.p.data, rec["quarantine"], "k3s", "server", "db", "state.db-wal"), "rb") as f:
            self.assertEqual(f.read(), wal)
        self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)

    def test_a_copy_that_does_not_fit_is_removed_and_k3s_stays_held(self):
        self.empty_db_with_wal()
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks.shutil, "copyfile", side_effect=OSError(28, "No space left on device")), \
                mock.patch.object(ks, "say"):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)
        self.assertNotIn("datastore_copy", self.last())
        self.assertFalse([d for d in os.listdir(self.p.recovery) if d.endswith(ks.COPY_SUFFIX)])

    def test_no_room_for_a_quarantine_folder_still_holds_k3s(self):
        self.empty_db_with_wal()
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks.os, "mkdir", side_effect=OSError(28, "No space left on device")), \
                mock.patch.object(ks, "say"):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)

    def test_a_record_that_cannot_be_written_still_holds_k3s(self):
        self.db(["/registry/deployments/apps/jellyfin"])
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks, "atomic_write", side_effect=OSError(28, "No space left on device")), \
                mock.patch.object(ks, "say"):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)

    def test_the_repeat_limit_holds_k3s_too(self):
        for i in range(ks.REPEAT_LIMIT):
            os.makedirs(os.path.join(self.p.recovery, f"old{i}"))
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks, "say"):
            self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), ks.HOLD)


class AgentOnly(Box):
    """The earlier #1155 review's follow-up: damage limited to the agent's own files is repaired without the
    datastore, so a box with apps keeps its cluster (CRITERIA-FIRSTBOOT.md F33). k3s's agent asks its server for
    these certificates again at every start and makes a missing key."""

    AGENT = ("client-kubelet.crt", "client-kubelet.key", "serving-kubelet.crt", "kubelet.kubeconfig")

    def setUp(self):
        super().setUp()
        self.db(["/registry/deployments/kube-system/coredns", "/registry/deployments/apps/jellyfin"])

    def test_agent_certificates_alone_are_repaired_with_apps_in_the_cluster(self):
        with open(self.p.db, "rb") as f:
            db = f.read()
        self.truncate([os.path.join(self.p.agent, "client-kubelet.key")])
        with mock.patch.object(ks, "owner_workloads", wraps=ks.owner_workloads) as ow:
            rec = ks.recover(self.p, now=NOW)
        ow.assert_not_called()                          # the datastore is not even read
        self.assertEqual((rec["action"], rec["scope"]), ("repaired", "agent"))
        self.assertEqual(sorted(rec["moved"]), sorted(os.path.join("k3s", "agent", n) for n in self.AGENT))
        for n in self.AGENT:
            self.assertFalse(os.path.lexists(os.path.join(self.p.agent, n)), n)
        with open(self.p.db, "rb") as f:
            self.assertEqual(f.read(), db)
        for kept in (os.path.join(self.p.server, "token"), os.path.join(self.p.server, "tls", "server-ca.crt"),
                     os.path.join(self.p.agent, "etc", "containerd", "config.toml"), self.p.node_password,
                     self.p.gw_kubeconfig, os.path.join(self.p.agent, "containerd", "blob")):
            self.assertTrue(os.path.isfile(kept), kept)
        self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)

    def test_agent_certificate_and_agent_config_together(self):
        self.truncate([os.path.join(self.p.agent, "serving-kubelet.crt"),
                       os.path.join(self.p.agent, "etc", "containerd", "config.toml")])
        rec = ks.recover(self.p, now=NOW)
        self.assertEqual(rec["scope"], "agent")
        self.assertIn(os.path.join("k3s", "agent", "etc"), rec["moved"])
        self.assertTrue(all(m.startswith(os.path.join("k3s", "agent") + os.sep) for m in rec["moved"]))

    def test_a_server_file_too_means_the_cluster_and_the_owner_decides(self):
        self.truncate([os.path.join(self.p.agent, "client-kubelet.crt"), os.path.join(self.p.server, "token")])
        with mock.patch.object(ks, "say"):
            rec = ks.recover(self.p, now=NOW)
        self.assertEqual((rec["action"], rec["scope"]), ("needs-approval", "cluster"))
        self.assertTrue(os.path.isfile(os.path.join(self.p.agent, "client-kubelet.crt")))

    def test_the_node_password_is_not_an_agent_file(self):
        # the server remembers it in the datastore, so a new one would be refused: never repaired on its own
        self.assertFalse(ks.agent_scope(self.p, [(self.p.node_password, "empty")]))


class Role(Box):
    """PR #1155 review: a missing or damaged role file used to return silently, so a box hit by the bug got no
    repair and no alert."""

    def state(self, data):
        self.put(self.p.state, data if isinstance(data, str) else json.dumps(data))

    def test_state_json_names_the_role_when_the_role_file_is_damaged(self):
        self.state({"role": "hub", "node_id": "ab12"})
        self.truncate(self.everything_k3s() + [self.p.role])
        self.assertEqual(ks.box_role(self.p), ("hub", "state.json"))
        self.assertEqual(ks.recover(self.p, now=NOW)["action"], "repaired")

    def test_a_configured_box_with_no_role_anywhere_says_so_once(self):
        self.state("{ torn")
        os.unlink(self.p.role)
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks, "console") as console:
            self.assertIsNone(ks.recover(self.p, now=NOW))
            self.assertIsNone(ks.recover(self.p, now=NOW + 5))
        self.assertEqual(console.call_count, 1)
        self.assertIn("NOT checked", console.call_args.args[1])
        last = self.last()
        self.assertEqual(last["action"], "not-checked")
        self.assertGreater(len(last["damaged"]), 5)
        # nothing was moved and k3s is not held (nobody knows it is a hub)
        self.assertEqual(ks.main(["--root", self.tmp.name, "recover"]), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.p.server, "token")))

    def test_a_box_before_first_boot_is_quiet(self):
        os.unlink(self.p.role)
        self.truncate(self.everything_k3s())
        with mock.patch.object(ks, "console") as console:
            self.assertIsNone(ks.recover(self.p, now=NOW))
        console.assert_not_called()
        self.assertFalse(os.path.exists(self.p.recovery))

    def test_worker_and_leaf_from_state_json_are_left_alone(self):
        os.unlink(self.p.role)
        self.truncate(self.everything_k3s())
        for role in ("worker", "leaf"):
            self.state({"role": role})
            self.assertIsNone(ks.recover(self.p, now=NOW), role)
        self.assertFalse(os.path.exists(self.p.recovery))


class Wiring(unittest.TestCase):
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def read(self, *rel):
        with open(os.path.join(self.ROOT, *rel)) as f:
            return f.read()

    def test_recover_is_k3s_execcondition(self):
        text = self.read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "k3s.service.d",
                         "30-onemind-recover.conf")
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        self.assertIn("ExecCondition=/usr/lib/onemind/onemind-k3s-state recover", lines)
        self.assertFalse([l for l in lines if l.startswith("ExecStartPre")])

    def test_wrapper_lets_only_the_hold_code_skip_k3s(self):
        import shutil as sh
        import tempfile
        wrapper = os.path.join(self.ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind-k3s-state")
        src = self.read("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind-k3s-state")
        self.assertTrue(os.access(wrapper, os.X_OK))
        with tempfile.TemporaryDirectory() as d:
            for rc, want in ((0, 0), (3, 3), (1, 0), (127, 0), (2, 0)):
                fake = os.path.join(d, "python3")
                with open(fake, "w") as f:
                    f.write(f"#!/bin/sh\nexit {rc}\n")
                os.chmod(fake, 0o755)
                script = os.path.join(d, "w.sh")
                with open(script, "w") as f:
                    f.write(src.replace("/usr/lib/onemind/gateway/venv/bin/python3", fake))
                r = subprocess.run(["/bin/sh", script, "recover"], capture_output=True, check=False)
                self.assertEqual(r.returncode, want, rc)
            self.assertTrue(sh.which("sh"))


if __name__ == "__main__":
    unittest.main()
