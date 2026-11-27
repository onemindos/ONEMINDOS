# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 9: rule revisions, max_uses, size caps, notify_after, unused lapse, target,
forever, suspension (design §3.6, §3.6.2; F-10, D-028).

Each test fails without the change: before it a rule could not be edited (only deleted), had no use
or size limits, never lapsed, matched no target, always expired within 90 days, and kept firing after
its agent's token was rotated or the agent started reading outside text.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from conftest import AGENT, OWNER, action_body
from onemind_core.actions import FeatureAction
from onemind_core.auth import Principal
from onemind_core.executors import ExecResult
from test_automation import auto_settings, client, install, iso  # noqa: F401  (fixtures)

HERMES = Principal("hermes", "agent", "agent")


def body(clock, **kw) -> dict:
    out = {"allow": {"types": ["app.restart"], "requested_by": ["agent:hermes"], "params": {}},
           "limits": {"per_day": 50}, "expires_at": iso(clock.now + timedelta(days=30))}
    for k, v in kw.items():
        if k in ("max_uses", "bytes_per_day", "items_per_day"):
            out["limits"][k] = v
        elif k in ("types", "requested_by"):
            out["allow"][k] = v
        else:
            out[k] = v
    return out


def make(client, clock, **kw):
    return client.post("/v1/approval-policies", json=body(clock, **kw), headers=OWNER)


def restart(client, clock, key):
    return client.post("/v1/actions", json=action_body(clock, "whoami", "app.restart", key=key), headers=AGENT).json()


def audit(client) -> list[dict]:
    return [json.loads(x) for x in client.app.state.settings.audit_path.read_text().splitlines()]


def test_narrowing_applies_at_once_and_widening_needs_a_passkey(client, clock):
    pol = make(client, clock).json()
    client.app.state.identity.passkeys_active = lambda: True
    r = client.patch(f"/v1/approval-policies/{pol['id']}", headers=OWNER, json={"limits": {"per_day": 2}})
    assert r.status_code == 200 and r.json()["revision"] == 2 and r.json()["limits"]["per_day"] == 2
    for widen in ({"limits": {"per_day": 3}}, {"expires_at": iso(clock.now + timedelta(days=60))}, {"forever": True},
                  {"lapse_unused_days": None}, {"allow": {"types": ["app.restart", "backup.run"], "requested_by": ["agent:hermes"]}}):
        r = client.patch(f"/v1/approval-policies/{pol['id']}", headers=OWNER, json=widen)
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required", (widen, r.text)
    assert client.get("/v1/approval-policies", headers=OWNER).json()[0]["revision"] == 2
    # a stale revision is refused; an agent never edits
    assert client.patch(f"/v1/approval-policies/{pol['id']}", headers=OWNER, json={"revision": 1, "name": "x"}).status_code == 409
    assert client.patch(f"/v1/approval-policies/{pol['id']}", headers=AGENT, json={"name": "x"}).status_code == 403
    revised = [e for e in audit(client) if e["event"] == "approval.policy.revised"]
    assert revised[0]["data"]["direction"] == "narrow" and revised[0]["data"]["changed"] == ["limits.per_day"]
    client.app.state.identity.passkeys_active = lambda: False  # owner token, no passkeys yet: widening is allowed
    r = client.patch(f"/v1/approval-policies/{pol['id']}", headers=OWNER, json={"limits": {"per_day": 3}})
    assert r.status_code == 200 and r.json()["revision"] == 3


def test_max_uses_one_approves_once_then_the_rule_ends(client, clock):
    install(client, clock)
    pid = make(client, clock, max_uses=1).json()["id"]
    assert restart(client, clock, "m0")["state"] == "succeeded"
    assert restart(client, clock, "m1")["state"] == "awaiting_approval"
    assert client.app.state.automation.repo.get_policy(pid)["state"] == "ended"


def test_a_use_that_did_not_go_through_reopens_a_max_uses_rule_at_the_new_revision(client, clock):
    """Intended: release_use makes the ended rule live again but keeps the bumped revision, so an
    approval or plan pinned to the old revision is not silently valid again."""
    install(client, clock)
    pid = make(client, clock, max_uses=1).json()["id"]
    used = restart(client, clock, "r0")
    repo = client.app.state.automation.repo
    ended = repo.get_policy(pid)
    assert ended["state"] == "ended" and ended["revision"] == 2
    repo.release_use(used["id"])
    back = repo.get_policy(pid)
    assert back["state"] == "active" and back["revision"] == 2 and back["uses"] == 0
    repo.release_use(used["id"])  # a second release changes nothing
    assert repo.get_policy(pid)["uses"] == 0


