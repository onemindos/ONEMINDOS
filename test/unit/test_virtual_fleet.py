# SPDX-License-Identifier: Apache-2.0
"""#864: the virtual fleet test's lab guards and judge (test/fleet).

The fleet itself runs on the Proxmox lab (test/fleet/README.md). Here: what it may touch (VM ids 500-509,
the memory budget, the 8 GiB floor, other VMs), how a run is judged (every check, the broken-image
negative control, three green runs in a row) and that nothing from the lab reaches a report.
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "test" / "fleet"


def load(name):
    spec = importlib.util.spec_from_file_location(name, FLEET / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = load("fleetcore")
ENV = {"ONEMIND_FLEET_PVE": "lab-host", "ONEMIND_FLEET_BRIDGE": "br9",
       "ONEMIND_FLEET_ADDRS": "192.0.2.10/24,192.0.2.11/24,192.0.2.12/24,192.0.2.13/24",
       "ONEMIND_FLEET_GW": "192.0.2.1", "ONEMIND_FLEET_STORAGE": "vmstore",
       "ONEMIND_FLEET_SNIPPETS": "snips", "ONEMIND_FLEET_SNIPPETS_DIR": "/srv/snips"}
FREE = """               total        used        free      shared  buff/cache   available
Mem:              78          27          {free}           0           0          {avail}
Swap:              0           0           0
"""
QM = """      VMID NAME                 STATUS     MEM(MiB)   BOOTDISK(GiB) PID
       200 onemind-hub-1        running    8192              40.00 3318
       500 onemind-fleet-hub    stopped    4096              16.00 0
       501 somebody-else        running    2048              16.00 99
