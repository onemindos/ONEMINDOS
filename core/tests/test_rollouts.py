# SPDX-License-Identifier: Apache-2.0
"""Fleet-staged OS updates (CORE-UPDATE-9, #156): roll out, pause on an injected failure, resume.

Real gateway, real routes, real ledger and owner-approval rule, real heartbeat registry. Five
machines report heartbeats the way `onemindd` does (contract §2, §12.10 `update`); the test plays
each machine's update service by changing what its heartbeat says. The bus is a recorder of what
the gateway publishes, standing in for NATS (test_nats_integration.py covers the real connection).
"""

from __future__ import annotations

import base64
import json
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.backups.jobs import canonical
from onemind_core.rollouts import RolloutStartParams, job_subject

OLD, NEW = "0.1.20261101000000", "0.1.20261118000000"
NODES = ["n1", "n2", "n3", "n4", "n5"]


def hb(node_id: str, version: str = OLD, state: str = "idle", last_result: str = "nothing") -> dict:
    return {"schema": "onemind.node.status/v1", "node_id": node_id, "hostname": f"box-{node_id}", "role": "node",
            "board": "x86_64-efi", "arch": "amd64",
            "update": {"channel": "stable", "current_version": version, "available_version": None,
                       "state": state, "last_check": None, "last_result": last_result}}


@pytest.fixture
def fleet(settings, clock, executor, monkeypatch):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        sent: list[tuple[str, dict]] = []
        gw_bus = app.state.rollouts.gw.bus
        gw_bus.publish_threadsafe = lambda subject, data: sent.append((subject, json.loads(data)))
        monkeypatch.setattr(type(gw_bus), "connected", property(lambda self: True))

        def report(node_id, **kw):
            assert app.state.registry.ingest(f"onemind.node.{node_id}.status", json.dumps(hb(node_id, **kw)).encode())

        for n in NODES:
            report(n)
        c.report, c.sent, c.svc, c.clock, c.n = report, sent, app.state.rollouts, clock, 0
        yield c


def ask(c, typ, params, who=OWNER):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": typ, "params": params, "idempotency_key": f"k{c.n}",
        "expires_at": (c.clock.now + timedelta(minutes=10)).isoformat()})


def approve(c, action_id):
    r = c.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    return r.json()


def offered(c, rid):
    return sorted(n["node_id"] for n in c.get(f"/v1/os/rollouts/{rid}", headers=OWNER).json()["nodes"] if n["state"] == "offered")


