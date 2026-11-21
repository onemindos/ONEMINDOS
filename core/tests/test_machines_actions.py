# SPDX-License-Identifier: Apache-2.0
"""Machine actions (MACH-01, #281 part 3): create, start, stop, delete go through owner approval.

Real gateway, real routes, real ledger and approval rule. The runtime is the noop one the gateway
picks with the noop executor, and the kubectl runtime is exercised with a scripted runner.
"""

from __future__ import annotations

import json
import subprocess
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.executors import ExecResult
from onemind_core.identity.scopes import required_scopes
from onemind_core.machines.runtime import KubectlRuntime
from onemind_core.machines.spec import (
    NAMESPACE, RESERVE_MB, MachineCreateParams, quota_problem, render_create,
)

PC = {"schema": "onemind.node.status/v1", "node_id": "pc0123456789", "hostname": "beelink", "role": "hub",
      "board": "x86_64-efi", "arch": "amd64", "mem_total_mb": 15_800, "cpus": 8, "kvm": True,
      "k3s": {"present": True, "role": "server", "ready": True}}
VM = {"name": "win", "ram_mb": 4096, "cpus": 2, "disk_gb": 40, "image_url": "https://images.example.org/debian.qcow2"}


@pytest.fixture
def box(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        def report(**changes):
            hb = {**PC, **changes}
            assert app.state.registry.ingest(f"onemind.node.{hb['node_id']}.status", json.dumps(hb).encode())
        c.report, c.clock, c.n = report, clock, 0
        c.ask = lambda typ, params, who=OWNER: _ask(c, typ, params, who)
        yield c


def _ask(c, typ, params, who):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": typ, "params": params, "idempotency_key": f"k{c.n}", "expires_at": (c.clock.now + timedelta(minutes=10)).isoformat()})


def done(c, typ, params, who=OWNER):
    r = c.ask(typ, params, who)
    assert r.status_code == 201, r.text
    a = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert a.status_code == 200, a.text
    assert a.json()["state"] == "succeeded", a.text
    return a.json()


def test_owner_creates_starts_opens_console_stops_and_deletes(box):
    box.report()
    queued = box.ask("machine.create", VM)
    assert queued.status_code == 201 and queued.json()["state"] == "awaiting_approval"
    assert box.get("/v1/machines", headers=OWNER).json() == []  # nothing exists before approval
    box.post(f"/v1/actions/{queued.json()['id']}/approve", headers=OWNER)
    m = box.get("/v1/machines/win", headers=OWNER).json()
    assert m["state"] == "stopped" and m["ram_mb"] == 4096 and m["node_id"] == "pc0123456789"
    assert box.post("/v1/machines/win/console", headers=OWNER).status_code == 409  # not running yet
    done(box, "machine.start", {"name": "win"})
    assert box.get("/v1/machines/win", headers=OWNER).json()["state"] == "running"
    t = box.post("/v1/machines/win/console", headers=OWNER)
    assert t.status_code == 200 and t.json()["ticket"] and t.json()["machine"] == "win"
    svc = box.app.state.machines
    assert svc.redeem_ticket(t.json()["ticket"], "win") is True
    assert svc.redeem_ticket(t.json()["ticket"], "win") is False  # single use
    done(box, "machine.stop", {"name": "win"})
    assert box.get("/v1/machines/win", headers=OWNER).json()["state"] == "stopped"
    done(box, "machine.delete", {"name": "win", "confirm": "win"})
    assert box.get("/v1/machines", headers=OWNER).json() == []


def test_an_agent_can_request_but_never_approve_or_open_a_console(box):
    box.report()
    r = box.ask("machine.create", VM, AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert r.json()["requested_by"]["kind"] == "agent"
    aid = r.json()["id"]
    assert box.post(f"/v1/actions/{aid}/approve", headers=AGENT).status_code == 403
    assert box.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert box.get("/v1/machines", headers=OWNER).json() == []
    box.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    done(box, "machine.start", {"name": "win"})
    for who in (AGENT, ADULT, GUEST):
        assert box.post("/v1/machines/win/console", headers=who).status_code == 403


@pytest.mark.parametrize("changes", [
    {"board": "rpi5", "arch": "arm64", "mem_total_mb": 7_800, "kvm": False}, {"mem_total_mb": 7_800}, {"kvm": False}])
def test_a_pi_or_small_box_refuses_a_create_with_a_reason(box, changes):
    box.report(**changes)
    r = box.ask("machine.create", VM)
    assert r.status_code == 409 and r.json()["reason"] == "machines_unsupported", r.text
    assert "cannot run virtual machines" in r.json()["message"]


def test_no_node_reporting_refuses_a_create(box):
    assert box.ask("machine.create", VM).status_code == 409


def test_the_box_keeps_a_reserve_and_a_quota_is_checked_at_request_and_approval(box):
    box.report()  # 15,800 MB, 8 cpus: machines may use 15,800 - RESERVE_MB
    big = {**VM, "name": "big", "ram_mb": 15_800 - RESERVE_MB + 1}
    r = box.ask("machine.create", big)
    assert r.status_code == 409 and r.json()["reason"] == "quota_exceeded"
    # two requests that each fit alone, filed before either is approved: the second is refused at approval
    a = box.ask("machine.create", {**VM, "name": "one", "ram_mb": 8_000}).json()
    b = box.ask("machine.create", {**VM, "name": "two", "ram_mb": 8_000}).json()
    assert box.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    r = box.post(f"/v1/actions/{b['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"
    assert box.get(f"/v1/actions/{b['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert [m["name"] for m in box.get("/v1/machines", headers=OWNER).json()] == ["one"]


def test_cpu_quota_keeps_a_core_for_the_system():
    node = {"mem_total_mb": 64_000, "cpus": 4}
    assert quota_problem(node, [], 1024, 3) is None
    assert "cores" in quota_problem(node, [], 1024, 4)


def test_state_rules_and_the_delete_confirmation(box):
    box.report()
    assert box.ask("machine.start", {"name": "ghost"}).status_code == 409
    done(box, "machine.create", VM)
    assert box.ask("machine.create", VM).status_code == 409  # name taken
    assert box.ask("machine.stop", {"name": "win"}).status_code == 409  # not running
    assert box.ask("machine.delete", {"name": "win", "confirm": "nope"}).status_code == 422
    assert box.ask("machine.delete", {"name": "win"}).status_code == 422


def test_params_are_strict(box):
    box.report()
    for bad in ({**VM, "name": "Bad Name"}, {**VM, "image_url": "http://plain.example.org/x"}, {**VM, "ram_mb": 8}, {**VM, "extra": 1}):
        assert box.ask("machine.create", bad).status_code == 422


def test_a_failed_create_gives_its_quota_back(settings, clock):
    class Broken:
        def create(self, p):
            return ExecResult("failed", "kubectl exited 1", [])
    app = create_app(settings, clock=clock)
    with TestClient(app) as c:
        app.state.machines.runtime = Broken()
        app.state.registry.ingest("onemind.node.pc0123456789.status", json.dumps(PC).encode())
        c.clock, c.n = clock, 0
        r = _ask(c, "machine.create", VM, OWNER)
        out = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()
        assert out["state"] == "failed"
        assert c.get("/v1/machines", headers=OWNER).json() == []


def test_an_unknown_create_keeps_its_quota_and_name(settings, clock):
    class TimedOut:
        def create(self, p):
            return ExecResult("outcome_unknown", "kubectl timed out", [])
    app = create_app(settings, clock=clock)
    with TestClient(app) as c:
        app.state.machines.runtime = TimedOut()
        app.state.registry.ingest("onemind.node.pc0123456789.status", json.dumps(PC).encode())
        c.clock, c.n = clock, 0
        r = _ask(c, "machine.create", VM, OWNER)
        out = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()
        assert out["state"] == "outcome_unknown"
        held = c.get("/v1/machines", headers=OWNER).json()
        assert [(m["name"], m["state"]) for m in held] == [("win", "unknown")]  # still booked
        assert _ask(c, "machine.create", VM, OWNER).status_code == 409  # the name is held until an owner reconciles


@pytest.mark.parametrize("how", ["deny", "expire"])
@pytest.mark.parametrize("outcome", ["succeeded", "outcome_unknown"])
def test_a_duplicate_create_that_ends_does_not_release_the_in_flight_create(settings, clock, how, outcome):
    """Two creates for one name are filed. A is approved and running; B is denied or expires meanwhile."""
    app = create_app(settings, clock=clock)
    with TestClient(app) as c:
        c.clock, c.n = clock, 0
        app.state.registry.ingest("onemind.node.pc0123456789.status", json.dumps(PC).encode())
        a = _ask(c, "machine.create", VM, OWNER).json()["id"]
        b = _ask(c, "machine.create", VM, OWNER).json()["id"]
        seen = {}

        class Slow:
            def create(self, p):
                if how == "deny":
                    assert c.post(f"/v1/actions/{b}/deny", headers=OWNER).status_code == 200
                else:
                    clock.advance(11 * 60)
                    assert c.get(f"/v1/actions/{b}", headers=OWNER).json()["state"] == "expired"
                seen["row"] = app.state.machines.repo.get("win")
                return ExecResult(outcome, "x", [])
        app.state.machines.runtime = Slow()
        out = c.post(f"/v1/actions/{a}/approve", headers=OWNER).json()
        assert out["state"] == outcome
        assert seen["row"] is not None and seen["row"]["state"] == "creating"  # B's end did not touch A's row
        held = c.get("/v1/machines", headers=OWNER).json()
        assert [(m["name"], m["state"]) for m in held] == [("win", "stopped" if outcome == "succeeded" else "unknown")]


@pytest.mark.parametrize("name", ["capabilities", "enable"])
def test_machine_names_cannot_shadow_a_route(box, name):
    box.report()
    assert box.ask("machine.create", {**VM, "name": name}).status_code == 422


def test_the_routes_have_scope_rows():
    assert required_scopes("GET", "/v1/machines") == ("nodes:read",)
    assert required_scopes("GET", "/v1/machines/win") == ("nodes:read",)
    assert required_scopes("GET", "/v1/machines/capabilities") == ("nodes:read",)
    assert required_scopes("POST", "/v1/machines/win/console") == ("machines:admin",)


# ---- what the objects say, and what kubectl is asked to do ---------------------------------------------

def test_the_objects_cap_the_machine_and_deny_its_network():
    items = json.loads(render_create(MachineCreateParams.model_validate(VM)))["items"]
    kinds = {i["kind"]: i for i in items}
    pol = kinds["NetworkPolicy"]["spec"]
    assert pol["policyTypes"] == ["Ingress", "Egress"] and "ingress" not in pol and "egress" not in pol  # deny all
    dom = kinds["VirtualMachine"]["spec"]["template"]["spec"]["domain"]
    assert dom["resources"]["limits"] == dom["resources"]["requests"] == {"memory": "4096Mi", "cpu": "2"}
    assert kinds["VirtualMachine"]["spec"]["runStrategy"] == "Halted"
    assert all(i["metadata"].get("namespace", NAMESPACE) == NAMESPACE for i in items if i["kind"] != "Namespace")


def test_kubectl_runtime_applies_patches_and_deletes_and_maps_outcomes():
    calls = []

    def runner(argv, **kw):
        calls.append((argv, kw.get("input")))
        return subprocess.CompletedProcess(argv, 0, "", "")
    rt = KubectlRuntime("kubectl", runner)
    assert rt.create(MachineCreateParams.model_validate(VM)).outcome == "succeeded"
    assert calls[0][0][:3] == ["kubectl", "apply", "--server-side"] and '"VirtualMachine"' in calls[0][1]
    assert rt.set_running("win", True).outcome == "succeeded"
    assert "Always" in calls[1][0][-1] and calls[1][0][1] == "patch"
    assert rt.delete("win").outcome == "succeeded" and [c[0][1] for c in calls[2:]] == ["delete"] * 3

    def failing(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, "", "boom")

    def hangs(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)

    def missing(argv, **kw):
        raise FileNotFoundError
    assert KubectlRuntime(runner=failing).set_running("win", False).outcome == "failed"
    assert KubectlRuntime(runner=hangs).set_running("win", False).outcome == "outcome_unknown"
    assert KubectlRuntime(runner=missing).delete("win").outcome == "failed"


# ---- restart, force off, snapshot and clone (the lifecycle slice) --------------------------------------------

def _waiting(c, typ, params, who=OWNER):
    """Filed, and proven to wait: nothing changes until an owner approves."""
    r = c.ask(typ, params, who)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval", r.text
    return r.json()["id"]


def _up(box, name="win"):
    box.report()
    done(box, "machine.create", {**VM, "name": name})
    done(box, "machine.start", {"name": name})


@pytest.mark.parametrize("typ,params,after", [
    ("machine.restart", {"name": "win"}, "running"),
    ("machine.force_stop", {"name": "win"}, "stopped"),
])
def test_restart_and_force_off_wait_for_approval(box, typ, params, after):
    _up(box)
    aid = _waiting(box, typ, params, AGENT)  # an agent may ask
    assert box.post(f"/v1/actions/{aid}/approve", headers=AGENT).status_code == 403
    assert box.get("/v1/machines/win", headers=OWNER).json()["state"] == "running"  # untouched while waiting
    assert box.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()["state"] == "succeeded"
    assert box.get("/v1/machines/win", headers=OWNER).json()["state"] == after


def test_restart_needs_a_running_machine_and_force_off_a_known_one(box):
    box.report()
    done(box, "machine.create", VM)
    assert box.ask("machine.restart", {"name": "win"}).status_code == 409  # stopped
    assert box.ask("machine.force_stop", {"name": "ghost"}).status_code == 409
    assert box.ask("machine.force_stop", {"name": "win"}).status_code == 201  # a hung shutdown still reads `stopped`


def test_snapshot_waits_for_approval_lists_with_its_consistency_and_is_capped(box):
    _up(box)
    aid = _waiting(box, "machine.snapshot", {"name": "win", "snapshot": "before-update"}, AGENT)
    assert box.get("/v1/machines/win/snapshots", headers=OWNER).json() == []  # nothing before approval
    out = box.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()
    assert out["state"] == "succeeded"
    snaps = box.get("/v1/machines/win/snapshots", headers=OWNER).json()
    assert [(x["name"], x["consistency"]) for x in snaps] == [("before-update", "quiesced")]
    assert box.ask("machine.snapshot", {"name": "win", "snapshot": "before-update"}).status_code == 409  # taken
    assert box.get("/v1/machines/ghost/snapshots", headers=OWNER).status_code == 404
    for i in range(4):
        done(box, "machine.snapshot", {"name": "win", "snapshot": f"s{i}"})
    r = box.ask("machine.snapshot", {"name": "win", "snapshot": "one-too-many"})
    assert r.status_code == 409 and r.json()["reason"] == "too_many_snapshots"


@pytest.mark.parametrize("indications,state,expected", [
    (["GuestAgent"], "running", "quiesced"),
    (["Online", "QuiesceFailed"], "running", "quiesce_failed"),
    (["NoGuestAgent"], "running", "best_effort"),
    ([], "stopped", "offline"),
])
def test_quiesce_failure_is_shown_to_the_owner_as_best_effort(box, indications, state, expected):
    _up(box)
    if state == "stopped":
        done(box, "machine.stop", {"name": "win"})
    box.app.state.machines.runtime.snapshot = lambda n, s: (ExecResult("succeeded", "taken", []), indications)
    out = done(box, "machine.snapshot", {"name": "win", "snapshot": "s1"})
    snap = box.get("/v1/machines/win/snapshots", headers=OWNER).json()[0]
    assert snap["consistency"] == expected and snap["note"]
    if expected == "quiesce_failed":
        assert "QuiesceFailed" in out["result"]["message"] and "best effort" in snap["note"]


def test_a_failed_snapshot_leaves_no_record(box):
    _up(box)
    box.app.state.machines.runtime.snapshot = lambda n, s: (ExecResult("failed", "kubectl exited 1", []), [])
    aid = _waiting(box, "machine.snapshot", {"name": "win", "snapshot": "s1"})
    assert box.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()["state"] == "failed"
    assert box.get("/v1/machines/win/snapshots", headers=OWNER).json() == []


def test_clone_waits_for_approval_counts_against_the_quota_and_starts_stopped(box):
    box.report()  # machines may use 15,800 - RESERVE_MB = 11,704 MB
    done(box, "machine.create", {**VM, "name": "base", "ram_mb": 5_000})
    running = _waiting(box, "machine.start", {"name": "base"})
    box.post(f"/v1/actions/{running}/approve", headers=OWNER)
    r = box.ask("machine.clone", {"source": "base", "name": "copy"})
    assert r.status_code == 409 and r.json()["reason"] == "wrong_state"  # stop the source first
    done(box, "machine.stop", {"name": "base"})
    aid = _waiting(box, "machine.clone", {"source": "base", "name": "copy"}, AGENT)
    assert box.get("/v1/machines/copy", headers=OWNER).status_code == 404  # nothing before approval
    assert box.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()["state"] == "succeeded"
    c = box.get("/v1/machines/copy", headers=OWNER).json()
    assert (c["state"], c["ram_mb"], c["cpus"], c["disk_gb"]) == ("stopped", 5_000, 2, 40)
    # base 5,000 + copy 5,000 + another 5,000 > 11,704: a second copy does not fit, at request time
    r = box.ask("machine.clone", {"source": "base", "name": "copy2"})
    assert r.status_code == 409 and r.json()["reason"] == "quota_exceeded"


def test_clone_is_refused_at_approval_when_the_quota_filled_up_meanwhile(box):
    box.report()
    done(box, "machine.create", {**VM, "name": "base", "ram_mb": 5_000})
    a = _waiting(box, "machine.clone", {"source": "base", "name": "copy"})
    done(box, "machine.create", {**VM, "name": "big", "ram_mb": 5_000})  # now only ~1.7 GB is left
    r = box.post(f"/v1/actions/{a}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"
    assert box.get(f"/v1/actions/{a}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert box.get("/v1/machines/copy", headers=OWNER).status_code == 404


def test_clone_input_rules(box):
    box.report()
    done(box, "machine.create", VM)
    assert box.ask("machine.clone", {"source": "ghost", "name": "copy"}).status_code == 409
    assert box.ask("machine.clone", {"source": "win", "name": "win"}).status_code == 422
    assert box.ask("machine.clone", {"source": "win", "name": "capabilities"}).status_code == 422
    assert box.ask("machine.clone", {"source": "win", "name": "copy", "ram_mb": 1}).status_code == 422  # strict


def test_a_failed_clone_gives_its_quota_and_name_back(box):
    box.report()
    done(box, "machine.create", VM)
    box.app.state.machines.runtime.clone = lambda s, t: ExecResult("failed", "kubectl exited 1", [])
    aid = _waiting(box, "machine.clone", {"source": "win", "name": "copy"})
    assert box.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()["state"] == "failed"
    assert [m["name"] for m in box.get("/v1/machines", headers=OWNER).json()] == ["win"]


def test_deleting_a_machine_with_snapshots_asks_for_the_typed_name_and_takes_them_along(box):
    _up(box)
    done(box, "machine.snapshot", {"name": "win", "snapshot": "s1"})
    done(box, "machine.snapshot", {"name": "win", "snapshot": "s2"})
    for params in ({"name": "win"}, {"name": "win", "confirm": "nope"}):
        assert box.ask("machine.delete", params).status_code == 422
    svc = box.app.state.machines
    assert "2 snapshots" in svc.problem("delete", {"name": "win"})[1]
    done(box, "machine.stop", {"name": "win"})
    done(box, "machine.delete", {"name": "win", "confirm": "win"})
    assert svc.repo.snapshots("win") == []


def test_the_snapshots_route_has_a_scope_row():
    assert required_scopes("GET", "/v1/machines/win/snapshots") == ("nodes:read",)


def test_kubectl_runtime_lifecycle_commands_and_the_freeze_result():
    calls = []

    def runner(argv, **kw):
        calls.append((argv, kw.get("input")))
        out = '["Online","QuiesceFailed"]' if argv[1] == "get" else ""
        return subprocess.CompletedProcess(argv, 0, out, "")
    rt = KubectlRuntime("kubectl", runner)
    assert rt.restart("win").outcome == "succeeded" and calls[-1][0][1:4] == ["delete", "virtualmachineinstance", "win"]
    calls.clear()
    assert rt.force_stop("win").outcome == "succeeded"
    assert "Halted" in calls[0][0][-1] and "--grace-period=0" in calls[1][0]  # Halted first, or it would come back
    calls.clear()
    res, ind = rt.snapshot("win", "s1")
    assert res.outcome == "succeeded" and ind == ["Online", "QuiesceFailed"]
    assert '"VirtualMachineSnapshot"' in calls[0][1] and calls[1][0][1] == "wait"
    calls.clear()
    assert rt.clone("win", "copy").outcome == "succeeded"
    assert '"VirtualMachineClone"' in calls[0][1] and '"NetworkPolicy"' in calls[0][1]
    assert "Halted" in calls[2][0][-1] and "onemind.io/machine" in calls[2][0][-1]
    calls.clear()
    assert rt.delete("win").outcome == "succeeded" and "virtualmachinesnapshot" in calls[0][0]
    assert KubectlRuntime(runner=lambda a, **k: subprocess.CompletedProcess(a, 1, "", "boom")).snapshot("w", "s")[0].outcome == "failed"
