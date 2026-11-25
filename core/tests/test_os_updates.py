# SPDX-License-Identifier: Apache-2.0
"""OS updates (UMB-P05, #142): status and history from real heartbeats, install only via approval.

Real gateway, real routes, real ledger. The heartbeats are the shape `onemindd` sends
(internal/heartbeat: `update`, `rauc`).
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app

HB = {"schema": "onemind.node.status/v1", "node_id": "box0123456789", "hostname": "beelink", "role": "hub",
      "rauc": {"present": True, "booted_slot": "A", "slots": [
          {"name": "rootfs.0", "bootname": "A", "state": "booted", "boot_status": "good", "bundle_version": "0.1.1",
           "device": "/dev/disk/by-id/ata-SERIAL123-part2"},
          {"name": "rootfs.1", "bootname": "B", "state": "inactive", "boot_status": "good", "bundle_version": "0.1.0"}]},
      "update": {"channel": "security", "current_version": "0.1.1", "available_version": "0.1.2",
                 "state": "idle", "last_check": "2026-11-18T10:00:00Z", "last_result": "update available"}}


@pytest.fixture
def box(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        def report(update=None, **changes):
            hb = {**HB, **changes, "update": {**HB["update"], **(update or {})}}
            assert app.state.registry.ingest(f"onemind.node.{hb['node_id']}.status", json.dumps(hb).encode())
        c.report, c.clock, c.n = report, clock, 0
        yield c


def ask(c, params, who=OWNER):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": "os.update.install", "params": params, "idempotency_key": f"os{c.n}",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})


def test_status_reports_version_slots_and_pending_update(box):
    box.report()
    r = box.get("/v1/os/updates", headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["install"] == {**body["install"], "available": False, "reason": "engine_unreachable"}
    [n] = body["nodes"]
    assert n["current_version"] == "0.1.1" and n["available_version"] == "0.1.2" and n["state"] == "idle"
    assert n["channel"] == "security" and n["reported"] is True and n["status"] == "online"
    assert n["rauc"]["booted_slot"] == "A" and [s["bootname"] for s in n["rauc"]["slots"]] == ["A", "B"]
    assert "SERIAL123" not in r.text  # the slot device path names the disk serial: never passed on


def test_node_without_update_service_and_hostile_fields(box):
    hb = {k: v for k, v in HB.items() if k != "update"}
    assert box.app.state.registry.ingest("onemind.node.box0123456789.status", json.dumps(hb).encode())
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["reported"] is False and n["state"] is None and n["current_version"] is None
    box.report(update={"state": "hacked", "current_version": 7, "last_result": "x" * 5000}, rauc="nope")
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["state"] == "unknown" and n["current_version"] is None and len(n["last_result"]) == 500
    assert n["rauc"] == {"present": False, "booted_slot": None, "slots": []}


def test_install_files_an_owner_approval_and_never_installs(box):
    box.report()
    r = ask(box, {"node_id": "box0123456789", "version": "0.1.2"})
    assert r.status_code == 201, r.text
    assert r.json()["state"] == "awaiting_approval"
    # An adult may ask; only an owner approves.
    assert box.post(f"/v1/actions/{r.json()['id']}/approve", headers=ADULT).status_code == 403
    done = box.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert done.status_code == 200, done.text
    a = done.json()
    assert a["state"] == "failed" and "onemind update apply" in a["result"]["message"]
    assert a["result"]["steps"][0]["result"] == "engine_unreachable"
    [req] = box.get("/v1/os/updates/history", headers=OWNER).json()["requests"]
    assert req["action_id"] == a["id"] and req["state"] == "failed" and req["version"] == "0.1.2"


def test_install_is_refused_for_an_update_nobody_offers(box):
    assert ask(box, {"node_id": "box0123456789", "version": "0.1.2"}).status_code == 409  # never reported
    box.report()
    wrong = ask(box, {"node_id": "box0123456789", "version": "9.9.9"})
    assert wrong.status_code == 409 and wrong.json()["reason"] == "no_such_update"
    ghost = ask(box, {"node_id": "ghost", "version": "0.1.2"})
    assert ghost.status_code == 409 and ghost.json()["reason"] == "unknown_node"
    assert ask(box, {"node_id": "box0123456789", "version": "0.1.2", "now": True}).status_code == 422
    assert ask(box, {"node_id": "box0123456789", "version": "0.1.2"}, who=AGENT).status_code == 403
    box.report(update={"state": "trial"})
    busy = ask(box, {"node_id": "box0123456789", "version": "0.1.2"})
    assert busy.status_code == 409 and busy.json()["reason"] == "already_installing"


def test_install_is_an_actuate_request(box):
    box.report()
    r = ask(box, {"node_id": "box0123456789", "version": "0.1.2"})
    assert r.status_code == 201, r.text
    assert box.app.state.actions.feature_types["os.update.install"].risk == "actuate"  # it reboots the box


def test_approval_rechecks_the_node(box):
    box.report()
    r = ask(box, {"node_id": "box0123456789", "version": "0.1.2"})
    box.report(update={"state": "installing"})  # the box started on its own (security channel, BD-09)
    stale = box.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert stale.status_code == 409
    assert box.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_history_records_each_commit_and_rollback_once(box):
    box.report(update={"state": "committed", "current_version": "0.1.2", "available_version": None})
    box.report(update={"state": "committed", "current_version": "0.1.2", "available_version": None})  # 10 s later
    box.report(update={"state": "idle"})
    box.report(update={"state": "rolled_back", "current_version": "0.1.2", "last_result": "gate: image-bad 0.1.3"})
    events = box.get("/v1/os/updates/history", headers=OWNER).json()["events"]
    assert [(e["state"], e["version"]) for e in events] == [("rolled_back", "0.1.2"), ("committed", "0.1.2")]
    assert events[0]["last_result"] == "gate: image-bad 0.1.3"
    # A restarted gateway does not record the same verdict again.
    box.app.state.osupdate._seen.clear()
    box.report(update={"state": "rolled_back", "current_version": "0.1.2", "last_result": "gate: image-bad 0.1.3"})
    assert len(box.get("/v1/os/updates/history", headers=OWNER).json()["events"]) == 2


def test_history_stays_bounded(box, monkeypatch):
    import onemind_core.osupdate as osupdate
    monkeypatch.setattr(osupdate, "KEEP_PER_NODE", 3)
    for i in range(6):
        box.report(update={"state": "committed" if i % 2 else "rolled_back", "current_version": f"0.1.{i}"})
    events = box.get("/v1/os/updates/history", headers=OWNER).json()["events"]
    assert [e["version"] for e in events] == ["0.1.5", "0.1.4", "0.1.3"]


def test_a_failing_listener_never_drops_a_heartbeat(box):
    def boom(_):
        raise RuntimeError("x")
    box.app.state.registry.listeners.insert(0, boom)
    box.report()
    assert box.get("/v1/os/updates", headers=OWNER).json()["nodes"][0]["state"] == "idle"


def test_reworded_last_result_does_not_repeat_a_verdict(box):
    box.report(update={"state": "committed", "current_version": "0.1.2", "last_result": "gate: good"})
    box.report(update={"state": "committed", "current_version": "0.1.2", "last_result": "gate: good (12 s)"})
    events = box.get("/v1/os/updates/history", headers=OWNER).json()["events"]
    assert [(e["state"], e["version"], e["last_result"]) for e in events] == [("committed", "0.1.2", "gate: good")]


def test_rotating_node_ids_stay_bounded(box, monkeypatch):
    """No NATS users yet (H-06): a LAN device inventing node ids grows neither the table nor the cache."""
    import onemind_core.osupdate as osupdate
    monkeypatch.setattr(osupdate, "KEEP_PER_NODE", 2)
    monkeypatch.setattr(osupdate, "MAX_NODES", 4)
    svc = box.app.state.osupdate
    for i in range(30):
        for state in ("committed", "rolled_back"):
            box.report(node_id=f"fake{i:04d}", update={"state": state, "current_version": f"0.{i}.0"})
        assert len(svc._seen) <= 4
        assert svc.repo.count() <= 2 * 4
    assert svc.repo.count() == 8 and list(svc._seen) == [f"fake{i:04d}" for i in range(26, 30)]
    newest = svc.repo.list()
    assert {e["node_id"] for e in newest} == {f"fake{i:04d}" for i in range(26, 30)}


# ---- os.rollback (P-16): back to the previous version ---------------------------------------------------------
def ask_rollback(c, params, who=OWNER):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": "os.rollback", "params": params, "idempotency_key": f"rb{c.n}",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})


def slots(other_status="good", other_version="0.1.0", booted="A"):
    first = {"name": "rootfs.0", "class": "rootfs", "bootname": "A", "state": "booted" if booted == "A" else "inactive",
             "boot_status": "good", "bundle_version": "0.1.1"}
    second = {"name": "rootfs.1", "class": "rootfs", "bootname": "B", "state": "inactive" if booted == "A" else "booted",
              "boot_status": other_status, "bundle_version": other_version}
    other = {"name": "efi.0", "class": "efi", "bootname": "", "state": "inactive"}
    if booted == "B":
        first["boot_status"], second["boot_status"], second["bundle_version"], first["bundle_version"] = \
            other_status, "good", "0.1.1", other_version
    return {"present": True, "booted_slot": booted, "slots": [first, second, other]}


def test_status_names_the_version_a_rollback_would_boot(box):
    box.report(rauc=slots())
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["rollback"] == {"available": True, "version": "0.1.0", "slot": "B", "reason": None, "message": None}
    box.report(rauc=slots(booted="B"))  # the other direction: B runs, A is the previous one
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["rollback"]["available"] is True and n["rollback"]["slot"] == "A" and n["rollback"]["version"] == "0.1.0"


def test_a_slot_the_image_wrote_takes_its_version_from_the_engines_note(box):
    """RAUC has no record for a slot the image builder wrote, so the first update's old slot has no bundle
    version: the engine's previous_version (the version it replaced, noted at the commit) names it."""
    bare = slots(other_version="")
    box.report(rauc=bare)
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["rollback"]["reason"] == "previous_unknown"
    box.report(rauc=bare, update={"previous_version": "0.1.0"})
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["rollback"] == {"available": True, "version": "0.1.0", "slot": "B", "reason": None, "message": None}
    box.report(rauc=bare, update={"previous_version": "0.1.1"})  # the same as the running version: nothing to go back to
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["rollback"]["reason"] == "same_version"


