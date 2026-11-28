# SPDX-License-Identifier: Apache-2.0
"""Standing approvals fire on the handler and feature paths, never the secrets path (gateway permissions PR 2).

Each test fails without its fix: the rule approves a feature or handler request and the audit line
names the rule; a request a feature raised to destructive, a tainted requester, or a configure with
secrets still waits for a person; a rule for a type nothing files is refused when made.
"""

from __future__ import annotations

import json
import itertools
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from onemind_core.actions import ExecResult, FeatureAction, StandingGrant
from onemind_core.app import create_app
from onemind_core.auth import Principal
from onemind_core.taint import plan_taint
from onemind_core.automation import AutomationSettings

from conftest import OWNER, action_body, apply_queued_policy

AGENT_P = Principal(id="hermes", kind="agent", role="agent")
OWNER_P = Principal(id="owner", kind="person", role="owner")
_keys = itertools.count()


@pytest.fixture
def client(settings, clock, executor):
    s = replace(settings, sections={"automation": AutomationSettings(enabled=False)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


class Ran:
    def __init__(self):
        self.ids: list[str] = []

    def run(self, action, finish):
        self.ids.append(action.id)
        finish(ExecResult("succeeded", "done"))


@pytest.fixture
def ran(client):
    r = Ran()
    acts = client.app.state.actions
    acts.register_type("test.sp.write", FeatureAction(
        risk="write", run=r.run, requesters=frozenset({"person", "agent"}),
        risk_for=lambda p: "destructive" if p.get("wipe") else "write"))
    return r


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def rule(client, clock, types, who="agent:hermes"):
    body = {"allow": {"types": list(types), "requested_by": [who], "params": {}}, "limits": {"per_day": 5},
            "expires_at": iso(clock.now + timedelta(days=7))}
    return apply_queued_policy(client, client.post("/v1/approval-policies", json=body, headers=OWNER))


def file_feature(client, clock, params=None, principal=AGENT_P, type_="test.sp.write"):
    a, _ = client.app.state.actions.request_feature(
        principal, type_, params or {}, idempotency_key=f"sp-{next(_keys)}",
        expires_at=clock.now + timedelta(minutes=10))
    return a


def audit(client):
    return [json.loads(x) for x in client.app.state.settings.audit_path.read_text().splitlines()]


def test_a_rule_approves_a_feature_request_and_the_audit_names_it(client, clock, ran):
    pol = rule(client, clock, ["test.sp.write"])
    assert pol.status_code == 202, pol.text
    a = file_feature(client, clock)
    assert a["state"] == "succeeded", a
    assert a["decided_by"]["kind"] == "policy"
    approved = [e for e in audit(client) if e["event"] == "action.approved"]
    assert approved[-1]["data"]["policy_id"] == pol.json()["id"]
    assert a["plan_sha256"]  # the approval is bound to these params


def test_a_feature_whose_params_raise_it_to_destructive_waits(client, clock, ran):
    assert rule(client, clock, ["test.sp.write"]).status_code == 202
    calm = file_feature(client, clock, {"x": 1})
    assert calm["state"] == "succeeded"
    wiped = file_feature(client, clock, {"wipe": True})
    assert wiped["state"] == "awaiting_approval", "a rule approved a request its params made destructive"
    assert wiped["risk"] == "destructive"
    assert len(ran.ids) == 1


def test_a_tainted_requester_waits_on_the_feature_path(client, clock, ran):
    assert rule(client, clock, ["test.sp.write"]).status_code == 202
    client.app.state.actions.taint.mark("hermes", "rest:GET /v1/apps/{app_id}")
    a = file_feature(client, clock)
    assert a["state"] == "awaiting_approval"
    assert not ran.ids


def test_a_physical_feature_is_never_approved_by_a_rule(client, clock):
    r = Ran()
    client.app.state.actions.register_type("test.sp.pump", FeatureAction(
        risk="write", run=r.run, requesters=frozenset({"person", "agent"}), physical=True))
    assert rule(client, clock, ["test.sp.pump"]).status_code == 422


class Handler:
    def __init__(self):
        self.dispatched: list[str] = []

    def recheck(self, action):
        return None

    def dispatch(self, action):
        self.dispatched.append(action.id)
        return ExecResult("succeeded", "ok")


def test_a_rule_approves_a_handler_request_and_the_audit_names_it(client, clock):
    h = Handler()
    acts = client.app.state.actions
    acts.register_handler("node.drain", h)  # a write type in the risk table that nothing else files here
    pol = rule(client, clock, ["node.drain"])
    assert pol.status_code == 202, pol.text
    a = acts.file("node.drain", {"node_id": "n1"}, {"id": "hermes", "kind": "agent"},
                  expires_at=clock.now + timedelta(minutes=10), idempotency_key="h1")
    assert a.state == "succeeded", a
    approved = [e for e in audit(client) if e["event"] == "action.approved"][-1]
    assert approved["data"]["policy_id"] == pol.json()["id"]
    assert h.dispatched == [a.id]


def test_a_tainted_handler_request_waits_for_a_person(client, clock):
    h = Handler()
    acts = client.app.state.actions
    acts.register_handler("node.drain", h)
    assert rule(client, clock, ["node.drain"]).status_code == 202
    acts.taint.mark("hermes", "rest:GET /v1/apps/{app_id}")
    a = acts.file("node.drain", {"node_id": "n1"}, {"id": "hermes", "kind": "agent"},
                  expires_at=clock.now + timedelta(minutes=10), idempotency_key="h2")
    assert a.state == "awaiting_approval" and not h.dispatched
    assert a.plan_sha256 and plan_taint(a.plan)


def test_a_rule_never_fires_on_the_configure_with_secrets_path(client, clock):
    r = client.post("/v1/actions", json=action_body(clock, "whoami", key="sp-inst"), headers=OWNER)
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    acts = client.app.state.actions
    acts.standing_approvals.insert(0, lambda a: StandingGrant(
        Principal("policy:pol_x@1", "policy", "policy"), {"approved_via": "policy"}, lambda: None))
    a, _ = acts.request_configure(OWNER_P, {"app_id": "whoami"}, "sp-cfg", clock.now + timedelta(minutes=10))
    assert a["state"] == "awaiting_approval"


def test_a_rule_for_a_type_nothing_files_is_refused(client, clock):
    r = rule(client, clock, ["node.drain"])  # no handler is registered in this gateway
    assert r.status_code == 422, r.text
