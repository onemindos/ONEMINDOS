# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 6: taint in the database, exposed agents, owner-only inputs (gap 16, F-11 = a)."""

from __future__ import annotations

import json

import pytest

from conftest import ADULT, AGENT, OWNER, make_client
from onemind_core.taint import FOREVER, TTL
from test_mcp import call
from test_tainted_input import (  # noqa: F401  (fixtures and helpers)
    agent_removes_whoami, install_whoami, owner_allows_removals, tclient, hostile_apps,
)

INPUTS = "/v1/agents/hermes/inputs"


def audit(client) -> list[dict]:
    return [json.loads(x) for x in client.app.state.settings.audit_path.read_text().splitlines()]


def test_taint_survives_a_restart_and_keeps_its_ttl(settings, clock, executor):
    hostile_apps(settings)
    with make_client(settings, clock, executor) as c:
        install_whoami(c, clock)
        call(c, "get_app", {"app_id": "evil-app"})  # the agent reads a hostile page
        assert c.app.state.gateway.actions.taint.get("hermes") is not None
    clock.advance(60)
    with make_client(settings, clock, executor) as again:
        t = again.app.state.gateway.actions.taint.get("hermes")
        assert t is not None and not t.permanent and any("mcp:get_app" in s for s in t.sources)
        owner_allows_removals(again)
        assert agent_removes_whoami(again, clock, "after-restart").json()["state"] == "awaiting_approval"
    # The TTL runs on across the restart: an hour after the read it is gone, and stays gone.
    clock.advance(TTL.total_seconds())
    with make_client(settings, clock, executor) as third:
        assert third.app.state.gateway.actions.taint.get("hermes") is None
    with make_client(settings, clock, executor) as fourth:
        assert fourth.app.state.gateway.actions.taint.get("hermes") is None
        events = [e["event"] for e in audit(fourth)]
        assert "taint.set" in events


def test_a_declared_input_taints_an_agent_forever_and_no_rule_accepts_it(tclient, clock):
    install_whoami(tclient, clock)
    owner_allows_removals(tclient)
    assert agent_removes_whoami(tclient, clock, "clean").json()["state"] == "succeeded"  # control
    install_whoami(tclient, clock)
    v = tclient.put(INPUTS, json={"external_inputs": ["web", "email"]}, headers=OWNER)
    assert v.status_code == 200, v.text
    assert v.json()["external_inputs"] == ["web", "email"] and v.json()["permanently_tainted"] is True
    r = agent_removes_whoami(tclient, clock, "exposed")  # it has read nothing through the gateway
    assert r.json()["state"] == "awaiting_approval"
    assert "web" in " ".join(r.json()["plan"]["taint"]["sources"])
    t = tclient.app.state.gateway.actions.taint.get("hermes")
    assert t.permanent and t.until == FOREVER
    clock.advance(10 * 86400)  # no expiry, however long it reads nothing
    assert tclient.app.state.gateway.actions.taint.get("hermes").permanent
    assert agent_removes_whoami(tclient, clock, "exposed-later").json()["state"] == "awaiting_approval"
    e = [x for x in audit(tclient) if x["event"] == "agent.inputs.set"]
    assert e and e[-1]["data"]["external_inputs"] == ["web", "email"] and e[-1]["data"]["was"] == []


def test_exposure_survives_a_restart(settings, clock, executor):
    hostile_apps(settings)
    with make_client(settings, clock, executor) as c:
        assert c.put(INPUTS, json={"external_inputs": ["files"]}, headers=OWNER).status_code == 200
    with make_client(settings, clock, executor) as again:
        assert again.get(INPUTS, headers=OWNER).json()["external_inputs"] == ["files"]
        assert again.app.state.gateway.actions.taint.get("hermes").permanent