@pytest.mark.parametrize("rauc,reason", [
    (slots(other_status="bad", other_version="0.1.2"), "previous_not_good"),  # the gate rejected it
    (slots(other_status=""), "previous_not_good"),
    (slots(other_version=""), "previous_unknown"),
    (slots(other_version="0.1.1"), "same_version"),
    ({"present": True, "booted_slot": "A", "slots": slots()["slots"][:1]}, "no_previous_slot"),
    ({"present": False, "booted_slot": None, "slots": []}, "no_previous_slot"),
])
def test_rollback_is_refused_when_the_other_slot_is_not_known_good(box, rauc, reason):
    box.report(rauc=rauc)
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert n["rollback"]["available"] is False and n["rollback"]["reason"] == reason and n["rollback"]["message"]
    r = ask_rollback(box, {"node_id": "box0123456789", "version": "0.1.0"})
    assert r.status_code == 409 and r.json()["reason"] == reason


def test_rollback_request_rules(box):
    assert ask_rollback(box, {"node_id": "box0123456789", "version": "0.1.0"}).status_code == 409  # never reported
    box.report(rauc=slots())
    assert ask_rollback(box, {"node_id": "ghost", "version": "0.1.0"}).json()["reason"] == "unknown_node"
    wrong = ask_rollback(box, {"node_id": "box0123456789", "version": "9.9.9"})
    assert wrong.status_code == 409 and wrong.json()["reason"] == "no_such_version"
    assert ask_rollback(box, {"node_id": "box0123456789", "version": "0.1.0", "force": True}).status_code == 422
    assert ask_rollback(box, {"node_id": "box0123456789", "version": "0.1.0"}, who=AGENT).status_code == 403
    r = ask_rollback(box, {"node_id": "box0123456789", "version": "0.1.0"})
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval" and r.json()["risk"] == "destructive"
    box.report(update={"state": "trial"}, rauc=slots())
    busy = ask_rollback(box, {"node_id": "box0123456789", "version": "0.1.0"})
    assert busy.status_code == 409 and busy.json()["reason"] == "update_in_progress"


def test_status_reports_the_rollback_engine_and_history_lists_requests(box):
    box.report(rauc=slots())
    st = box.get("/v1/os/updates", headers=OWNER).json()
    assert st["rollback"]["available"] is False and st["rollback"]["reason"] == "engine_unreachable"
    r = ask_rollback(box, {"node_id": "box0123456789", "version": "0.1.0"})
    [req] = box.get("/v1/os/updates/history", headers=OWNER).json()["requests"]
    assert req["type"] == "os.rollback" and req["version"] == "0.1.0" and req["action_id"] == r.json()["id"]
