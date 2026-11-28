# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 12: approve and remember (design §3.6.1, fix 4).

Each test fails without the change: before it an approval could not make a rule at all, and nothing
bound a rule body to the owner's passkey.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.permissions import remember as rm
from test_identity import SoftAuthenticator, csrf, id_settings, register_passkey, setup_owner


@pytest.fixture
def box(settings, clock, executor):
    """A household with an owner account and a passkey, whoami installed, and hermes asking to restart it."""
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as c:
        setup_owner(c)
        r = c.post("/v1/actions", json=action_body(clock, "whoami", key="inst"), headers=OWNER)
        assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
        key = SoftAuthenticator()
        register_passkey(c, key)
        yield c, key


@pytest.fixture
def l2(box):
    """What design PR 11 wires: the owner proved a hardware key (L2), so T1 and Forever rules may be remembered."""
    box[0].app.state.automation.policies.proven_key = lambda: True
    box[0].app.state.identity.passkey_verification_level = lambda _credential: 2
    return box


def ask(c, clock, key_):
    r = c.post("/v1/actions", json=action_body(clock, "whoami", "app.restart", key=key_), headers=AGENT)
    assert r.status_code == 201, r.text
    return r.json()


def test_approve_and_remember_makes_the_narrowest_rule_bound_to_the_passkey(box, l2, clock):
    c, key = box
    a = ask(c, clock, "r0")
    assert a["state"] == "awaiting_approval"
    opts = c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": {}}, headers=csrf(c)).json()
    rule = opts["remember"]["rule"]
    assert rule["allow"] == {"types": ["app.restart"], "requested_by": ["agent:hermes"], "params": {"app_id": {"const": "whoami"}}}
    assert rule["limits"] == {"per_day": 10} and rule["lapse_unused_days"] == 14 and rule["forever"] is False
    assert opts["remember"]["rule_sha256"] == rm.rule_sha256(rule)
    assert opts["remember"]["summary"].startswith("agent:hermes may app.restart for app_id = whoami, up to 10 a day")
    assert opts["remember"]["required_level"] == "L2" and opts["remember"]["enforced_level"] == "L1"
    assert opts["device_payload"].startswith("onemind-approve-v2\n") and opts["remember"]["rule_sha256"] in opts["device_payload"]
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=csrf(c),
               json={"webauthn": key.assert_(opts["challenge"]), "remember": {"rule": rule}})
    assert r.status_code == 200, r.text
    pid = r.json()["remembered_policy"]
    made = next(p for p in c.get("/v1/approval-policies", headers=OWNER).json() if p["id"] == pid)
    assert made["created_from"] == a["id"] and made["allow"] == rule["allow"]
    # the next request like it goes through on the rule
    assert ask(c, clock, "r1")["state"] == "succeeded"


def test_failed_remember_insert_rolls_back_approval_and_can_be_retried(l2, clock, executor, monkeypatch):
    from sqlalchemy.exc import OperationalError

    c, key = l2
    action = ask(c, clock, "remember-atomic")
    url = f"/v1/actions/{action['id']}"
    repo = c.app.state.automation.repo
    ran = len(executor.calls)

    def fail_after_insert(session, **values):
        insert_policy(session, **values)
        session.flush()
        raise OperationalError("simulated write failure", {}, RuntimeError("policy store unavailable"))

    def approve():
        opts = c.post(f"{url}/approve-options", json={"remember": {}}, headers=csrf(c)).json()
        return c.post(f"{url}/approve", headers=csrf(c), json={"webauthn": key.assert_(opts["challenge"]),
                      "remember": {"rule": opts["remember"]["rule"]}})

    insert_policy = repo.insert_policy
    with monkeypatch.context() as mp:
        mp.setattr(repo, "insert_policy", fail_after_insert)
        failed = approve()
    assert failed.status_code == 503 and failed.json()["reason"] == "remember_write_failed", failed.text
    assert c.get(url, headers=OWNER).json()["state"] == "awaiting_approval"
    assert c.get("/v1/approval-policies", headers=OWNER).json() == []
    assert len(executor.calls) == ran
    retried = approve()
    assert retried.status_code == 200 and retried.json()["state"] == "succeeded", retried.text
    assert len(executor.calls) == ran + 1
    assert [rule["id"] for rule in c.get("/v1/approval-policies", headers=OWNER).json()] == [retried.json()["remembered_policy"]]