@pytest.mark.default_exposure
def test_every_agent_and_plugin_is_exposed_by_default_and_people_are_not(tclient):
    ins = tclient.app.state.agent_inputs
    assert ins.inputs("agent:whoami") == ("app",)  # an installed app's agent
    assert ins.inputs("plugin:whoami") == ("plugin",)
    # D-028: any other agent (identity token, MCP client, the v0 token) is exposed until declared
    assert ins.inputs("agent:hermes", "agent") == ("agent",) and ins.inputs("hermes", "agent") == ("agent",)
    assert ins.inputs("hermes") == ("agent",)  # an unknown kind fails closed
    assert ins.inputs("owner", "person") == () and ins.inputs("automation:r1", "automation") == ()
    assert tclient.app.state.gateway.actions.taint.get("hermes", "agent").permanent
    assert tclient.app.state.gateway.actions.taint.get("owner", "person") is None
    v = tclient.get("/v1/agents/agent:whoami/inputs", headers=OWNER).json()
    assert v["exposed"] is True and v["declared"] is False
    assert tclient.app.state.gateway.actions.taint.get("agent:whoami").permanent
    # the owner may declare an app's agent reads nothing outside; that is recorded
    r = tclient.put("/v1/agents/agent:whoami/inputs", json={"external_inputs": []}, headers=OWNER)
    assert r.status_code == 200 and r.json()["exposed"] is False and r.json()["declared"] is True
    assert tclient.app.state.gateway.actions.taint.get("agent:whoami") is None


def test_only_the_owner_changes_what_an_agent_reads(tclient):
    tclient.put(INPUTS, json={"external_inputs": ["web"]}, headers=OWNER)
    # the agent cannot lower its own taint, nor can an adult
    for who in (AGENT, ADULT):
        r = tclient.put(INPUTS, json={"external_inputs": []}, headers=who)
        assert r.status_code == 403, r.text
    assert tclient.get(INPUTS, headers=OWNER).json()["external_inputs"] == ["web"]


def test_bad_inputs_are_refused(tclient):
    for body in ({"external_inputs": ["tv"]}, {"external_inputs": ["web"], "extra": 1}, {}):
        assert tclient.put(INPUTS, json=body, headers=OWNER).status_code == 422
    assert tclient.put("/v1/agents/Bad Name/inputs", json={"external_inputs": []}, headers=OWNER).status_code == 422


def test_accept_injection_risk_is_owner_only_one_write_type_and_not_yet_in_effect(tclient, clock):
    ok = tclient.put(INPUTS, json={"external_inputs": ["web"], "accept_injection_risk": ["app.restart"]}, headers=OWNER)
    assert ok.status_code == 200, ok.text
    v = ok.json()
    assert v["accept_injection_risk"] == ["app.restart"] and v["accept_injection_risk_effective"] is False
    for types, needle in ((["app.install"], "write type"), (["backup.restore"], "write type"),
                          (["nope.nope"], "unknown action type")):
        r = tclient.put(INPUTS, json={"external_inputs": ["web"], "accept_injection_risk": types}, headers=OWNER)
        assert r.status_code == 422 and needle in r.json()["message"], r.text
    r = tclient.put(INPUTS, json={"external_inputs": [], "accept_injection_risk": ["app.restart"]}, headers=OWNER)
    assert r.status_code == 422
    # recording the flag loosens nothing: the exposed agent's request still waits for a person
    install_whoami(tclient, clock)
    owner_allows_removals(tclient)
    assert agent_removes_whoami(tclient, clock, "still-waits").json()["state"] == "awaiting_approval"


@pytest.mark.default_exposure
def test_an_identity_token_agent_and_the_v0_token_are_tainted_until_the_owner_declares_none(tclient, clock):
    # D-028: a token the gateway knows nothing about (hermes here is the v0 agent token) reads outside
    # text on its own, so it is exposed from the first request; declaring "none" is the owner's act.
    install_whoami(tclient, clock)
    owner_allows_removals(tclient)
    t = tclient.app.state.gateway.actions.taint
    assert t.get("hermes", "agent").permanent and t.get("agent:claude-code", "agent").permanent
    assert t.get("plugin:x", "plugin").permanent
    assert t.get("owner", "person") is None and t.get("automation:r1", "automation") is None
    assert agent_removes_whoami(tclient, clock, "default").json()["state"] == "awaiting_approval"
    assert tclient.put(INPUTS, json={"external_inputs": []}, headers=OWNER).status_code == 200
    assert agent_removes_whoami(tclient, clock, "declared-none").json()["state"] == "succeeded"


