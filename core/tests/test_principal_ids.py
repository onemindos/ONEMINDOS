# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 7: standing approvals bind to permanent principal ids (gap 19, fix 12 part 1).

Each test fails without the change: before it, a rule named only the display id (`agent:<name>`), so
a revoked token's rules lived on in the next token, a reinstalled app inherited the old install's rules,
and an app could take an agent id a person already used.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import AGENT, OWNER, action_body, apply_settings_change
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.identity.models import TokenRow
from test_automation import auto_settings, client, iso, policy  # noqa: F401  (fixtures)

WHO = {"id": "agent:notes", "kind": "agent"}


def mint(client, name="agent:notes") -> dict:
    r = client.post("/v1/tokens", headers=OWNER, json={"name": "t", "principal": {"kind": "agent", "id": name}})
    assert r.status_code in (200, 201), r.text
    return r.json()


def covered(client, clock, who=WHO) -> str:
    pol = client.app.state.automation.policies
    return pol.evaluate("app.restart", {"app_id": "whoami"}, who, clock.now, paused=False).outcome


def audit(client) -> list[str]:
    import json
    return [json.loads(x)["event"] for x in client.app.state.settings.audit_path.read_text().splitlines()]


def test_a_rule_binds_to_the_agents_permanent_id(client, clock):
    tok = mint(client)
    r = policy(client, clock, requested_by=("agent:notes",))
    assert r.status_code == 202, r.text
    uid = r.json()["principals"]["agent:notes"]["uid"]
    assert uid.startswith("prn_")
    assert client.get("/v1/agents/agent:notes", headers=OWNER).json()["principal_uid"] == uid
    assert covered(client, clock) == "auto_approved"
    # re-minting under the same name while the first token lives keeps the identity; since PR 9 a second
    # credential suspends the rule until the owner re-confirms it, and the binding stays the same
    mint(client)
    assert covered(client, clock) == "needs_approval"
    apply_settings_change(client, client.post(f"/v1/approval-policies/{r.json()['id']}/reconfirm", headers=OWNER))
    assert covered(client, clock) == "auto_approved"
    assert "principal.registered" in audit(client) and tok["principal_id"] == "agent:notes"


def test_competing_agent_tokens_cannot_share_an_owner_binding(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from types import SimpleNamespace

    from sqlalchemy import select

    from onemind_core.auth import Principal
    from onemind_core.errors import ApiError
    from onemind_core.identity.service import AuthContext

    ident = client.app.state.identity
    name = "agent:concurrent"
    both_checked = Barrier(2)
    check = ident._check_agent_id

    def synchronized_check(*args):
        check(*args)
        both_checked.wait(timeout=10)

    monkeypatch.setattr(ident, "_check_agent_id", synchronized_check)

    def issue(owner):
        p = Principal(owner, "person", "owner")
        ctx = AuthContext(p, frozenset({"*"}), user=SimpleNamespace(id=owner))
        try:
            return 201, ident.create_token(ctx, p, "test credential", {"kind": "agent", "id": name}, None, None)
        except ApiError as exc:
            return exc.status, exc.reason

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(issue, ["usr_first", "usr_second"]), key=lambda result: result[0])
    assert [status for status, _ in outcomes] == [201, 409]
    assert outcomes[1][1] == "agent_id_taken"
    owner = outcomes[0][1]["owner_user_id"]
    rows = ident.repo.all(select(TokenRow).where(TokenRow.principal_id == name))
    assert [row.owner_user_id for row in rows] == [owner]
    from onemind_core.identity.models import AgentOwnerRow

    assert ident.repo.get(AgentOwnerRow, name).owner_user_id == owner
    assert client.app.state.actions.principals.live(name)["owner_user_id"] == owner


def test_a_personal_agent_cannot_claim_the_static_agents_display_name(client):
    r = client.post("/v1/tokens", headers=OWNER, json={"name": "duplicate", "principal": {"kind": "agent", "id": "agent:hermes"}})
    assert r.status_code == 409 and r.json()["reason"] == "agent_id_taken", r.text


@pytest.mark.parametrize("static_alias", [False, True])
def test_upgrade_refuses_ambiguous_stored_agent_identity(client, clock, static_alias):
    name = "agent:hermes" if static_alias else "agent:legacy-notes"
    ident = client.app.state.identity
    svc = client.app.state.automation
    headers = [AGENT] if static_alias else []
    owners = [None] if static_alias else []
    if static_alias:
        assert policy(client, clock, requested_by=(name,)).status_code == 202
        assert covered(client, clock, {"id": "hermes", "kind": "agent"}) == "auto_approved"
    else:
        for label in ("First owner", "Second owner"):
            user = client.post("/v1/users", headers=OWNER, json={"display_name": label, "role": "adult"})
            assert user.status_code == 201, user.text
            owners.append(user.json()["id"])
    for i, owner in enumerate(owners):
        token = new_secret("agt")
        ident.repo.add(TokenRow(id=f"tok_legacy_{i}", prefix=token[:11], name="Legacy credential", hash=sha256_hex(token),
                                kind="agent", principal_id=name, owner_user_id=owner, scopes=["instance:read"],
                                source="api", created_by="owner", created_at=clock(),
                                expires_at=clock() + timedelta(days=1)))
        headers.append({"Authorization": f"Bearer {token}"})

    svc.repo.add_policy(id="pol_legacy", name=None, per_day=5, window_id=None,
                        expires_at=clock.now + timedelta(days=5),
                        allow={"types": ["app.restart"], "requested_by": [name], "params": {}},
                        created_by={"id": "owner"}, created_at=clock.now)
    assert svc.policies.adopt_unbound() == 0
    assert svc.repo.get_policy("pol_legacy")["principals"] is None
    if static_alias:
        assert covered(client, clock, {"id": "hermes", "kind": "agent"}) == "needs_approval"
    r = policy(client, clock, requested_by=(name,))
    assert r.status_code == 422 and r.json()["reason"] == "unknown_principal", r.text
    for credential in headers:
        assert client.get("/v1/me", headers=credential).status_code == 401


