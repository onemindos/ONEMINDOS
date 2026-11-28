# SPDX-License-Identifier: Apache-2.0
"""#723: the physical flag on action types, the hold flag on the approval card, the motion lockout."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from onemind_core.actions import HOLD_MIN_MS, ApprovalInput, FeatureAction, approval_card, hold_required
from onemind_core.auth import Principal
from onemind_core.automation import registry
from onemind_core.errors import ApiError
from onemind_core.executors import ExecResult

from conftest import AGENT, OWNER
from test_identity import LOCAL_PEER, setup_bearer_owner

OWNER_P = Principal(id="person:owner", kind="person", role="owner")
AGENT_P = Principal(id="agent:hermes", kind="agent", role="agent")
AUTOMATION_P = Principal(id="automation:rule1", kind="automation", role="automation")
POLICY_P = Principal(id="policy:pol1@1", kind="policy", role="policy")
PASSKEY_HOLD = ApprovalInput(webauthn=True, hold_ms=HOLD_MIN_MS)


class Pump:
    def __init__(self):
        self.runs: list[dict] = []
        self.max_s = 300

    def limits(self, params: dict) -> list[dict]:
        return [{"name": "duration", "value": params["seconds"], "unit": "s"},
                {"name": "max_duration", "value": self.max_s, "unit": "s"}]

    def run(self, action, finish) -> None:
        self.runs.append(action.params)
        finish(ExecResult("succeeded", "pump ran"))


@pytest.fixture
def pump(client):
    p = Pump()
    # risk "write" on purpose: physical is independent of the risk class
    client.app.state.actions.register_type("test.pump.run", FeatureAction(
        risk="write", run=p.run, requesters=frozenset({"person", "agent"}), physical=True,
        limits_for=p.limits, preview_for=lambda params: {"kind": "text", "text": f"pump for {params['seconds']} s"},
    ))
    return p


def _file(client, clock, principal=AGENT_P, key="k1", seconds=30):
    return client.app.state.actions.request_feature(
        principal, "test.pump.run", {"seconds": seconds}, idempotency_key=key,
        expires_at=clock.now + timedelta(minutes=10))


def _approve(client, action, principal=OWNER_P, plan=None, extra=PASSKEY_HOLD):
    return client.app.state.actions.approve(principal, action["id"], plan or action["plan_sha256"], extra=extra)


def _audit(settings) -> list[dict]:
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


def _refused(fn) -> ApiError:
    with pytest.raises(ApiError) as e:
        fn()
    return e.value


def test_card_carries_physical_hold_limits_preview_and_plan(client, clock, pump, settings):
    action, created = _file(client, clock)
    assert created and action["state"] == "awaiting_approval"  # an agent may file
    card = action["approval"]
    assert card == {"physical": True, "hold": True, "hold_ms": HOLD_MIN_MS,
                    "limits": [{"name": "duration", "value": 30, "unit": "s"},
                               {"name": "max_duration", "value": 300, "unit": "s"}],
                    "preview": {"kind": "text", "ref": None, "text": "pump for 30 s"}}
    assert action["plan_sha256"].startswith("sha256:") and action["plan"]["approval"] == card
    assert action["risk"] == "write"
    got = client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()
    assert got["approval"] == card and got["plan_sha256"] == action["plan_sha256"]
    requested = next(e for e in _audit(settings) if e["event"] == "action.requested"
                     and e["action_id"] == action["id"])
    assert requested["data"]["physical"] is True and requested["data"]["plan_sha256"] == action["plan_sha256"]


def test_full_approval_runs_once_and_is_audited(client, clock, pump, settings):
    action, _ = _file(client, clock)
    out = _approve(client, action)
    assert out["state"] == "succeeded" and pump.runs == [{"seconds": 30}]
    approved = next(e for e in _audit(settings) if e["event"] == "action.approved" and e["action_id"] == action["id"])
    assert approved["data"]["physical"] is True and approved["data"]["hold_ms"] == HOLD_MIN_MS
    assert approved["data"]["approval"] == "passkey" and approved["data"]["requested_by"] == "agent:hermes"


@pytest.mark.parametrize("extra, status, reason", [
    (ApprovalInput(webauthn=True), 409, "hold_required"),
    (ApprovalInput(webauthn=True, hold_ms=HOLD_MIN_MS - 1), 409, "hold_required"),
    (ApprovalInput(hold_ms=HOLD_MIN_MS), 401, "step_up_required"),
])
def test_approval_without_passkey_or_hold_is_refused(client, clock, pump, extra, status, reason):
    action, _ = _file(client, clock)
    e = _refused(lambda: _approve(client, action, extra=extra))
    assert (e.status, e.reason) == (status, reason)
    assert client.app.state.actions.get(action["id"])["state"] == "awaiting_approval" and pump.runs == []


def test_approval_is_bound_to_plan_sha256(client, clock, pump):
    a, _ = _file(client, clock, key="k1", seconds=30)
    b, _ = _file(client, clock, key="k2", seconds=600)
    svc = client.app.state.actions
    e = _refused(lambda: svc.approve(OWNER_P, a["id"], None, extra=PASSKEY_HOLD))
    assert (e.status, e.reason) == (409, "plan_unchecked")
    # the fingerprint of other parameters (600 s, not 30 s) does not approve this request
    e = _refused(lambda: _approve(client, a, plan=b["plan_sha256"]))
    assert (e.status, e.reason) == (409, "plan_changed")
    # a changed limit changes the plan: the old approval card no longer describes what would run
    pump.max_s = 60
    e = _refused(lambda: _approve(client, a))
    assert (e.status, e.reason) == (409, "plan_changed")
    assert pump.runs == [] and svc.get(a["id"])["state"] == "awaiting_approval"


def test_agents_standing_approvals_and_automations_never_approve(client, clock, pump, settings):
    action, _ = _file(client, clock)
    svc = client.app.state.actions
    assert _refused(lambda: _approve(client, action, principal=AGENT_P)).status == 403
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
    # a standing approval (contract §12.17) is refused whatever its risk ceiling says
    e = _refused(lambda: svc._approve(POLICY_P, action["id"], action["plan_sha256"], standing={"approved_via": "policy"},
                                      extra=PASSKEY_HOLD))
    assert e.status == 403 and pump.runs == []
    assert registry.policy_may_cover("test.pump.run") and registry.automatable("test.pump.run")
    # an automation cannot even file one
    assert _refused(lambda: _file(client, clock, principal=AUTOMATION_P, key="k9")).status == 403
    with pytest.raises(ValueError):
        svc.register_type("test.pump.auto", FeatureAction(risk="write", run=pump.run, physical=True,
                                                          requesters=frozenset({"person", "automation"})))
    assert svc.get(action["id"])["state"] == "awaiting_approval"


def test_policy_store_refuses_a_physical_type(client, clock, pump):
    r = client.post("/v1/approval-policies", headers=OWNER, json={
        "name": "pump", "allow": {"types": ["test.pump.run"], "requested_by": ["agent:hermes"]},
        "limits": {"per_day": 5}, "expires_at": (clock.now + timedelta(days=1)).isoformat()})
    assert r.status_code == 422, r.text
    assert "physical" in r.json()["message"]


def test_http_approve_needs_passkey_then_passes_hold_through(client, clock, pump):
    action, _ = _file(client, clock)
    body = {"plan_sha256": action["plan_sha256"], "hold_ms": HOLD_MIN_MS}
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER, json=body)
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    # with a verified assertion (the identity guard stands in here), hold_ms reaches the service
    gw = client.app.state.gateway

    def approval_guard(p, action_id, body, request):
        return None

    gw.approval_guards[:] = [approval_guard] + [g for g in gw.approval_guards if g.__name__ != "approval_guard"]
    assertion = {"id": "stand-in", "type": "public-key"}  # what the identity guard verified
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER, json={**body, "hold_ms": 500, "webauthn": assertion})
    assert r.status_code == 409 and r.json()["reason"] == "hold_required", (r.text, [g.__name__ for g in gw.approval_guards])
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER, json={**body, "webauthn": assertion})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text


def test_motion_lockout_refuses_every_physical_request(client, clock, pump, settings):
    pending, _ = _file(client, clock, key="k1")
    assert client.get("/v1/physical/lockout", headers=OWNER).json()["locked"] is False
    r = client.put("/v1/physical/lockout", headers=OWNER, json={"locked": True, "reason": "working on the pump"})
    assert r.status_code == 200 and r.json()["locked"] is True and r.json()["changed_by"]["id"]
    e = _refused(lambda: _file(client, clock, key="k2"))
    assert (e.status, e.reason) == (409, "motion_lockout")
    e = _refused(lambda: _approve(client, pending))
    assert (e.status, e.reason) == (409, "motion_lockout")
    assert pump.runs == []
    # agents can neither read nor lift it
    assert client.get("/v1/physical/lockout", headers=AGENT).status_code == 403
    assert client.put("/v1/physical/lockout", headers=AGENT, json={"locked": False}).status_code == 403
    assert client.get("/v1/physical/lockout", headers=OWNER).json()["locked"] is True
    events = [e["event"] for e in _audit(settings)]
    assert "physical.lockout.on" in events
    assert client.put("/v1/physical/lockout", headers=OWNER, json={"locked": False}).json()["locked"] is False
    assert _approve(client, pending)["state"] == "succeeded"


def test_lifting_the_lockout_requires_l2_after_the_box_has_an_owner(client, settings):
    home = TestClient(client.app, client=LOCAL_PEER)
    signed_in = setup_bearer_owner(home)
    # turning motion off stays one step: no passkey needed to make the box safer
    r = home.put("/v1/physical/lockout", headers=signed_in, json={"locked": True})
    assert r.status_code == 200 and r.json()["locked"] is True, r.text
    # lifting it with a bare token is refused, and the lockout holds
    for headers in (signed_in, OWNER):
        r = home.put("/v1/physical/lockout", headers=headers, json={"locked": False})
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    assert client.get("/v1/physical/lockout", headers=OWNER).json()["locked"] is True
    assert "physical.lockout.off" not in [e["event"] for e in _audit(settings)]


def test_lockout_that_cannot_be_read_counts_as_on(client, clock, pump):
    svc = client.app.state.actions

    def broken():
        raise RuntimeError("database gone")

    svc.motion_lockout = broken
    e = _refused(lambda: _file(client, clock))
    assert e.reason == "motion_lockout"


def test_existing_actuate_types_are_not_physical(client):
    svc = client.app.state.actions
    for t in ("node.wake", "os.update.install"):
        assert not svc.is_physical(t)
        assert t not in registry.PHYSICAL
    assert svc.feature_types["node.wake"].risk == "actuate" and "agent" in svc.feature_types["node.wake"].requesters


def test_card_rules():
    assert hold_required("destructive", False) and hold_required("write", True) and not hold_required("actuate", False)
    assert approval_card("destructive", False)["hold"] is True
    assert approval_card("actuate", False) == {"physical": False, "hold": False, "hold_ms": None, "limits": [],
                                               "preview": None}
    for bad in ([{"name": "x"}], [{"name": "x", "value": {"a": 1}}], [{"name": "", "value": 1}],
                [{"name": "x", "value": 1, "secret": "y"}], [{"name": "x", "value": 1, "unit": 5}]):
        with pytest.raises(ValueError):
            approval_card("write", True, bad)
    with pytest.raises(ValueError):
        approval_card("write", True, None, {"kind": "image", "script": "x"})


# Review blocker on #723: the card is on every action, not only physical ones, so "card present"
# never means "physical"; hold is true for an action that cannot be undone (risk destructive).
HOLD_CARD = {"physical": False, "hold": True, "hold_ms": HOLD_MIN_MS, "limits": [], "preview": None}
PLAIN_CARD = {"physical": False, "hold": False, "hold_ms": None, "limits": [], "preview": None}


def _feature(client, clock, action_type, params, key):
    return client.app.state.actions.request_feature(
        OWNER_P, action_type, params, idempotency_key=key, expires_at=clock.now + timedelta(minutes=10))


def test_destructive_action_card_asks_for_hold(client, clock):
    svc = client.app.state.actions
    svc.register_type("test.disk.wipe", FeatureAction(
        risk="destructive", run=lambda a, finish: finish(ExecResult("succeeded", "wiped")),
        requesters=frozenset({"person"})))
    action, created = _feature(client, clock, "test.disk.wipe", {"disk": "sdb"}, "wipe1")
    assert created and action["risk"] == "destructive" and action["approval"] == HOLD_CARD
    assert action["plan"] is None  # not physical: nothing extra is hashed into a plan
    got = client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()
    assert got["approval"] == HOLD_CARD
    listed = next(a for a in client.get("/v1/actions", headers=OWNER).json() if a["id"] == action["id"])
    assert listed["approval"] == HOLD_CARD


def test_card_follows_request_risk_and_is_plain_when_undoable(client, clock):
    svc = client.app.state.actions
    svc.register_type("test.note.write", FeatureAction(
        risk="write", run=lambda a, finish: finish(ExecResult("succeeded", "ok")), requesters=frozenset({"person"})))
    svc.register_type("test.files.clean", FeatureAction(
        risk="write", risk_for=lambda p: "destructive" if p.get("delete") else "write",
        run=lambda a, finish: finish(ExecResult("succeeded", "ok")), requesters=frozenset({"person"})))
    plain, _ = _feature(client, clock, "test.note.write", {"text": "hi"}, "n1")
    assert plain["risk"] == "write" and plain["approval"] == PLAIN_CARD
    keep, _ = _feature(client, clock, "test.files.clean", {"delete": False}, "c1")
    drop, _ = _feature(client, clock, "test.files.clean", {"delete": True}, "c2")
    assert keep["approval"] == PLAIN_CARD and drop["approval"] == HOLD_CARD


def test_handler_filed_destructive_type_card_asks_for_hold(client, clock):
    class Remover:
        def recheck(self, action):
            return None

        def dispatch(self, action):
            return ExecResult("succeeded", "removed")

    svc = client.app.state.actions
    svc.register_handler("node.remove", Remover())  # §12.5: destructive
    a = svc.file("node.remove", {"node_id": "n2"}, {"id": "person:owner", "kind": "person"},
                 expires_at=clock.now + timedelta(minutes=10), idempotency_key="rm1")
    assert a.risk == "destructive" and a.to_json()["approval"] == HOLD_CARD
