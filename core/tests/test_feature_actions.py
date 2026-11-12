# SPDX-License-Identifier: Apache-2.0
"""Feature action types (actions.FeatureActionType): one ledger, owner-only approval, audited."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from onemind_core.actions import FeatureActionType
from onemind_core.auth import Principal
from onemind_core.errors import ApiError
from onemind_core.executors import ExecResult

from conftest import AGENT, OWNER

OWNER_P = Principal(id="person:owner", kind="person", role="owner")
AGENT_P = Principal(id="agent:hermes", kind="agent", role="agent")


class Demo:
    def __init__(self):
        self.problem: str | None = None
        self.claimed: set[str] = set()
        self.runs: list[str] = []
        self.released: list[str] = []
        self.outcome = "succeeded"
        self.raise_in_run = False

    def check(self, params: dict) -> str | None:
        return self.problem

    def claim(self, action) -> str | None:
        key = action.params["thing"]
        if key in self.claimed:
            return f"{key} is busy"
        self.claimed.add(key)
        return None

    def release(self, action) -> None:
        self.claimed.discard(action.params["thing"])
        self.released.append(action.id)

    def run(self, action) -> ExecResult:
        self.runs.append(action.id)
        if self.raise_in_run:
            raise RuntimeError("boom")
        return ExecResult(self.outcome, f"demo {self.outcome}")

    def type(self) -> FeatureActionType:
        return FeatureActionType(
            type="demo.thing", risk="write", check=self.check, run=self.run, claim=self.claim, release=self.release
        )


@pytest.fixture
def demo(client):
    d = Demo()
    svc = client.app.state.actions
    svc.register_type(d.type())
    svc.spawn = lambda fn: fn()  # synchronous in tests
    return d


def _file(client, clock, key="k1", thing="a", principal=OWNER_P):
    svc = client.app.state.actions
    return svc.request_feature(
        principal, "demo.thing", {"thing": thing}, idempotency_key=key,
        expires_at=clock.now + timedelta(minutes=10), audit_extra={"credentials": "provided"},
    )


def _audit(settings) -> list[dict]:
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


def test_request_approve_runs_and_audits(client, clock, demo, settings):
    action, created = _file(client, clock)
    assert created and action["state"] == "awaiting_approval" and action["type"] == "demo.thing"
    assert demo.runs == []  # nothing runs before approval
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    got = client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()
    assert got["state"] == "succeeded" and got["result"]["message"] == "demo succeeded"
    assert demo.runs == [action["id"]] and demo.released == [action["id"]] and not demo.claimed
    events = [e["event"] for e in _audit(settings) if e.get("action_id") == action["id"]]
    assert events == [
        "action.requested", "action.awaiting_approval", "action.approved", "action.dispatched", "action.succeeded"
    ]
    requested = next(e for e in _audit(settings) if e["event"] == "action.requested")
    assert requested["data"]["credentials"] == "provided" and requested["data"]["risk"] == "write"


def test_agent_can_neither_request_nor_approve(client, clock, demo, settings):
    with pytest.raises(ApiError) as e:
        _file(client, clock, principal=AGENT_P)
    assert e.value.status == 403
    action, _ = _file(client, clock)
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT)
    assert r.status_code == 403
    assert demo.runs == []


def test_stale_at_request_and_at_approval(client, clock, demo):
    demo.problem = "plan changed"
    with pytest.raises(ApiError) as e:
        _file(client, clock)
    assert e.value.status == 409 and e.value.error == "stale_precondition"
    demo.problem = None
    action, _ = _file(client, clock, key="k2")
    demo.problem = "plan changed"
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"
    assert client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_claim_blocks_a_second_action_on_the_same_thing(client, clock, demo):
    a1, _ = _file(client, clock, key="k1")
    a2, _ = _file(client, clock, key="k2")
    svc = client.app.state.actions
    started = []
    svc.spawn = lambda fn: started.append(fn)  # keep a1 running
    assert client.post(f"/v1/actions/{a1['id']}/approve", headers=OWNER).status_code == 200
    r = client.post(f"/v1/actions/{a2['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and "busy" in r.json()["message"]
    started[0]()
    assert client.post(f"/v1/actions/{a2['id']}/approve", headers=OWNER).status_code == 200


def test_failed_and_crashed_runs(client, clock, demo):
    demo.outcome = "failed"
    a, _ = _file(client, clock, key="k1")
    client.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    assert client.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "failed"
    demo.raise_in_run = True
    b, _ = _file(client, clock, key="k2", thing="b")
    client.post(f"/v1/actions/{b['id']}/approve", headers=OWNER)
    got = client.get(f"/v1/actions/{b['id']}", headers=OWNER).json()
    assert got["state"] == "outcome_unknown" and "RuntimeError" in got["result"]["message"]
    assert not demo.claimed


def test_idempotent_replay_and_conflict(client, clock, demo):
    a, created = _file(client, clock, key="same")
    b, created2 = _file(client, clock, key="same")
    assert created and not created2 and a["id"] == b["id"]
    with pytest.raises(ApiError) as e:
        _file(client, clock, key="same", thing="other")
    assert e.value.status == 409


def test_deny_works_for_feature_actions(client, clock, demo):
    a, _ = _file(client, clock)
    r = client.post(f"/v1/actions/{a['id']}/deny", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert demo.runs == [] and demo.released == [a["id"]]  # the module drops what it held for it


def test_expiry_releases_feature_actions(client, clock, demo):
    a, _ = _file(client, clock)
    clock.advance(11 * 60)
    assert client.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "expired"
    assert demo.released == [a["id"]]
    client.get(f"/v1/actions/{a['id']}", headers=OWNER)
    assert demo.released == [a["id"]]  # once, when it expires


def test_restart_marks_dispatched_feature_action_unknown(settings, clock, demo, client):
    from onemind_core.app import create_app
    from fastapi.testclient import TestClient

    a, _ = _file(client, clock)
    svc = client.app.state.actions
    svc.spawn = lambda fn: None  # the worker never finishes: the gateway "dies" mid-run
    client.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    assert client.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "dispatched"
    # A new gateway on the same ledger, before any feature registered: no KeyError on params.
    with TestClient(create_app(settings, clock=clock)) as c2:
        assert c2.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "outcome_unknown"


def test_register_twice_or_unknown_risk_refused(client, demo):
    svc = client.app.state.actions
    with pytest.raises(ValueError):
        svc.register_type(demo.type())
    with pytest.raises(ValueError):
        svc.register_type(FeatureActionType(type="app.install", risk="write", check=demo.check, run=demo.run))
    with pytest.raises(ValueError):
        svc.register_type(FeatureActionType(type="demo.other", risk="huge", check=demo.check, run=demo.run))
