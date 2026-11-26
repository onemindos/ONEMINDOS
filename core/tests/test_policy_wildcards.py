# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 5: no wildcard crossings, automation authorship, revoke races (gap 18)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from onemind_core.app import create_app
from onemind_core.automation import store as astore
from test_automation import (  # noqa: F401  (fixtures)
    auto_settings, client, create_rule, iso, policy, remove_rule,
)
from conftest import AGENT, GUEST, OWNER

AT_NOON = None


def _legacy(client, clock, who, pid="pol_legacy", state="active"):
    """A rule written before PR 5, straight into the table (validation refuses it now)."""
    repo = client.app.state.automation.repo
    repo.add_policy(id=pid, name=None, per_day=5, window_id=None, expires_at=clock.now + timedelta(days=5),
                    allow={"types": ["app.restart"], "requested_by": [who], "params": {}},
                    created_by={"id": "owner"}, created_at=clock.now)
    if state != "active":
        from sqlalchemy import update
        with repo.db.session.begin() as s:
            s.execute(update(astore.PolicyRow).where(astore.PolicyRow.id == pid).values(state=state))
    return pid


@pytest.mark.parametrize("who", ["person:*", "automation:*", "agent:*", "plugin:*"])
def test_new_wildcard_rules_are_refused(client, clock, who):
    r = policy(client, clock, requested_by=(who,))
    assert r.status_code == 422 and "names it exactly" in r.json()["message"]


def test_an_old_person_wildcard_no_longer_covers_children_teens_or_guests(client, clock):
    _legacy(client, clock, "person:*")
    pol = client.app.state.automation.policies
    roles = {"u_owner": "owner", "u_adult": "adult", "u_child": "child", "u_teen": "teen", "u_guest": "guest"}
    pol.person_role = roles.get
    at = clock.now
    verdicts = {r: pol.evaluate("app.restart", {"app_id": "whoami"}, {"id": f"person:u_{r}", "kind": "person"}, at,
                                paused=False).outcome for r in ("owner", "adult", "child", "teen", "guest")}
    assert verdicts == {"owner": "auto_approved", "adult": "auto_approved", "child": "needs_approval",
                        "teen": "needs_approval", "guest": "needs_approval"}
    # a person the identity module cannot name is not covered either (fails closed)
    assert pol.evaluate("app.restart", {"app_id": "whoami"}, {"id": "person:stranger", "kind": "person"}, at,
                        paused=False).outcome == "needs_approval"


def test_an_agent_proposed_automation_never_matches_an_automation_wildcard(client, clock):
    _legacy(client, clock, "automation:*")
    rule = create_rule(client, remove_rule({"event": {"type": "app.unhealthy"}}))
    assert rule["author"]["id"] == "owner" and rule["proposed_by"] is None
    s = client.app.state.automation
    who = {"id": f"automation:{rule['id']}", "kind": "automation"}
    args = ("app.restart", {"app_id": "whoami"}, who, clock.now)
    assert s.policies.evaluate(*args, paused=False).outcome == "auto_approved"
    from sqlalchemy import update
    with s.repo.db.session.begin() as db:  # an agent proposed it and the owner accepted it
        db.execute(update(astore.RuleRow).where(astore.RuleRow.id == rule["id"])
                   .values(proposed_by={"id": "agent:hermes", "kind": "agent"}))
    assert s.get(rule["id"])["proposed_by"]["id"] == "agent:hermes"
    assert s.policies.evaluate(*args, paused=False).outcome == "needs_approval"
    ghost = {"id": "automation:rule_gone", "kind": "automation"}
    assert s.policies.evaluate("app.restart", {"app_id": "whoami"}, ghost, clock.now, paused=False).outcome == "needs_approval"


def test_migration_pauses_old_automation_wildcards_until_the_owner_confirms(client, clock):
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE automation_rules (id VARCHAR(40))"))
        c.execute(text("CREATE TABLE automation_policies (id VARCHAR(40), state VARCHAR(16), revision INT, allow JSON)"))
        for pid, who in (("a", "automation:*"), ("b", "agent:hermes"), ("c", "person:*")):
            c.execute(text("INSERT INTO automation_policies VALUES (:i, 'active', 1, :a)"),
                      {"i": pid, "a": '{"requested_by": ["%s"]}' % who})
        astore._automation_v2(c)
        rows = dict(c.execute(text("SELECT id, state FROM automation_policies")).all())
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(automation_rules)"))}
    assert rows == {"a": "paused", "b": "active", "c": "active"} and "proposed_by" in cols

    pid = _legacy(client, clock, "automation:*", state="paused")
    listed = {p["id"]: p for p in client.get("/v1/approval-policies", headers=OWNER).json()}
    assert listed[pid]["state"] == "paused"
    pol = client.app.state.automation.policies
    rule = create_rule(client, remove_rule({"event": {"type": "app.unhealthy"}}))
    who = {"id": f"automation:{rule['id']}", "kind": "automation"}
    assert pol.evaluate("app.restart", {"app_id": "whoami"}, who, clock.now, paused=False).outcome == "needs_approval"
    assert client.post(f"/v1/approval-policies/{pid}/confirm", headers=AGENT).status_code == 403
    r = client.post(f"/v1/approval-policies/{pid}/confirm", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "active" and r.json()["revision"] == 2
    assert pol.evaluate("app.restart", {"app_id": "whoami"}, who, clock.now, paused=False).outcome == "auto_approved"
    assert client.post(f"/v1/approval-policies/{pid}/confirm", headers=OWNER).status_code == 404


def test_revoke_bumps_the_revision_and_a_racing_use_is_refused(client, clock):
    pid = policy(client, clock, requested_by=("agent:hermes",)).json()["id"]
    repo = client.app.state.automation.repo
    assert repo.reserve_use(pid, 1, 5, "act_one", clock.now) == ("ok", 1)
    assert client.delete(f"/v1/approval-policies/{pid}", headers=OWNER).status_code == 204
    row = repo.get_policy(pid)
    assert row["state"] == "deleted" and row["revision"] == 2
    # a request that matched before the revoke now tries to take its use at the old revision
    assert repo.reserve_use(pid, 1, 5, "act_two", clock.now) == ("changed", 0)
    assert repo.reserve_use(pid, 2, 5, "act_three", clock.now) == ("changed", 0)
    assert repo.uses_by_action(["act_two", "act_three"]) == {}


def test_a_new_rule_never_approves_a_request_already_waiting(client, clock):
    from conftest import action_body
    from test_automation import install

    install(client, clock)
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.restart", key="pend1"), headers=AGENT)
    assert r.json()["state"] == "awaiting_approval"
    assert policy(client, clock, requested_by=("agent:hermes",)).status_code == 201
    assert client.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