def test_security_change_approval_requires_the_exact_change_and_l2(box, monkeypatch):
    c, key = box
    headers = csrf(c)
    path = "/v1/permission-modes/agent:hermes"
    # Use explicit initial policy state since this fixture runs with its default set to Auto.
    assert c.put(path, headers=headers, json={"mode": "ask"}).status_code == 200
    first = c.put(path, headers=headers, json={"mode": "remember"})
    second = c.put(path, headers=headers, json={"mode": "auto"})
    assert first.status_code == second.status_code == 202
    first_url, second_url = (f"/v1/actions/{r.json()['id']}" for r in (first, second))
    assert first.json()["params"]["mode"] == "remember" and second.json()["params"]["mode"] == "auto"

    def signed(url):
        o = c.post(f"{url}/approve-options", headers=headers)
        assert o.status_code == 200, o.text
        return {"webauthn": key.assert_(o.json()["challenge"])}

    wrong = c.post(f"{second_url}/approve", headers=headers, json=signed(first_url))
    assert wrong.status_code == 401 and "another action" in wrong.json()["message"], wrong.text
    l1 = c.post(f"{first_url}/approve", headers=headers, json=signed(first_url))
    assert l1.status_code == 409 and l1.json()["reason"] == "needs_proven_key"
    # The L1 action assertion also creates a fresh passkey session. The session alone is insufficient.
    session_only = c.post(f"{first_url}/approve", headers=headers)
    assert session_only.status_code in (401, 409)
    assert c.get(path, headers=headers).json()["mode"] == "ask"

    monkeypatch.setattr(c.app.state.identity, "passkey_verification_level", lambda _credential: 2)
    accepted = c.post(f"{first_url}/approve", headers=headers, json=signed(first_url))
    assert accepted.status_code == 200 and accepted.json()["state"] == "succeeded", accepted.text
    assert c.get(path, headers=headers).json()["mode"] == "remember"


def test_a_tampered_rule_body_after_the_challenge_is_refused(box, l2, clock):
    c, key = box
    a = ask(c, clock, "t0")
    opts = c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": {}}, headers=csrf(c)).json()
    wider = {**opts["remember"]["rule"], "limits": {"per_day": 1000}, "allow": {**opts["remember"]["rule"]["allow"], "params": {}}}
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=csrf(c),
               json={"webauthn": key.assert_(opts["challenge"]), "remember": {"rule": wider}})
    assert r.status_code == 409 and r.json()["reason"] == "rule_changed", r.text
    assert c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert c.get("/v1/approval-policies", headers=OWNER).json() == []
    # a plain challenge cannot carry a rule either
    plain = c.post(f"/v1/actions/{a['id']}/approve-options", headers=csrf(c)).json()
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=csrf(c),
               json={"webauthn": key.assert_(plain["challenge"]), "remember": {"rule": opts["remember"]["rule"]}})
    assert r.status_code == 409 and r.json()["reason"] == "rule_changed"


def test_remember_needs_the_passkey_not_the_phone_key_or_a_token(box, l2, clock):
    c, _ = box
    a = ask(c, clock, "p0")
    opts = c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": {}}, headers=csrf(c)).json()
    sig = {"key_id": "apk_x", "challenge": opts["challenge"], "signature": "AAAA"}
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=csrf(c),
               json={"device_signature": sig, "remember": {"rule": opts["remember"]["rule"]}})
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER, json={"remember": {"rule": opts["remember"]["rule"]}})
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"


def test_the_person_may_widen_one_field_at_a_time_and_the_summary_follows(box, l2, clock):
    c, key = box
    a = ask(c, clock, "w0")
    choice = {"lifetime": "forever", "lapse_unused": False, "per_day": 3, "unpin": ["app_id"], "notify_after": "each"}
    opts = c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": choice}, headers=csrf(c)).json()
    rule = opts["remember"]["rule"]
    assert rule["forever"] is True and rule["expires_at"] is None and rule["allow"]["params"] == {}
    assert "with any parameters, up to 3 a day, with no end date" in opts["remember"]["summary"]
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=csrf(c),
               json={"webauthn": key.assert_(opts["challenge"]), "remember": {"rule": rule}})
    assert r.status_code == 200, r.text
    assert c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": {"unpin": ["nope"]}},
                  headers=csrf(c)).status_code == 409  # already approved