def test_a_rule_stops_when_its_token_is_revoked(client, clock):
    tok = mint(client)
    pid = policy(client, clock, requested_by=("agent:notes",)).json()["id"]
    assert client.delete(f"/v1/tokens/{tok['id']}", headers=OWNER).status_code == 204
    assert covered(client, clock) == "needs_approval"
    # a new token under the same name is a new principal: the old rule never covers it
    mint(client)
    v = client.app.state.automation.policies.evaluate("app.restart", {"app_id": "whoami"}, WHO, clock.now, paused=False)
    assert v.outcome == "needs_approval" and v.reason in ("principal_changed", "rule_suspended")  # PR 9 suspends it
    old = client.app.state.automation.repo.get_policy(pid)["principals"]["agent:notes"]["uid"]
    assert client.get("/v1/agents/agent:notes", headers=OWNER).json()["principal_uid"] not in (None, old)
    assert "principal.retired" in audit(client)


def test_cancelling_an_agent_stops_its_rules(client, clock):
    mint(client)
    policy(client, clock, requested_by=("agent:notes",))
    assert client.post("/v1/agents/agent:notes/cancel", headers=OWNER).status_code == 200
    assert covered(client, clock) == "needs_approval"


def test_a_rule_for_an_agent_nobody_holds_is_refused(client, clock):
    r = policy(client, clock, requested_by=("agent:ghost",))
    assert r.status_code == 422 and r.json()["reason"] == "unknown_principal"


def test_a_static_file_agent_binds_too(client, clock):
    r = policy(client, clock, requested_by=("agent:hermes",))
    assert r.status_code == 202
    assert r.json()["principals"]["agent:hermes"]["uid"].startswith("prn_")
    assert covered(client, clock, {"id": "hermes", "kind": "agent"}) == "auto_approved"


def test_an_app_installed_with_a_colliding_id_is_refused(client, clock, executor):
    # A personal agent token minted under the app's id before the app reached the catalog.
    token = new_secret("agt")
    client.app.state.identity.repo.add(TokenRow(
        id="tok_collide", prefix=token[:11], name="old agent", hash=sha256_hex(token), kind="agent",
        principal_id="agent:hermes-like", owner_user_id=None, scopes=["apps:read"], source="api",
        created_by="owner", created_at=clock(), expires_at=clock() + timedelta(days=1)))
    r = client.post("/v1/actions", json=action_body(clock, app_id="hermes-like", key="c1"), headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "agent_id_taken", r.text
    assert executor.calls == []
    # once that token is revoked, the app installs with an identity of its own
    assert client.delete("/v1/tokens/tok_collide", headers=OWNER).status_code == 204
    r = client.post("/v1/actions", json=action_body(clock, app_id="hermes-like", key="c2"), headers=OWNER)
    assert r.status_code == 201, r.text
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    live = client.app.state.gateway.actions.principals.live("agent:hermes-like")
    assert live["source"] == "app"


def test_a_reinstalled_app_does_not_inherit_the_old_installs_rules(client, clock):
    def run(type_, key):
        r = client.post("/v1/actions", json=action_body(clock, app_id="hermes-like", type_=type_, key=key), headers=OWNER)
        assert r.status_code == 201, r.text
        assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"

    run("app.install", "i1")
    who = {"id": "agent:hermes-like", "kind": "agent"}
    assert policy(client, clock, requested_by=("agent:hermes-like",)).status_code == 202
    assert covered(client, clock, who) == "auto_approved"
    run("app.remove", "r1")
    assert covered(client, clock, who) == "needs_approval"
    run("app.install", "i2")
    assert covered(client, clock, who) == "needs_approval"


def test_rules_made_before_the_upgrade_bind_to_whoever_holds_the_id_now(client, clock):
    repo = client.app.state.automation.repo
    repo.add_policy(id="pol_old", name=None, per_day=5, window_id=None, expires_at=clock.now + timedelta(days=5),
                    allow={"types": ["app.restart"], "requested_by": ["agent:hermes", "agent:ghost"], "params": {}},
                    created_by={"id": "owner"}, created_at=clock.now)
    pol = client.app.state.automation.policies
    assert covered(client, clock, {"id": "hermes", "kind": "agent"}) == "needs_approval"  # unbound: fails closed
    assert pol.adopt_unbound() == 1
    bound = repo.get_policy("pol_old")["principals"]
    assert set(bound) == {"agent:hermes"}  # nobody holds agent:ghost: it stays unbound and never matches
    assert covered(client, clock, {"id": "hermes", "kind": "agent"}) == "auto_approved"
    assert covered(client, clock, {"id": "agent:ghost", "kind": "agent"}) == "needs_approval"
    assert "approval.policy.bound" in audit(client)
    assert pol.adopt_unbound() == 0  # idempotent
    _ = iso