def test_a_rule_unused_for_14_days_lapses(client, clock):
    install(client, clock)
    pid = make(client, clock).json()["id"]
    keep = make(client, clock, lapse_unused_days=None, types=["backup.run"]).json()["id"]
    assert client.get("/v1/approval-policies", headers=OWNER).json()[0]["lapse_unused_days"] == 14  # on by default
    clock.advance(13 * 86400)
    assert restart(client, clock, "l0")["state"] == "succeeded"  # a use restarts the 14 days
    clock.advance(13 * 86400)
    assert restart(client, clock, "l1")["state"] == "succeeded"
    clock.advance(14 * 86400 + 1)
    assert restart(client, clock, "l2")["state"] == "awaiting_approval"
    ids = {p["id"] for p in client.get("/v1/approval-policies", headers=OWNER).json()}
    assert pid not in ids and keep in ids  # lapsed and gone; the unticked one stays
    assert any(e["event"] == "approval.policy.lapsed" and e["data"]["policy_id"] == pid for e in audit(client))


@pytest.fixture
def notes(client):
    """A write type that names a target and a size (as notes.write will, design PR 20)."""
    gw = client.app.state.gateway
    ran = []

    def run(a, finish):
        ran.append(a.params)
        finish(ExecResult("succeeded", "written"))

    if "test.note.write" not in gw.actions.feature_types:
        gw.actions.register_type("test.note.write", FeatureAction(
            "write", run, frozenset({"person", "agent"}),
            target_for=lambda p: ("notes", f"vault:u1/{p['path']}"), size_for=lambda p: (p["bytes"], 1)))
    return gw, ran


def note(gw, clock, key, path="Agent Inbox/a.md", size=10):
    out, _ = gw.actions.request_feature(HERMES, "test.note.write", {"path": path, "bytes": size},
                                        idempotency_key=key, expires_at=clock.now + timedelta(hours=1))
    return out["state"]


def test_byte_caps_hold(client, clock, notes):
    gw, _ = notes
    assert make(client, clock, types=["test.note.write"], bytes_per_day=100, items_per_day=5).status_code == 201
    assert note(gw, clock, "b0", size=60) == "succeeded"
    assert note(gw, clock, "b1", size=60) == "awaiting_approval"  # 120 bytes would pass the cap
    assert note(gw, clock, "b2", size=40) == "succeeded"  # exactly 100
    assert any(e["event"] == "automation.policy.limit_reached" and e["data"]["reason"] == "cap_reached" for e in audit(client))


def test_a_target_rule_matches_only_inside_its_locations(client, clock, notes):
    gw, _ = notes
    r = make(client, clock, types=["test.note.write"], target={"type": "notes", "locations": ["vault:u1/Agent Inbox/**"]})
    assert r.status_code == 201, r.text
    assert note(gw, clock, "t0", "Agent Inbox/today.md") == "succeeded"
    assert note(gw, clock, "t1", "Diary/today.md") == "awaiting_approval"
    assert note(gw, clock, "t2", "Agent Inbox/../Diary/x.md") == "awaiting_approval"
    bad = make(client, clock, types=["test.note.write"], target={"type": "notes", "locations": ["vault:u1/../**"]})
    assert bad.status_code == 422
    # a type that names no target cannot carry one
    assert make(client, clock, target={"type": "notes", "locations": ["x/**"]}).status_code == 422


def test_forever_rules_are_fenced(client, clock):
    assert make(client, clock, forever=True, expires_at=None, accept_injection_risk=True).status_code == 422
    assert make(client, clock, accept_injection_risk=True).status_code == 422  # needs L2 (design PR 11)
    assert make(client, clock, types=["app.install"], forever=True, expires_at=None).status_code == 422
    assert make(client, clock, forever=True).status_code == 422  # forever has no expires_at
    assert make(client, clock, expires_at=iso(clock.now + timedelta(days=181))).status_code == 422
    assert make(client, clock, expires_at=iso(clock.now + timedelta(days=180))).status_code == 201
    assert make(client, clock, notify_after="silent").status_code == 422  # silent is for read-only rules
    # D-028: any Forever rule needs a proven key (L2), which design PR 11 brings; refused until then
    r = make(client, clock, forever=True, expires_at=None, lapse_unused_days=None, types=["backup.run"])
    assert r.status_code == 409 and r.json()["reason"] == "needs_proven_key", r.text
    pid = make(client, clock).json()["id"]
    r = client.patch(f"/v1/approval-policies/{pid}", headers=OWNER, json={"forever": True})
    assert r.status_code == 409 and r.json()["reason"] == "needs_proven_key", r.text
    assert next(p for p in client.get("/v1/approval-policies", headers=OWNER).json() if p["id"] == pid)["forever"] is False
    client.app.state.automation.policies.proven_key = lambda: True  # what PR 11 wires
    r = make(client, clock, forever=True, expires_at=None, lapse_unused_days=None, types=["backup.run"])
    assert r.status_code == 201 and r.json()["forever"] is True and r.json()["expires_at"] is None