def test_only_loosening_an_agents_inputs_needs_the_passkey(tclient):
    ident = tclient.app.state.identity
    ident.passkeys_active = lambda: True
    # tightening is L0: adding an input, or none -> web, needs no step-up
    assert tclient.put(INPUTS, json={"external_inputs": ["web"]}, headers=OWNER).status_code == 200
    assert tclient.put(INPUTS, json={"external_inputs": ["web", "email"]}, headers=OWNER).status_code == 200
    # loosening needs it: removing an input, declaring none, accepting a risk
    for body in ({"external_inputs": ["web"]}, {"external_inputs": []},
                 {"external_inputs": ["web", "email"], "accept_injection_risk": ["app.restart"]}):
        r = tclient.put(INPUTS, json=body, headers=OWNER)
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required", (body, r.text)
    assert tclient.get(INPUTS, headers=OWNER).json()["external_inputs"] == ["web", "email"]
    ident.passkeys_active = lambda: False
    ok = {"external_inputs": ["web", "email"], "accept_injection_risk": ["app.restart"]}
    assert tclient.put(INPUTS, json=ok, headers=OWNER).status_code == 200
    ident.passkeys_active = lambda: True
    # removing an accepted risk (same inputs) tightens again
    assert tclient.put(INPUTS, json={"external_inputs": ["web", "email"]}, headers=OWNER).status_code == 200


def test_a_mark_writes_the_database_outside_the_ledger_lock(clock):
    from onemind_core.taint import TaintLedger

    ledger = TaintLedger(clock)
    seen = {}

    class Store:
        def load(self):
            return {}

        def save(self, pid, t):
            seen["locked"] = ledger._lock.locked()

        def delete(self, pid):
            pass

    ledger.attach(Store(), lambda _pid, _kind=None: None)
    ledger.mark("hermes", "mcp:get_app")
    assert seen == {"locked": False}


def test_deleting_an_expired_mark_stays_outside_the_ledger_lock(clock):
    from onemind_core.taint import TaintLedger

    ledger = TaintLedger(clock)
    seen = {}

    class Store:
        def load(self):
            return {}

        def save(self, pid, t):
            pass

        def delete(self, pid):
            seen["locked"] = ledger._lock.locked()

    ledger.attach(Store(), lambda _pid, _kind=None: None)
    ledger.mark("hermes", "mcp:get_app")
    clock.advance(TTL.total_seconds() + 1)
    assert ledger.get("hermes") is None
    assert seen == {"locked": False}


SCOUT = "/v1/agents/scout/inputs"


def test_the_inputs_audit_records_how_presence_was_proved_and_a_removed_app_forgets_its_declaration(tclient):
    assert tclient.put(SCOUT, json={"external_inputs": ["web"]}, headers=OWNER).status_code == 200
    ins = tclient.app.state.agent_inputs
    assert tclient.put(SCOUT, json={"external_inputs": []}, headers=OWNER).status_code == 200  # loosens
    e = [x for x in audit(tclient) if x["event"] == "agent.inputs.set"]
    assert "via" in e[-1]["data"]
    # the app is removed: what the owner declared must not carry over to a new agent with that id
    from onemind_core.agent_principals import AgentPrincipals

    pid = AgentPrincipals.principal_id("scout")
    assert tclient.app.state.actions.agent_forgotten == ins.forget
    assert ins.view(pid)["declared"] is True and ins.view(pid)["external_inputs"] == []
    assert ins.forget(pid) is True and ins.forget(pid) is False
    v = ins.view(pid)
    assert v["declared"] is False and v["exposed"] is True  # back to the fail-closed default
    cleared = [x for x in audit(tclient) if x["event"] == "agent.inputs.cleared"]
    assert cleared and cleared[-1]["data"]["reason"] == "identity_ended"
