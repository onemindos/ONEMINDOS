# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 10: permission modes (design §3.5, §3.5.1; F-7, F-8, fix 6, fix 14).

Each test fails without the change: before it there was no mode, so every rule fired for every
principal, nothing waited for an owner passkey, and nobody could lock an agent or make it headless.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from conftest import ADULT, AGENT, OWNER, action_body, apply_settings_change, make_client
from onemind_core.auth import Principal
from onemind_core.errors import ApiError
from test_agent_principals import APP, bearer, run_action
from test_automation import auto_settings, client, install, iso, policy  # noqa: F401  (fixtures)

pytestmark = pytest.mark.real_mode_defaults


@pytest.fixture
def passkey(monkeypatch):
    """The owner has enrolled a passkey (F-8 met); step-up itself stays off, as for an owner token."""
    from onemind_core.permissions import changes
    monkeypatch.setattr(changes, "owner_has_passkey", lambda app: True)


def restart(client, clock, key, headers=AGENT):
    return client.post("/v1/actions", json=action_body(clock, "whoami", "app.restart", key=key), headers=headers)


def mode(client, who, m, headers=OWNER, **kw):
    path = f"/v1/permission-modes/{who}"
    set_path = "/v1/permission-modes" if who == "default" else path
    r = client.put(set_path, headers=headers, json={"mode": m, **kw})
    if r.status_code == 202:
        apply_settings_change(client, r)
        return client.get(path, headers=headers)
    return r


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
    assert policy(client, clock, requested_by=("agent:hermes",)).status_code == 202
    view = client.get("/v1/permission-modes/agent:hermes", headers=OWNER).json()
    assert (view["mode"], view["own"], view["household_default"]) == ("ask", False, "ask")
    assert restart(client, clock, "a0").json()["state"] == "awaiting_approval"  # the rule is ignored
    assert client.get("/v1/approval-policies", headers=OWNER).json()[0]["modes"] == {"agent:hermes": "ask"}
    assert mode(client, "agent:hermes", "auto", reason="trusted helper").status_code == 200
    assert restart(client, clock, "a1").json()["state"] == "succeeded"
    changed = [e for e in audit(client) if e["event"] == "permission.mode.changed"]
    d = changed[-1]["data"]
    assert (d["from"], d["to"], d["direction"], d["reason"]) == ("ask", "auto", "loosen", "trusted helper")


def test_new_agent_starts_on_ask_in_an_auto_household(client, clock, passkey):
    assert mode(client, "default", "auto").status_code == 200
    assert client.get("/v1/permission-modes/agent:hermes", headers=OWNER).json()["mode"] == "auto"
    name = "agent:newcomer"
    r = client.post("/v1/tokens", headers=OWNER, json={"name": "new agent", "principal": {"kind": "agent", "id": name}})
    assert r.status_code == 201, r.text
    view = client.get(f"/v1/permission-modes/{name}", headers=OWNER).json()
    assert (view["mode"], view["household_default"], view["own"]) == ("ask", "auto", False)


@pytest.fixture(params=["app", "token"])
def replace_agent(client, clock, executor, request):
    """Replace a credential through its public lifecycle under the same display name."""
    if request.param == "app":
        name = f"agent:{APP}"

        def provision(replace=False):
            if replace:
                assert run_action(client, clock, "app.remove", key="replace-remove")["state"] == "succeeded"
            key = "replace-install" if replace else "first-install"
            assert run_action(client, clock, key=key)["state"] == "succeeded"
            return bearer(executor.agents[-1].token)
    else:
        name = "agent:tested-replacement"
        token = None

        def provision(replace=False):
            nonlocal token
            if replace:
                r = client.delete(f"/v1/tokens/{token['id']}", headers=OWNER)
                assert r.status_code == 204, r.text
            r = client.post("/v1/tokens", headers=OWNER,
                            json={"name": "Test agent", "principal": {"kind": "agent", "id": name}})
            assert r.status_code == 201, r.text
            token = r.json()
            return bearer(token["one_time"]["token"])

    first = provision()
    assert client.get("/v1/instance", headers=first).status_code == 200

    def replace():
        second = provision(replace=True)
        assert client.get("/v1/instance", headers=first).status_code == 401
        assert client.get("/v1/instance", headers=second).status_code == 200
        return second

    return name, replace


def test_replacement_agent_starts_on_ask_and_is_exposed(client, passkey, replace_agent):
    name, replace = replace_agent
    mode_path, inputs_path = f"/v1/permission-modes/{name}", f"/v1/agents/{name}/inputs"
    assert mode(client, "default", "auto").json()["mode"] == "auto"
    assert client.get(mode_path, headers=OWNER).json()["mode"] == "auto"
    assert mode(client, name, "headless").json()["mode"] == "headless"
    apply_settings_change(client, client.put(inputs_path, headers=OWNER, json={"external_inputs": []}))
    assert not client.get(inputs_path, headers=OWNER).json()["exposed"]

    headers = replace()
    view = client.get(mode_path, headers=headers).json()
    assert (view["mode"], view["own"], view["household_default"]) == ("ask", False, "auto")
    view = client.get(inputs_path, headers=OWNER).json()
    assert (view["declared"], view["exposed"]) == (False, True)
    assert client.app.state.gateway.actions.taint.get(name, "agent").permanent


