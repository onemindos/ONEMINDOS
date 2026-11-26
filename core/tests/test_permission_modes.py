# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 10: permission modes (design §3.5, §3.5.1; F-7, F-8, fix 6, fix 14).

Each test fails without the change: before it there was no mode, so every rule fired for every
principal, nothing waited for an owner passkey, and nobody could lock an agent or make it headless.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from conftest import ADULT, AGENT, OWNER, action_body
from onemind_core.auth import Principal
from onemind_core.errors import ApiError
from test_automation import auto_settings, client, install, iso, policy  # noqa: F401  (fixtures)

pytestmark = pytest.mark.real_mode_defaults


@pytest.fixture
def passkey(monkeypatch):
    """The owner has enrolled a passkey (F-8 met); step-up itself stays off, as for an owner token."""
    from onemind_core.routers import permissions
    monkeypatch.setattr(permissions, "owner_has_passkey", lambda app: True)


def restart(client, clock, key, headers=AGENT):
    return client.post("/v1/actions", json=action_body(clock, "whoami", "app.restart", key=key), headers=headers)


def mode(client, who, m, headers=OWNER, **kw):
    return client.put(f"/v1/permission-modes/{who}", headers=headers, json={"mode": m, **kw})


def audit(client) -> list[dict]:
    return [json.loads(x) for x in client.app.state.settings.audit_path.read_text().splitlines()]


def test_with_no_owner_passkey_every_loosening_gets_409(client, clock):
    r = mode(client, "agent:hermes", "auto")
    assert r.status_code == 409 and r.json()["reason"] == "no_owner_passkey" and "passkey first" in r.json()["message"]
    assert client.put("/v1/permission-modes", headers=OWNER, json={"mode": "headless"}).status_code == 409
    assert policy(client, clock, requested_by=("agent:hermes",)).status_code == 409
    # tightening never waits for a passkey
    assert mode(client, "agent:hermes", "locked").status_code == 200
    assert client.get("/v1/permission-modes/agent:hermes", headers=OWNER).json()["owner_passkey"] is False


def test_every_new_agent_starts_on_always_ask(client, clock, passkey):
    install(client, clock)
    assert policy(client, clock, requested_by=("agent:hermes",)).status_code == 201
    view = client.get("/v1/permission-modes/agent:hermes", headers=OWNER).json()
    assert (view["mode"], view["own"], view["household_default"]) == ("ask", False, "ask")
    assert restart(client, clock, "a0").json()["state"] == "awaiting_approval"  # the rule is ignored
    assert client.get("/v1/approval-policies", headers=OWNER).json()[0]["modes"] == {"agent:hermes": "ask"}
    assert mode(client, "agent:hermes", "auto", reason="trusted helper").status_code == 200
    assert restart(client, clock, "a1").json()["state"] == "succeeded"
    changed = [e for e in audit(client) if e["event"] == "permission.mode.changed"]
    d = changed[-1]["data"]
    assert (d["from"], d["to"], d["direction"], d["reason"]) == ("ask", "auto", "loosen", "trusted helper")


def test_remember_uses_rules_and_waits_for_the_rest(client, clock, passkey):
    install(client, clock)
    mode(client, "agent:hermes", "remember")
    assert restart(client, clock, "r0").json()["state"] == "awaiting_approval"
    policy(client, clock, requested_by=("agent:hermes",))
    assert restart(client, clock, "r1").json()["state"] == "succeeded"


def test_locked_refuses_at_once_and_cancels_what_waits(client, clock, passkey):
    install(client, clock)
    pending = restart(client, clock, "l0").json()
    assert pending["state"] == "awaiting_approval"
    assert mode(client, "agent:hermes", "locked").status_code == 200
    assert client.get(f"/v1/actions/{pending['id']}", headers=OWNER).json()["state"] == "cancelled"
    r = restart(client, clock, "l1")
    assert r.status_code == 403 and r.json()["reason"] == "mode_locked"


