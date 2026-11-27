# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 8: decide() + the hard floor, deny rules, the clock guard (design §3.4, §3.5.2).

Each test fails without the change: before it there was no single ordered decision, no deny rules,
no clock check, and a standing approval still fired with the floor's own settings switched off.
"""

from __future__ import annotations

import itertools
import json
from datetime import timedelta

import pytest
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from conftest import ADULT, AGENT, OWNER, action_body
from onemind_core.automation.registry import RISKS
from onemind_core.permissions.decide import MODES, Facts, decide
from onemind_core.permissions.floor import GRANTS_ACCESS
from test_automation import auto_settings, client, install, policy  # noqa: F401  (fixtures)

KINDS = ("agent", "plugin", "automation", "person")


def facts(**kw) -> Facts:
    base = {"principal": "agent:x", "kind": "agent", "action_type": "app.restart", "risk": "write",
            "mode": "auto", "rule": "policy:pol_1@1"}
    return Facts(**{**base, **kw})


# ---- the table: every risk x physical x taint x exposure x mode cell -------------------------------
@pytest.mark.parametrize("risk, physical, tainted, exposed, mode",
                         list(itertools.product((*RISKS, None, "bogus"), (False, True), (False, True), (False, True), MODES)))
def test_every_cell(risk, physical, tainted, exposed, mode):
    d = decide(facts(risk=risk, physical=physical, tainted=tainted or exposed, exposed=exposed, mode=mode))
    floor = physical or tainted or exposed or risk in ("destructive", "actuate")
    if mode == "locked":
        assert (d.outcome, d.step) == ("refuse", 2)
    elif risk not in RISKS:
        assert (d.outcome, d.reason) == ("refuse", "unknown_risk")
    elif floor:
        assert d.outcome == ("refuse" if mode == "headless" else "wait") and d.step == 6
    elif mode == "ask":
        assert d.outcome == "wait" and d.step == 8
    else:  # remember, auto, headless, bypass with a live rule
        assert (d.outcome, d.via) == ("approve", "policy:pol_1@1")


@pytest.mark.parametrize("mode", MODES)
def test_without_a_rule_only_headless_refuses(mode):
    d = decide(facts(rule=None, mode=mode))
    assert d.outcome == {"locked": "refuse", "headless": "refuse"}.get(mode, "wait")


@pytest.mark.parametrize("action_type", sorted(GRANTS_ACCESS))
def test_anything_that_grants_access_waits_for_a_person(action_type):
    d = decide(facts(action_type=action_type))
    assert (d.outcome, d.reason) == ("wait", "floor:grants_access")


@pytest.mark.parametrize("fact, reason", [("network_paths", "grants_access"), ("sealed", "secrets")])
def test_network_paths_and_secrets_are_floor_items(fact, reason):
    assert decide(facts(**{fact: True})).reason == f"floor:{reason}"


def test_licence_radio_and_smb_are_floor_items():
    assert decide(facts(licence_green=False)).reason == "floor:licence"
    assert decide(facts(action_type="radio.message.transmit")).reason == "floor:radio_transmit"
    assert decide(facts(action_type="files.share.create")).reason == "floor:smb_share"
    assert decide(facts(action_type="files.share.create", kind="person")).outcome == "approve"


@pytest.mark.parametrize("fact, reason", [("clock_trusted", "clock_untrusted"), ("floor_settings_on", "floor_settings_off"),
                                          ("owner_passkey", "no_owner_passkey")])
def test_untrusted_time_floor_settings_or_no_passkey_turn_every_mode_into_always_ask(fact, reason):
    for mode in ("remember", "auto", "headless", "bypass"):
        d = decide(facts(mode=mode, **{fact: False}))
        assert (d.outcome, d.reason, d.step) == ("wait", reason, 7)


# ---- properties ---------------------------------------------------------------------------------
cells = st.builds(
    Facts, principal=st.just("agent:x"), kind=st.sampled_from(KINDS),
    action_type=st.sampled_from(["app.restart", "system.check", "node.join", "files.share.create", "radio.x.transmit"]),
    risk=st.sampled_from((*RISKS, None)), mode=st.sampled_from(MODES + ("weird",)),
    physical=st.booleans(), tainted=st.booleans(), exposed=st.booleans(), network_paths=st.booleans(),
    sealed=st.booleans(), licence_green=st.booleans(), agents_stopped=st.booleans(), motion_lockout=st.booleans(),
    automation_paused=st.booleans(), deny=st.sampled_from([None, "den_1"]), scope_ok=st.booleans(),
    clock_trusted=st.booleans(), floor_settings_on=st.booleans(), owner_passkey=st.booleans(),
    rule=st.sampled_from([None, "policy:pol_1@1"]))


@hsettings(max_examples=3000, deadline=None)
@given(cells)
def test_no_mode_ever_approves_a_floor_item_and_deny_beats_allow(f):
    d = decide(f)
    if d.outcome == "approve":
        assert not (f.physical or f.tainted or f.exposed or f.network_paths or f.sealed or not f.licence_green)
        assert f.risk in ("read", "write", "sensitive") and f.deny is None and f.rule
        assert f.mode in ("remember", "auto", "headless", "bypass") and f.clock_trusted and f.floor_settings_on and f.owner_passkey
    if f.deny is not None:
        assert d.outcome == "refuse"
    if f.agents_stopped and f.kind in ("agent", "plugin"):
        assert (d.outcome, d.reason) == ("refuse", "agents_stopped")


# ---- the engine on the real filing paths --------------------------------------------------------
def audit(client) -> list[dict]:
    return [json.loads(x) for x in client.app.state.settings.audit_path.read_text().splitlines()]


def restart(client, clock, key, headers=AGENT):
    return client.post("/v1/actions", json=action_body(clock, "whoami", "app.restart", key=key), headers=headers)


def test_a_deny_rule_beats_a_standing_approval_until_the_owner_removes_it(client, clock):
    install(client, clock)
    assert policy(client, clock, requested_by=("agent:hermes",)).status_code == 201
    assert restart(client, clock, "d0").json()["state"] == "succeeded"
    r = client.post("/v1/approval-denies", headers=OWNER,
                    json={"principal": "agent:hermes", "action_type": "app.restart", "reason": "too noisy"})
    assert r.status_code == 201, r.text
    deny = r.json()
    r = restart(client, clock, "d1")
    assert r.status_code == 403 and r.json()["reason"] == "denied_by_rule"
    refused = [e for e in audit(client) if e["event"] == "authz.denied" and e["data"].get("reason") == "denied_by_rule"]
    assert refused and refused[-1]["data"]["deny_id"] == deny["id"] and refused[-1]["data"]["step"] == 3
    # a tier deny covers every write type
    client.delete(f"/v1/approval-denies/{deny['id']}", headers=OWNER)
    client.post("/v1/approval-denies", headers=OWNER, json={"principal": "agent:hermes", "tier": "T1"})
    assert restart(client, clock, "d2").status_code == 403
    for d in client.get("/v1/approval-denies", headers=OWNER).json():
        assert client.delete(f"/v1/approval-denies/{d['id']}", headers=OWNER).status_code == 204
    assert restart(client, clock, "d3").json()["state"] == "succeeded"
    assert {"approval.deny.added", "approval.deny.removed"} <= {e["event"] for e in audit(client)}


def test_agents_and_other_people_cannot_manage_deny_rules(client, clock):
    body = {"principal": "agent:hermes", "tier": "T3"}
    assert client.post("/v1/approval-denies", headers=AGENT, json=body).status_code == 403
    assert client.get("/v1/approval-denies", headers=AGENT).status_code == 403
    # an adult owns no agent token here, so has no say over hermes
    assert client.post("/v1/approval-denies", headers=ADULT, json=body).status_code == 403
    d = client.post("/v1/approval-denies", headers=OWNER, json=body).json()
    assert client.delete(f"/v1/approval-denies/{d['id']}", headers=ADULT).status_code == 403
    assert client.get("/v1/approval-denies", headers=ADULT).json() == []
    bad = [{"principal": "agent:hermes"}, {"principal": "agent:hermes", "tier": "T1", "action_type": "app.restart"},
           {"principal": "hermes", "tier": "T1"}, {"principal": "person:owner", "tier": "T1"}]
    for b in bad:
        assert client.post("/v1/approval-denies", headers=OWNER, json=b).status_code == 422, b


def test_a_clock_set_back_refuses_automatic_approval(client, clock):
    install(client, clock)
    policy(client, clock, requested_by=("agent:hermes",))
    assert restart(client, clock, "c0").json()["state"] == "succeeded"
    clock.advance(-3600)  # an hour behind the latest time the gateway recorded
    assert restart(client, clock, "c1").json()["state"] == "awaiting_approval"
    assert any(e["event"] == "clock.untrusted" and e["data"]["reason"] == "clock_behind" for e in audit(client))
    clock.advance(3600 + 60)
    assert restart(client, clock, "c2").json()["state"] == "succeeded"
    assert any(e["event"] == "clock.trusted" for e in audit(client))


def test_an_unsynchronised_clock_refuses_automatic_approval(client, clock, tmp_path):
    install(client, clock)
    policy(client, clock, requested_by=("agent:hermes",))
    guard = client.app.state.permissions.clock_guard
    guard.sync_file = str(tmp_path / "synchronized")
    assert restart(client, clock, "s0").json()["state"] == "awaiting_approval"
    (tmp_path / "synchronized").write_text("")
    assert restart(client, clock, "s1").json()["state"] == "succeeded"


def test_rules_are_off_while_the_floors_own_settings_are_off(client, clock):
    install(client, clock)
    policy(client, clock, requested_by=("agent:hermes",))
    ident = client.app.state.identity
    from dataclasses import replace
    ident.cfg = replace(ident.cfg, require_passkey_approval=False)
    assert restart(client, clock, "f0").json()["state"] == "awaiting_approval"
    ident.cfg = replace(ident.cfg, require_passkey_approval=True, enforce_role_scopes=False)
    assert restart(client, clock, "f1").json()["state"] == "awaiting_approval"
    ident.cfg = replace(ident.cfg, enforce_role_scopes=True)
    assert restart(client, clock, "f2").json()["state"] == "succeeded"


def test_an_automation_cannot_file_while_automation_is_paused(client, clock):
    install(client, clock)
    gw = client.app.state.gateway
    from onemind_core.actions import ActionRequest
    from onemind_core.auth import Principal
    assert client.post("/v1/automation/pause", json={"reason": "x"}, headers=OWNER).status_code == 200
    req = ActionRequest.model_validate(action_body(clock, "whoami", "app.restart", key="p0"))
    from onemind_core.errors import ApiError
    with pytest.raises(ApiError) as exc:
        gw.actions.create(Principal("automation:update-policy", "automation", "automation"), req)
    assert exc.value.status == 403 and exc.value.reason == "automation_paused"


def test_a_request_with_no_known_risk_is_refused_before_it_is_filed(client, clock):
    gw = client.app.state.gateway

    class H:
        def recheck(self, a):
            return None

        def dispatch(self, a):
            return None

    gw.actions.register_handler("test.unknown.kind", H())
    from onemind_core.errors import ApiError
    with pytest.raises(ApiError) as exc:
        gw.actions.file("test.unknown.kind", {}, {"id": "hermes", "kind": "agent"},
                        expires_at=clock.now + timedelta(hours=1), idempotency_key="u0")
    assert exc.value.reason == "unknown_risk"
    assert gw.actions.repo.get_by_idempotency_key("u0") is None


def test_adding_the_same_deny_twice_returns_the_rule_already_there(client):
    body = {"principal": "agent:hermes", "tier": "T3"}
    a = client.post("/v1/approval-denies", headers=OWNER, json=body).json()
    b = client.post("/v1/approval-denies", headers=OWNER, json=body).json()
    assert a["id"] == b["id"] and len(client.get("/v1/approval-denies", headers=OWNER).json()) == 1



def test_a_tier_deny_judges_the_risk_a_feature_derived(client, clock):
    """A write type whose risk_for raises a request to destructive is refused by a T3 deny."""
    from onemind_core.actions import FeatureAction
    from onemind_core.auth import Principal
    from onemind_core.errors import ApiError
    gw = client.app.state.gateway
    if "test.purge.run" not in gw.actions.feature_types:
        gw.actions.register_type("test.purge.run", FeatureAction(
            "write", lambda a, finish: None, frozenset({"person", "agent"}),
            risk_for=lambda p: "destructive" if p.get("all") else "write"))
    client.post("/v1/approval-denies", headers=OWNER, json={"principal": "agent:hermes", "tier": "T3"})
    hermes = Principal("hermes", "agent", "agent")
    out, _ = gw.actions.request_feature(hermes, "test.purge.run", {"all": False}, idempotency_key="pg0",
                                        expires_at=clock.now + timedelta(hours=1))
    assert out["state"] == "awaiting_approval"
    with pytest.raises(ApiError) as exc:
        gw.actions.request_feature(hermes, "test.purge.run", {"all": True}, idempotency_key="pg1",
                                   expires_at=clock.now + timedelta(hours=1))
    assert exc.value.reason == "denied_by_rule"
