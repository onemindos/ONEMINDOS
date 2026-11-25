# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 6: taint in the database, exposed agents, owner-only inputs (gap 16, F-11 = a)."""

from __future__ import annotations

import json

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


def test_apps_and_plugins_are_exposed_by_default_and_other_agents_are_not(tclient):
    ins = tclient.app.state.agent_inputs
    assert ins.inputs("agent:whoami") == ("app",)  # an installed app's agent
    assert ins.inputs("plugin:whoami") == ("plugin",)
    assert ins.inputs("agent:hermes") == () and ins.inputs("hermes") == ()
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