"""


def run(results):
    return {cid: {"result": r, "evidence": "x"} for cid, r in results.items()}


class Guards(unittest.TestCase):
    def test_plan_is_one_hub_and_three_nodes_inside_500_509(self):
        vms = core.plan()
        self.assertEqual([v[0] for v in vms], [500, 501, 502, 503])
        self.assertEqual([v[2] for v in vms], ["hub", "node", "node", "node"])
        self.assertTrue(all(v[1].startswith(core.NAME_PREFIX) for v in vms))
        self.assertLessEqual(sum(v[3] for v in vms), 3 * 4096)

    def test_plan_refuses_ids_outside_the_range_and_over_budget(self):
        for base in (499, 507, 200):
            with self.assertRaises(core.GuardError):
                core.plan(base=base)
        with self.assertRaises(core.GuardError):
            core.plan(hub_mib=4096, node_mib=4096)     # four 4 GiB VMs: over the three-VM budget
        with self.assertRaises(core.GuardError):
            core.plan(hub_mib=8192)

    def test_host_floor_of_8_gib(self):
        self.assertEqual(core.available_gib(FREE.format(free=51, avail=50)), 50)
        self.assertTrue(core.may_start(FREE.format(free=13, avail=12), 4096))
        self.assertFalse(core.may_start(FREE.format(free=11, avail=11), 4096))
        self.assertFalse(core.may_start(FREE.format(free=8, avail=7), 1024))

    def test_never_touches_a_vm_that_is_not_ours(self):
        self.assertEqual(core.foreign(QM, core.plan()), [501])
        self.assertEqual(core.ours(QM), [500])

    def test_environment_is_required_and_checked(self):
        cfg = core.parse_env(ENV)
        self.assertEqual(cfg["addrs"][0], "192.0.2.10/24")
        for bad in ({}, {**ENV, "ONEMIND_FLEET_ADDRS": "192.0.2.10/24"},
                    {**ENV, "ONEMIND_FLEET_ADDRS": "192.0.2.10/24," * 3 + "192.0.2.10/24"},
                    {**ENV, "ONEMIND_FLEET_BRIDGE": ""}):
            with self.assertRaises(core.GuardError):
                core.parse_env(bad)
        self.assertEqual(core.parse_env({**ENV, "ONEMIND_FLEET_PVE": ""})["ONEMIND_FLEET_PVE"], "")

    def test_driver_refuses_to_run_without_the_lab_environment(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ONEMIND_FLEET_")}
        p = subprocess.run([sys.executable, "-I", str(FLEET / "fleet.py"), "--release", "dev-x"],
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("missing environment", p.stderr)


class Commands(unittest.TestCase):
    def test_vm_create_targets_only_the_planned_vm_and_the_env_lab(self):
        fleet = load("fleet")
        cfg = core.parse_env(ENV)
        vm = core.plan()[1]
        cmd = fleet.create_cmd(cfg, vm, "/img/onemind-vm-do-1.qcow2", 1)
        self.assertTrue(cmd.startswith("qm create 501 --name onemind-fleet-node1 "))
        for want in ("bridge=br9", "ip=192.0.2.11/24,gw=192.0.2.1", "vmstore:0,import-from=/img/onemind-vm-do-1.qcow2",
                     "user=snips:snippets/onemind-fleet-501.yaml", "--memory 2048"):
            self.assertIn(want, cmd)

    def test_negative_control_breaks_only_the_cli_on_slot_a(self):
        fleet = load("fleet")
        sh = fleet.PLANT.format(vmid=501)
        self.assertIn("qm config 501 ", sh)
        self.assertIn('name="onemind-system-a"', sh)
        self.assertIn('rm -f "$m/usr/bin/onemind"', sh)
        self.assertIn("exit 1", sh)
        for never in ("dd ", "of=", "sgdisk", "wipefs", "mkfs"):     # the disk keeps its partitions and boot code
            self.assertNotIn(never, sh)
        self.assertEqual(subprocess.run(["bash", "-n"], input=sh, text=True).returncode, 0)

    def test_user_data_gives_the_hub_its_role_and_nodes_none(self):
        fleet = load("fleet")
        hub = fleet.user_data("hub", "ssh-ed25519 AAAA test")
        node = fleet.user_data("node", "ssh-ed25519 AAAA test")
        self.assertTrue(hub.startswith("#cloud-config\n"))
        self.assertIn("onemind:\n  role: hub\n", hub)
        self.assertNotIn("onemind:", node)          # a node joins later, with `onemind fabric join`
        self.assertIn("ssh-ed25519 AAAA test", node)


class Judge(unittest.TestCase):
    def test_green_only_when_every_check_passes(self):
        all_pass = run({c: "PASS" for c in core.CHECK_IDS})
        self.assertEqual(core.verdict(all_pass), "GREEN")
        for cid in core.CHECK_IDS:
            for r in ("FAIL", "BLOCKED"):
                self.assertEqual(core.verdict({**all_pass, cid: {"result": r, "evidence": ""}}), "RED")
        self.assertEqual(core.verdict({}), "RED")

    def test_broken_node_image_must_fail_the_join_check(self):
        b = ["onemind-fleet-node1"]
        f2 = lambda result, state: {"F0": {"result": "PASS"}, "F1": {"result": "PASS"},
                                    "F2": {"result": result, "evidence": "x", "nodes": {b[0]: state, "onemind-fleet-node2": "joined"}}}
        self.assertEqual(core.verdict(f2("FAIL", "failed"), True, b), "NEGATIVE-OK")
        # a broken node that never booted proves the boot check, not the join check (the old zeroed-disk control)
        self.assertEqual(core.verdict(f2("FAIL", "not-tried"), True, b), "NEGATIVE-MISSED")
        self.assertEqual(core.verdict(run({"F0": "PASS", "F1": "FAIL", "F2": "FAIL"}), True, b), "NEGATIVE-MISSED")
        self.assertEqual(core.verdict(f2("PASS", "joined"), True, b), "NEGATIVE-MISSED")
        self.assertEqual(core.verdict(f2("FAIL", "failed"), True, []), "NEGATIVE-MISSED")   # nothing was broken
        self.assertEqual(core.verdict(run({c: "PASS" for c in core.CHECK_IDS}), True, b), "NEGATIVE-MISSED")
        self.assertEqual(core.verdict(run({"F2": "BLOCKED"}), True, b), "NEGATIVE-MISSED")

    def test_three_green_runs_in_a_row_on_the_same_image(self):
        line = lambda v, sha="a" * 64: json.dumps({"verdict": v, "image_sha256": sha})
        self.assertEqual(core.streak([line("GREEN")] * 3, "a" * 64), 3)
        self.assertEqual(core.streak([line("GREEN"), line("RED"), line("GREEN"), line("GREEN")], "a" * 64), 2)
        self.assertEqual(core.streak([line("GREEN", "b" * 64), line("GREEN")], "a" * 64), 1)
        self.assertEqual(core.streak([], "a" * 64), 0)

    def test_gate_lines_and_node_views(self):
        log = ("HEALTH-GATE: x RESULT committed-boot slot=A version=0.1.0-dev.954\n"
               "HEALTH-GATE: x RESULT mark-good slot=B version=0.1.0-dev.954-next after 80s\n"
               "HEALTH-GATE: x RESULT fell-back slot=B version=0.1.0-dev.954-next; slot A (v1) marked bad\n")
        self.assertEqual(core.gate_results(log), [("committed-boot", "A", "0.1.0-dev.954"),
                                                  ("mark-good", "B", "0.1.0-dev.954-next"),
                                                  ("fell-back", "B", "0.1.0-dev.954-next")])
        self.assertEqual(core.nodes_list([{"node_id": "n1", "status": "online"}]), {"n1": "online"})
        self.assertEqual(core.nodes_list({"nodes": [{"node_id": "n2", "status": "offline"}]}), {"n2": "offline"})
        fab = {"joining": [{"hostname": "onemind-fleet-node1", "state": "awaiting_approval", "action_id": "a1"}]}
        self.assertEqual(core.pending_join(fab, "onemind-fleet-node1")["action_id"], "a1")
        self.assertEqual(core.pending_join(fab, "other-label")["action_id"], "a1")   # the only one waiting
        two = {"pending": fab["joining"] + [{"hostname": "x", "state": "awaiting_approval", "action_id": "a2"}]}
        self.assertIsNone(core.pending_join(two, "onemind-fleet-node2"))
        self.assertIsNone(core.pending_join({"joining": [{**fab["joining"][0], "state": "approved"}]}, "onemind-fleet-node1"))
        self.assertTrue(core.offline_in_time(165))
        self.assertFalse(core.offline_in_time(166))

    def test_failover_judges_where_the_work_went(self):
        pod = lambda node, phase="Running", pin="onemind-fleet-node1": {
            "metadata": {"name": "p"}, "spec": {"nodeName": node, "nodeSelector": {core.HOSTNAME_LABEL: pin} if pin else {}},
            "status": {"phase": phase}}
        ps = lambda *items: core.pods({"items": list(items)})
        self.assertEqual(ps(pod("Onemind-Fleet-Node1"))[0], {"name": "p", "phase": "Running", "node": "onemind-fleet-node1",
                                                              "pin": "onemind-fleet-node1"})
        gone = {**pod("onemind-fleet-node1"), "metadata": {"name": "p", "deletionTimestamp": "t"}}
        self.assertEqual(core.running_on(ps(gone)), [])
        h, ok = "onemind-fleet-node1", dict(down=True, took=113, others=["online"] * 3, back=True)
        work = lambda pin, during, after: {"app": "a", "host": h, "pin": pin, "during": during, "after": after}
        # pinned (placement chose the machine): stays off other nodes while down, runs there again after the rejoin
        r, ev = core.failover(**ok, work=work(h, ps(pod(h, "Pending")), ps(pod(h))))
        self.assertEqual(r, "PASS", ev)
        self.assertEqual(core.failover(**ok, work=work(h, ps(pod("onemind-fleet-node2")), ps(pod(h))))[0], "FAIL")
        self.assertEqual(core.failover(**ok, work=work(h, ps(pod(h, "Pending")), ps(pod(h, "Pending"))))[0], "FAIL")
        # not pinned: the work must be running on another node while its node is down
        self.assertEqual(core.failover(**ok, work=work(None, ps(pod("onemind-fleet-node2", pin=None)), []))[0], "PASS")
        self.assertEqual(core.failover(**ok, work=work(None, ps(pod(h, "Pending", pin=None)), []))[0], "FAIL")
        # no app placed (F6 not PASS): offline and rejoin alone never make F7 pass
        r, ev = core.failover(**ok, work=None)
        self.assertEqual(r, "BLOCKED")
        self.assertIn("not judged", ev)
        self.assertEqual(core.failover(**{**ok, "took": 200}, work=None)[0], "FAIL")
        self.assertEqual(core.failover(**{**ok, "back": False}, work=work(h, [], ps(pod(h))))[0], "FAIL")
        self.assertEqual(core.failover(**{**ok, "others": ["online", "offline"]}, work=work(h, [], ps(pod(h))))[0], "FAIL")
        self.assertEqual(core.node_hostname({"nodes": [{"node_id": "n1", "hostname": "Box"}]}, "n1"), "box")
        self.assertIsNone(core.node_hostname([{"node_id": "n1"}], "n1"))

    def test_report_shows_every_check_and_no_lab_detail(self):
        red = core.Redactor(["lab-host.example"])
        ev = red("ssh lab-host.example 192.0.2.11 onemind-join:v2?hub=x&code=AAAA " + "f" * 64)
        self.assertNotIn("lab-host", ev)
        self.assertNotIn("192.0.2", ev)
        self.assertNotIn("onemind-join:v2?", ev)
        self.assertNotIn("f" * 64, ev)
        self.assertIn("0.1.0-dev.954", red("version=0.1.0-dev.954"))
        res = run({"F0": "PASS", "F1": "PASS"})
        md = core.report({"verdict": "RED", "image": "onemind-vm-do-1.qcow2", "image_sha256": "a" * 64,
                          "started": "t", "minutes": 1, "mode": "normal", "streak": 0, "results": res})
        for cid in core.CHECK_IDS:
            self.assertIn(f"| {cid} |", md)
        self.assertIn("| F9 |", md)
        self.assertIn("not reached", md)
        self.assertNotIn("negative control", md)
        md = core.report({"verdict": "NEGATIVE-OK", "image": "i", "image_sha256": "a" * 64, "started": "t", "minutes": 1,
                          "mode": "broken-node-image", "streak": 0, "broken": ["onemind-fleet-node1"], "results": res})
        self.assertIn("broken onemind CLI on onemind-fleet-node1", md)


if __name__ == "__main__":
    unittest.main()
