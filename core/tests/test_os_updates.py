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
    assert ask(box, {"node_id": "box0123456789", "version": "0.1.2", "now": True}).status_code == 422
    assert ask(box, {"node_id": "box0123456789", "version": "0.1.2"}, who=AGENT).status_code == 403
    box.report(update={"state": "trial"})
    assert ask(box, {"node_id": "box0123456789", "version": "0.1.2"}).status_code == 409


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