def test_queued_settings_cannot_target_a_replacement_with_the_same_visible_state(client, passkey, replace_agent):
    from onemind_core.actions import ApprovalInput

    name, replace = replace_agent
    mode_path, inputs_path = f"/v1/permission-modes/{name}", f"/v1/agents/{name}/inputs"
    mode_request = client.put(mode_path, headers=OWNER, json={"mode": "auto"})
    inputs_request = client.put(inputs_path, headers=OWNER, json={"external_inputs": []})
    assert mode_request.status_code == inputs_request.status_code == 202
    before_mode = client.get(mode_path, headers=OWNER).json()
    before_inputs = client.get(inputs_path, headers=OWNER).json()

    replace()
    assert client.get(mode_path, headers=OWNER).json() == before_mode
    assert client.get(inputs_path, headers=OWNER).json() == before_inputs
    for response in (mode_request, inputs_request):
        action = response.json()
        result = client.app.state.actions.approve(Principal("owner", "person", "owner"), action["id"],
                                                  action["plan_sha256"], extra=ApprovalInput(verification_level=2))
        assert result["state"] == "failed" and "changed" in result["result"]["message"], result
    assert client.get(mode_path, headers=OWNER).json() == before_mode
    assert client.get(inputs_path, headers=OWNER).json() == before_inputs


def test_queued_household_change_only_applies_to_reviewed_identities(client, passkey, replace_agent):
    name, replace = replace_agent
    pending = client.put("/v1/permission-modes", headers=OWNER, json={"mode": "auto"})
    headers = replace()
    apply_settings_change(client, pending)
    view = client.get(f"/v1/permission-modes/{name}", headers=headers).json()
    assert (view["mode"], view["household_default"]) == ("ask", "auto")
    assert client.get("/v1/permission-modes/agent:hermes", headers=OWNER).json()["mode"] == "auto"


@pytest.mark.default_exposure
@pytest.mark.parametrize("legacy_mode", ["auto", "locked"])
def test_legacy_settings_keep_locks_but_do_not_assign_permissions(auto_settings, clock, executor, legacy_mode):
    from sqlalchemy import inspect, text

    with make_client(auto_settings, clock, executor) as c:
        assert run_action(c, clock)["state"] == "succeeded"
        app_name = f"agent:{APP}"
        with c.app.state.gateway.db.engine.begin() as conn:
            for table in ("permissions_modes", "permissions_mode_members", "agents_inputs"):
                if "identity_uid" in {col["name"] for col in inspect(conn).get_columns(table)}:
                    conn.execute(text(f"ALTER TABLE {table} DROP COLUMN identity_uid"))
            conn.execute(text("UPDATE schema_versions SET version = 1 WHERE feature IN ('agents', 'permissions')"))
            conn.execute(text("INSERT INTO permissions_modes (principal, mode, set_at) VALUES "
                              "('agent:hermes', :mode, :now), ('*', :mode, :now), ('__inheritance__', :mode, :now)"),
                         {"mode": legacy_mode, "now": clock()})
            conn.execute(text("INSERT INTO permissions_mode_members (principal) VALUES (:name), ('person:adult')"),
                         {"name": app_name})
            conn.execute(text("INSERT INTO agents_inputs (principal_id, external_inputs, accept_injection_risk, "
                              "updated_at, updated_by) VALUES ('hermes', '[]', '[]', :now, 'owner')"),
                         {"now": clock()})

    with make_client(auto_settings, clock, executor) as reopened:
        expected = "ask" if legacy_mode == "auto" else "locked"
        for name in ("agent:hermes", app_name):
            assert reopened.get(f"/v1/permission-modes/{name}", headers=OWNER).json()["mode"] == expected
        assert reopened.get("/v1/permission-modes/person:adult", headers=OWNER).json()["mode"] == legacy_mode
        inputs = reopened.get("/v1/agents/hermes/inputs", headers=OWNER).json()
        assert not inputs["declared"] and inputs["exposed"]


def test_queued_mode_change_cannot_overwrite_a_new_inherited_lock(client, passkey):
    from onemind_core.actions import ApprovalInput

    path = "/v1/permission-modes/agent:hermes"
    r = client.put(path, headers=OWNER, json={"mode": "auto"})
    assert r.status_code == 202 and r.json()["params"]["before"]["mode"] == "ask"
    assert client.put("/v1/permission-modes", headers=OWNER, json={"mode": "locked"}).status_code == 200
    queued = r.json()
    outcome = client.app.state.actions.approve(Principal("owner", "person", "owner"), queued["id"],
                                                extra=ApprovalInput(verification_level=2))
    assert outcome["state"] == "failed" and "permission mode changed" in outcome["result"]["message"]
    view = client.get(path, headers=OWNER).json()
    assert view["mode"] == "locked" and not view["own"]


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
    r = mode(client, "person:owner", "auto")  # the owner has no mode at all (design 3.5.1)
    assert r.status_code == 422 and r.json()["reason"] == "owner_exempt"
    assert mode(client, "person:adult", "auto", headers=ADULT).status_code == 403
    assert mode(client, "person:adult", "auto").status_code == 200  # a different approver sets it