def test_remember_is_refused_above_write(box, clock):
    c, _ = box
    r = c.post("/v1/actions", json=action_body(clock, "uptime-kuma", key="i0"), headers=AGENT)
    assert r.status_code == 201
    r = c.post(f"/v1/actions/{r.json()['id']}/approve-options", json={"remember": {}}, headers=csrf(c))
    assert r.status_code == 422 and r.json()["reason"] == "remember_refused" and "sensitive" in r.json()["message"]


NOW = datetime(2026, 11, 25, tzinfo=UTC)
AGENT_REQ = {"id": "hermes", "kind": "agent"}


@pytest.mark.parametrize("action, physical, needle", [
    ({"type": "app.restart", "params": {"app_id": "x"}, "requested_by": AGENT_REQ, "risk": "write",
      "plan": {"taint": {"sources": ["input:web"]}}}, False, "tainted"),
    ({"type": "app.restart", "params": {"app_id": "x"}, "requested_by": AGENT_REQ, "risk": "write"}, True, "physical"),
    ({"type": "app.install", "params": {"app_id": "x"}, "requested_by": AGENT_REQ, "risk": "sensitive"}, False, "sensitive"),
    ({"type": "backup.restore", "params": {}, "requested_by": AGENT_REQ, "risk": "destructive"}, False, "destructive"),
    ({"type": "app.restart", "params": {"app_id": "x"}, "requested_by": AGENT_REQ, "risk": "write",
      "plan": {"network_paths": [{"from": "a", "to": "b"}]}}, False, "hard-floor"),
    ({"type": "automation.rule.enable", "params": {}, "requested_by": AGENT_REQ, "risk": "write"}, False, "hard-floor"),
    ({"type": "app.restart", "params": {"app_id": "x"}, "requested_by": {"id": "adult", "kind": "person"},
      "risk": "write"}, False, "own requests"),
])
def test_remember_is_refused_for_taint_physical_high_risk_and_floor_items(action, physical, needle):
    why = rm.why_not(action, physical)
    assert why is not None and needle in why


def test_a_dated_read_only_rule_needs_l1_and_everything_else_l2():
    read = rm.narrowest_rule({"id": "a", "type": "system.check", "params": {}, "requested_by": AGENT_REQ},
                             rm.RememberChoice(), NOW)
    assert rm.required_level(read) == "L1"
    assert rm.required_level({**read, "forever": True}) == "L2"
    write = rm.narrowest_rule({"id": "a", "type": "app.restart", "params": {"app_id": "x"}, "requested_by": AGENT_REQ},
                              rm.RememberChoice(lifetime="90d"), NOW)
    assert rm.required_level(write) == "L2" and write["expires_at"] == "2027-02-23T00:00:00Z"


def test_remember_is_refused_while_the_agent_is_on_always_ask(box, clock):
    c, _ = box
    c.put("/v1/permission-modes/agent:hermes", headers=OWNER, json={"mode": "ask"})
    a = ask(c, clock, "m0")
    r = c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": {}}, headers=csrf(c))
    assert r.status_code == 409 and r.json()["reason"] == "mode_ignores_rules"


def test_t1_and_forever_remember_need_l2_which_is_refused_until_pr_11(box, clock):
    """Opus review on #1204 (D-028): L1 may make only a dated T0 rule. app.restart is a write (T1)."""
    c, key = box
    a = ask(c, clock, "l0")
    for choice in ({}, {"lifetime": "forever"}):
        r = c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": choice}, headers=csrf(c))
        assert r.status_code == 409 and r.json()["reason"] == "needs_proven_key", r.text
    # a challenge made while L2 was there does not carry the rule past its loss: checked again before the yes
    c.app.state.automation.policies.proven_key = lambda: True
    opts = c.post(f"/v1/actions/{a['id']}/approve-options", json={"remember": {}}, headers=csrf(c)).json()
    c.app.state.automation.policies.proven_key = lambda: False
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=csrf(c),
               json={"webauthn": key.assert_(opts["challenge"]), "remember": {"rule": opts["remember"]["rule"]}})
    assert r.status_code == 409 and r.json()["reason"] == "needs_proven_key", r.text
    assert c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert c.get("/v1/approval-policies", headers=OWNER).json() == []
    # approving once still works
    plain = c.post(f"/v1/actions/{a['id']}/approve-options", headers=csrf(c)).json()
    r = c.post(f"/v1/actions/{a['id']}/approve", headers=csrf(c), json={"webauthn": key.assert_(plain["challenge"])})
    assert r.status_code == 200, r.text