def test_headless_refuses_what_no_rule_covers(client, clock, passkey):
    install(client, clock)
    assert mode(client, "agent:hermes", "headless").status_code == 200
    r = restart(client, clock, "h0")
    assert r.status_code == 403 and r.json()["reason"] == "no_rule"  # never queued
    assert client.app.state.repo.get_by_idempotency_key("h0") is None
    policy(client, clock, requested_by=("agent:hermes",))
    assert restart(client, clock, "h1").json()["state"] == "succeeded"


def test_bypass_is_not_built_yet(client, passkey):
    r = mode(client, "agent:hermes", "bypass")
    assert r.status_code == 422 and r.json()["reason"] == "bypass_not_built"


def test_a_teen_cannot_loosen_their_own_agent(client):
    modes = client.app.state.permissions.modes
    modes.owned_by = lambda uid: {"agent:teenbot"} if uid == "u_teen" else set()
    modes.owner_passkey = lambda: True
    teen = Principal("u_teen", "person", "teen")
    assert modes.check_change(teen, "agent:teenbot", "locked", "u_teen") == "tighten"
    with pytest.raises(ApiError) as exc:
        modes.check_change(teen, "agent:teenbot", "auto", "u_teen")
    assert exc.value.status == 403
    with pytest.raises(ApiError):  # and no say at all over someone else's agent
        modes.check_change(teen, "agent:hermes", "locked", "u_teen")


def test_nobody_loosens_their_own_requests(client, passkey):
    r = mode(client, "person:owner", "auto")
    assert r.status_code == 403 and "your own requests" in r.json()["message"]
    assert mode(client, "person:adult", "auto", headers=ADULT).status_code == 403
    assert mode(client, "person:adult", "auto").status_code == 200  # a different approver sets it


def test_an_agent_reads_only_its_own_mode_and_never_changes_one(client, passkey):
    mode(client, "agent:other", "locked")
    assert client.get("/v1/permission-modes/agent:hermes", headers=AGENT).status_code == 200
    assert client.get("/v1/permission-modes/agent:other", headers=AGENT).status_code == 403
    listed = {m["principal"] for m in client.get("/v1/permission-modes", headers=AGENT).json()}
    assert listed == {"*"}
    assert mode(client, "agent:hermes", "locked", headers=AGENT).status_code == 403
    assert mode(client, "agent:hermes", "auto", headers=AGENT).status_code == 403


def test_loosening_needs_a_fresh_passkey_and_tightening_does_not(client, passkey):
    client.app.state.identity.passkeys_active = lambda: True
    r = mode(client, "agent:hermes", "auto")
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    assert mode(client, "agent:hermes", "locked").status_code == 200
    r = client.put("/v1/permission-modes", headers=OWNER, json={"mode": "auto"})
    assert r.status_code == 401


def test_live_rules_keep_firing_after_the_upgrade(client, clock, passkey):
    install(client, clock)
    svc = client.app.state.automation
    svc.repo.add_policy(id="pol_old", name=None, per_day=5, window_id=None, expires_at=clock.now + timedelta(days=5),
                        allow={"types": ["app.restart"], "requested_by": ["agent:hermes"], "params": {}},
                        created_by={"id": "owner"}, created_at=clock.now)
    svc.policies.adopt_unbound()
    modes = client.app.state.permissions.modes
    with svc.repo.db.session.begin() as s:  # a box upgraded from before modes: no marker yet
        from sqlalchemy import delete
        from onemind_core.permissions.modes import MIGRATED, ModeRow
        s.execute(delete(ModeRow).where(ModeRow.principal == MIGRATED))
    live = {w for p in svc.repo.list_policies() for w in p["allow"]["requested_by"]}
    assert modes.migrate(lambda: live) == ["agent:hermes"]
    assert modes.migrate(lambda: live) == []  # once
    assert restart(client, clock, "u0").json()["state"] == "succeeded"
    migrated = [e for e in audit(client) if e["event"] == "permission.mode.migrated"]
    assert migrated and migrated[-1]["data"]["principals"] == ["agent:hermes"]
    _ = iso