def test_rollout_stages_pauses_on_an_injected_failure_and_resumes(fleet):
    c = fleet
    # The fleet view: every machine on the old version.
    view = c.get("/v1/os/fleet", headers=ADULT).json()
    assert view["versions"] == [{"version": OLD, "count": 5}] and view["active_rollout_id"] is None

    # An agent asks; nothing is offered to any machine until the owner approves.
    r = ask(c, "os.rollout.start", {"version": NEW, "stages": [20, 60, 100]}, AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    assert c.get("/v1/os/rollouts", headers=OWNER).json() == [] and c.sent == []
    done = approve(c, r.json()["id"])
    rid = done["result"]["steps"][0]["rollout_id"]

    # Stage 1 (20 % of 5 = 1 machine): one signed update.apply job, naming the approved action.
    assert offered(c, rid) == ["n1"]
    subject, job = c.sent[-1]
    assert subject == job_subject("n1") == "onemind.node.n1.job.update.apply"
    assert job["kind"] == "update.apply" and job["params"]["version"] == NEW and job["action_id"] == r.json()["id"]
    key = c.svc._key.public_key()
    assert isinstance(key, Ed25519PublicKey)
    key.verify(base64.b64decode(job["sig"]), canonical({k: v for k, v in job.items() if k != "sig"}))

    c.svc.tick()
    assert offered(c, rid) == ["n1"]  # n1 has not reported yet: the next stage waits
    c.report("n1", version=NEW, state="committed", last_result="committed " + NEW)
    c.svc.tick()
    assert offered(c, rid) == ["n2", "n3"]  # stage 2: 60 % of 5 = 3 machines in all

    # Inject a failure: n3's health gate rolls the new slot back. The rollout pauses.
    c.report("n2", version=NEW, state="committed", last_result="committed " + NEW)
    c.report("n3", version=OLD, state="rolled_back", last_result="image-bad")
    c.svc.tick()
    ro = c.get(f"/v1/os/rollouts/{rid}", headers=OWNER).json()
    assert ro["state"] == "paused" and "1 machine(s) failed" in ro["reason"]
    assert ro["counts"] == {"waiting": 2, "offered": 0, "succeeded": 2, "failed": 1}
    before = len(c.sent)
    c.svc.tick()
    assert len(c.sent) == before  # paused: nothing more is offered

    # Resuming is an action too: the owner approves it, then the last stage opens.
    assert ask(c, "os.rollout.start", {"version": NEW}).status_code == 409  # one active rollout at a time
    res = ask(c, "os.rollout.resume", {"rollout_id": rid}, AGENT)
    assert res.status_code == 201 and c.get(f"/v1/os/rollouts/{rid}", headers=OWNER).json()["state"] == "paused"
    approve(c, res.json()["id"])
    assert offered(c, rid) == ["n4", "n5"]
    assert {s for s, _ in c.sent[before:]} == {job_subject("n4"), job_subject("n5")}
    for n in ("n4", "n5"):
        c.report(n, version=NEW, state="committed", last_result="committed " + NEW)
    c.svc.tick()
    ro = c.get(f"/v1/os/rollouts/{rid}", headers=OWNER).json()
    assert ro["state"] == "completed" and ro["counts"]["succeeded"] == 4 and ro["counts"]["failed"] == 1
    view = c.get("/v1/os/fleet", headers=OWNER).json()
    assert view["versions"] == [{"version": OLD, "count": 1}, {"version": NEW, "count": 4}]
    assert view["active_rollout_id"] is None


def test_a_silent_machine_times_out_and_an_earlier_error_does_not_count(fleet):
    c = fleet
    c.report("n1", state="error", last_result="check failed: offline")  # an old error, before the offer
    r = ask(c, "os.rollout.start", {"version": NEW, "stages": [20, 100], "node_timeout_s": 600, "max_failures": 1})
    rid = approve(c, r.json()["id"])["result"]["steps"][0]["rollout_id"]
    c.svc.tick()
    assert offered(c, rid) == ["n1"]  # the error it already had is not a failure of this rollout
    c.clock.advance(601)
    c.svc.tick()  # n1 never reported: failed, but one failure is allowed, so the next stage opens
    ro = c.get(f"/v1/os/rollouts/{rid}", headers=OWNER).json()
    assert ro["state"] == "running" and ro["counts"]["failed"] == 1 and ro["counts"]["offered"] == 4


def test_owner_cancels_and_nobody_else_can(fleet):
    c = fleet
    rid = approve(c, ask(c, "os.rollout.start", {"version": NEW}).json()["id"])["result"]["steps"][0]["rollout_id"]
    assert c.post(f"/v1/os/rollouts/{rid}/cancel", headers=AGENT).status_code == 403
    assert c.post(f"/v1/os/rollouts/{rid}/cancel", headers=ADULT).status_code == 403
    r = c.post(f"/v1/os/rollouts/{rid}/cancel", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert c.post(f"/v1/os/rollouts/{rid}/cancel", headers=OWNER).status_code == 409
    assert c.post("/v1/os/rollouts/rol_missing/cancel", headers=OWNER).status_code == 404


def test_machines_already_on_the_version_count_as_done(fleet):
    c = fleet
    c.report("n1", version=NEW, state="committed")
    rid = approve(c, ask(c, "os.rollout.start", {"version": NEW, "stages": [20, 100]}).json()["id"])["result"]["steps"][0]["rollout_id"]
    # n1 already fills the 20 % stage, so the 100 % stage opens straight away.
    assert offered(c, rid) == ["n2", "n3", "n4", "n5"]


@pytest.mark.parametrize("stages", [[50, 40, 100], [10, 50], [0, 100], []])
def test_stages_must_rise_to_100(stages):
    with pytest.raises(ValueError):
        RolloutStartParams(version=NEW, stages=stages)


def test_nothing_to_roll_out_to_is_refused(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        c.clock, c.n = clock, 0
        r = ask(c, "os.rollout.start", {"version": NEW})
        assert r.status_code == 409 and r.json()["reason"] == "no_updatable_nodes"


def test_a_junk_heartbeat_update_field_cannot_stall_a_rollout(fleet):
    """H-06: any LAN device can send any `update` value; the tick must not raise and the node times out."""
    c = fleet
    r = ask(c, "os.rollout.start", {"version": NEW, "stages": [20, 100], "node_timeout_s": 600, "max_failures": 1})
    rid = approve(c, r.json()["id"])["result"]["steps"][0]["rollout_id"]
    c.svc.tick()
    assert offered(c, rid) == ["n1"]
    app_reg = c.svc.gw.registry
    beat = hb("n1")
    beat["update"] = "x"
    assert app_reg.ingest("onemind.node.n1.status", json.dumps(beat).encode())
    c.svc.tick()  # must not raise
    c.clock.advance(601)
    c.svc.tick()
    ro = c.get(f"/v1/os/rollouts/{rid}", headers=OWNER).json()
    assert ro["counts"]["failed"] == 1 and ro["state"] == "running"
    # junk field types inside a valid update object are ignored too
    beat = hb("n2")
    beat["update"].update(state=["x"], last_result={"a": 1}, current_version=5)
    assert app_reg.ingest("onemind.node.n2.status", json.dumps(beat).encode())
    c.svc.tick()


def test_fleet_survives_unhashable_and_mixed_version_values(fleet):
    c = fleet
    for node, v in (("n1", ["x"]), ("n2", 7), ("n3", {"a": 1})):
        beat = hb(node)
        beat["update"]["current_version"] = v
        assert c.svc.gw.registry.ingest(f"onemind.node.{node}.status", json.dumps(beat).encode())
    r = c.get("/v1/os/fleet", headers=OWNER)
    assert r.status_code == 200
    counts = {v["version"]: v["count"] for v in r.json()["versions"]}
    assert counts == {OLD: 2, "unknown": 3}