def test_an_agent_reads_only_its_own_mode_and_never_changes_one(client, passkey):
    r = client.post("/v1/tokens", headers=OWNER,
                    json={"name": "Other agent", "principal": {"kind": "agent", "id": "agent:other"}})
    assert r.status_code == 201, r.text
    assert mode(client, "agent:other", "locked").status_code == 200
    assert client.get("/v1/permission-modes/agent:hermes", headers=AGENT).status_code == 200
    assert client.get("/v1/permission-modes/agent:other", headers=AGENT).status_code == 403
    listed = {m["principal"] for m in client.get("/v1/permission-modes", headers=AGENT).json()}
    assert listed == {"*"}
    assert mode(client, "agent:hermes", "locked", headers=AGENT).status_code == 403
    assert mode(client, "agent:hermes", "auto", headers=AGENT).status_code == 403


def test_loosening_needs_a_fresh_passkey_and_tightening_does_not(client, passkey):
    client.app.state.identity.passkeys_active = lambda: True
    r = client.put("/v1/permission-modes/agent:hermes", headers=OWNER, json={"mode": "auto"})
    assert r.status_code == 202 and r.json()["state"] == "awaiting_approval"
    refusal = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert refusal.status_code in (401, 409) and refusal.json()["reason"] in ("step_up_required", "needs_proven_key")
    assert mode(client, "agent:hermes", "locked").status_code == 200
    r = client.put("/v1/permission-modes", headers=OWNER, json={"mode": "auto"})
    assert r.status_code == 202 and r.json()["state"] == "awaiting_approval"


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
    live = {w: bound["uid"] for p in svc.repo.list_policies() for w, bound in p["principals"].items()}
    assert modes.migrate(lambda: live) == ["agent:hermes"]
    assert modes.migrate(lambda: live) == []  # once
    assert restart(client, clock, "u0").json()["state"] == "succeeded"
    migrated = [e for e in audit(client) if e["event"] == "permission.mode.migrated"]
    assert migrated and migrated[-1]["data"]["principals"] == ["agent:hermes"]
    _ = iso


def test_the_owner_cannot_lock_themselves_out(client, clock, passkey):
    """Opus review on #1203: Locked on person:owner used to answer 200, then every owner request got
    403 mode_locked and setting it back got 403 "your own requests": only a database edit undid it."""
    install(client, clock)
    for m in ("locked", "headless", "ask"):
        r = mode(client, "person:owner", m)
        assert r.status_code == 422 and r.json()["reason"] == "owner_exempt", (m, r.text)
    assert client.get("/v1/permission-modes/person:owner", headers=OWNER).json()["own"] is False
    r = restart(client, clock, "o0", headers=OWNER)
    assert r.status_code in (200, 201) and r.json()["state"] != "refused", r.text
    assert client.get("/v1/permission-modes", headers=OWNER).status_code == 200  # still in charge


@pytest.mark.parametrize("default", ["locked", "headless"])
def test_a_locked_or_headless_household_default_never_touches_the_owner(client, clock, passkey, default):
    install(client, clock)
    assert mode(client, "default", default).status_code == 200
    r = restart(client, clock, "h0", headers=OWNER)
    assert r.status_code in (200, 201), r.text  # the owner's own request runs as before modes
    r = restart(client, clock, "h1")  # an agent on the default is refused (locked; headless with no rule)
    assert r.status_code == 403
    # and the owner can always put the default back
    assert mode(client, "default", "ask").status_code == 200


def test_the_migration_lists_wildcard_rules_it_could_not_move(client, clock, passkey):
    svc = client.app.state.automation
    svc.repo.add_policy(id="pol_wild", name=None, per_day=5, window_id=None, expires_at=clock.now + timedelta(days=5),
                        allow={"types": ["backup.run"], "requested_by": ["person:*"], "params": {}},
                        created_by={"id": "owner"}, created_at=clock.now)
    modes = client.app.state.permissions.modes
    with svc.repo.db.session.begin() as s:  # a box upgraded from before modes: no marker yet
        from sqlalchemy import delete
        from onemind_core.permissions.modes import MIGRATED, ModeRow
        s.execute(delete(ModeRow).where(ModeRow.principal == MIGRATED))
    assert modes.migrate(dict, lambda: ["pol_wild"]) == []
    migrated = [e for e in audit(client) if e["event"] == "permission.mode.migrated"]
    assert migrated[-1]["data"]["wildcard_rules_not_moved"] == ["pol_wild"]