def test_forever_rules_get_a_90_day_review_that_ends_nothing(client, clock):
    install(client, clock)
    client.app.state.automation.policies.proven_key = lambda: True  # Forever needs L2 (design PR 11)
    pid = make(client, clock, forever=True, expires_at=None, lapse_unused_days=None).json()["id"]
    clock.advance(91 * 86400)
    svc = client.app.state.automation
    assert svc.policies.review_tick(clock.now) == [pid]
    assert svc.policies.review_tick(clock.now) == []  # once per period
    row = next(p for p in client.get("/v1/approval-policies", headers=OWNER).json() if p["id"] == pid)
    assert row["review_due"] is True and row["state"] == "active"
    assert restart(client, clock, "f0")["state"] == "succeeded"  # ignoring the reminder ends nothing
    assert client.post(f"/v1/approval-policies/{pid}/keep", headers=OWNER).json()["review_due"] is False
    assert any(e["event"] == "approval.policy.review_due" for e in audit(client))


def mint(client, name="agent:notes"):
    r = client.post("/v1/tokens", headers=OWNER, json={"name": "t", "principal": {"kind": "agent", "id": name}})
    assert r.status_code in (200, 201), r.text
    return r.json()


def covered(client, clock, who="agent:notes"):
    return client.app.state.automation.policies.evaluate(
        "app.restart", {"app_id": "whoami"}, {"id": who, "kind": "agent"}, clock.now, paused=False)


def test_rotating_the_agents_token_suspends_its_rules_until_reconfirmed(client, clock):
    tok = mint(client)
    pid = make(client, clock, requested_by=["agent:notes"]).json()["id"]
    assert covered(client, clock).outcome == "auto_approved"
    assert client.post(f"/v1/tokens/{tok['id']}/rotate", headers=OWNER, json={"grace_s": 0}).status_code == 201
    v = covered(client, clock)
    assert (v.outcome, v.reason) == ("needs_approval", "rule_suspended")
    row = client.get("/v1/approval-policies", headers=OWNER).json()[0]
    assert row["state"] == "suspended" and row["suspended_reason"] == "token_rotated"
    r = client.post(f"/v1/approval-policies/{pid}/reconfirm", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "active"
    assert covered(client, clock).outcome == "auto_approved"
    events = {e["event"] for e in audit(client)}
    assert {"approval.policy.suspended", "approval.policy.reconfirmed"} <= events


def test_an_agent_that_starts_reading_outside_text_has_its_rules_suspended(client, clock):
    mint(client)
    client.put("/v1/agents/agent:notes/inputs", headers=OWNER, json={"external_inputs": [], "accept_injection_risk": []})
    pid = make(client, clock, requested_by=["agent:notes"]).json()["id"]
    r = client.put("/v1/agents/agent:notes/inputs", headers=OWNER, json={"external_inputs": ["web"], "accept_injection_risk": []})
    assert r.status_code == 200, r.text
    row = next(p for p in client.get("/v1/approval-policies", headers=OWNER).json() if p["id"] == pid)
    assert (row["state"], row["suspended_reason"]) == ("suspended", "became_exposed")


def test_a_revoked_token_suspends_and_reconfirm_binds_the_new_identity(client, clock):
    tok = mint(client)
    pid = make(client, clock, requested_by=["agent:notes"]).json()["id"]
    client.delete(f"/v1/tokens/{tok['id']}", headers=OWNER)
    assert client.post(f"/v1/approval-policies/{pid}/reconfirm", headers=OWNER).status_code == 422  # nobody holds it now
    mint(client)
    r = client.post(f"/v1/approval-policies/{pid}/reconfirm", headers=OWNER)
    assert r.status_code == 200
    assert covered(client, clock).outcome == "auto_approved"


def test_revoke_is_one_tap_without_a_passkey(client, clock):
    install(client, clock)
    a = make(client, clock).json()["id"]
    b = make(client, clock, types=["backup.run"]).json()["id"]
    client.app.state.identity.passkeys_active = lambda: True
    r = client.post(f"/v1/approval-policies/{a}/revoke", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "revoked" and r.json()["revoked_by"]["id"] == "owner"
    assert restart(client, clock, "r0")["state"] == "awaiting_approval"
    assert client.post(f"/v1/approval-policies/{a}/revoke", headers=OWNER).status_code == 404
    assert client.post(f"/v1/approval-policies/{b}/revoke", headers=AGENT).status_code == 403
    r = client.post("/v1/approval-policies/revoke-all", headers=OWNER, json={"principal": "agent:hermes"})
    assert r.json()["revoked"] == [b]
    assert client.get("/v1/approval-policies", headers=OWNER).json() == []
