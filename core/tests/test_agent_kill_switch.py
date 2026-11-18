# SPDX-License-Identifier: Apache-2.0
"""CORE-SEC-6 (#159): the agent kill switch stops every AI agent, for every agent principal kind.

Kinds covered: the static agent token (tokens file), an app's agent principal issued at install
(§11.2), and an identity-issued agent token (§12.6). People keep working; only the owner can turn
it on or off; every change is audited; it survives a gateway restart.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER, action_body, make_client
from onemind_core.app import create_app
from onemind_core.audit import verify
from test_identity import csrf, id_settings, setup_owner

PATH = "/v1/agents/kill-switch"


def audit(settings) -> list[dict]:
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


def stop(client, on: bool, headers=OWNER, reason: str | None = "testing"):
    return client.put(PATH, json={"on": on, "reason": reason}, headers=headers)


def refused(r) -> bool:
    return r.status_code == 403 and r.json().get("reason") == "agents_stopped"


def app_agent(client, clock, executor) -> dict:
    """Install the fixture app with spec.agent and return its agent principal's bearer header."""
    r = client.post("/v1/actions", json=action_body(clock, app_id="hermes-like"), headers=OWNER)
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    return {"Authorization": f"Bearer {executor.agents[-1].token}"}


def test_off_by_default_and_any_person_can_read_it(client):
    for h in (OWNER, ADULT, GUEST, AGENT):
        r = client.get(PATH, headers=h)
        assert r.status_code == 200 and r.json()["on"] is False and r.json()["changed_by"] is None


def test_on_refuses_static_and_app_agents_everywhere_people_keep_working(client, clock, executor, settings):
    app_h = app_agent(client, clock, executor)
    assert client.get("/v1/apps", headers=app_h).status_code == 200
    r = stop(client, True, reason="agent misbehaving")
    assert r.status_code == 200 and r.json()["on"] is True and r.json()["reason"] == "agent misbehaving"
    assert r.json()["changed_by"] == {"id": "owner", "kind": "person", "role": "owner"}
    for h in (AGENT, app_h):
        assert refused(client.get("/v1/apps", headers=h))
        assert refused(client.get(PATH, headers=h))  # even reading the switch
        assert refused(client.post("/v1/actions", json=action_body(clock, app_id="whoami", key="x"), headers=h))
        assert refused(client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=h))
        assert refused(stop(client, False, headers=h))  # an agent can never turn it off
    assert client.get(PATH, headers=OWNER).json()["on"] is True
    for h in (OWNER, ADULT, GUEST):  # people are not agents
        assert client.get("/v1/apps", headers=h).status_code == 200
    assert client.post("/v1/actions", json=action_body(clock, app_id="whoami", key="o"), headers=OWNER).status_code == 201
    r = stop(client, False, reason="fixed")
    assert r.json()["on"] is False
    assert client.get("/v1/apps", headers=AGENT).status_code == 200
    assert client.get("/v1/apps", headers=app_h).status_code == 200
    events = [e["event"] for e in audit(settings)]
    assert "agents.stopped" in events and "agents.resumed" in events
    assert verify(settings.audit_path)[0]


def test_only_the_owner_changes_it_and_refusals_are_audited(client, settings):
    for h in (ADULT, GUEST, AGENT):
        r = stop(client, True, headers=h)
        assert r.status_code == 403 and r.json().get("reason") != "agents_stopped"
    assert client.get(PATH, headers=OWNER).json()["on"] is False
    denied = [e for e in audit(settings) if e["event"] == "authz.denied" and "kill switch" in e["data"].get("attempted", "")]
    assert {e["principal"]["id"] for e in denied} >= {"hermes"}
    assert client.put(PATH, json={"on": "maybe"}, headers=OWNER).status_code == 422
    assert client.put(PATH, json={"on": True, "extra": 1}, headers=OWNER).status_code == 422
    assert client.put(PATH, json={"on": True, "reason": "x" * 501}, headers=OWNER).status_code == 422
    assert client.get(PATH, headers=OWNER).json()["on"] is False


def test_change_is_an_audited_event(client, settings):
    stop(client, True, reason="looking into it")
    line = next(e for e in audit(settings) if e["event"] == "agents.stopped")
    assert line["principal"]["id"] == "owner"
    assert line["data"]["payload"]["reason"] == "looking into it" and line["data"]["severity"] == "warning"
    assert line["data"]["resource"] == {"kind": "agents", "id": "all"}
    stop(client, False, reason=None)
    assert [e["event"] for e in audit(settings) if e["event"].startswith("agents.")][-1] == "agents.resumed"


def test_an_agents_earlier_request_cannot_be_approved_while_stopped(client, clock):
    r = client.post("/v1/actions", json=action_body(clock, app_id="whoami", key="before"), headers=AGENT)
    assert r.status_code == 201
    aid = r.json()["id"]
    mine = client.post("/v1/actions", json=action_body(clock, app_id="uptime-kuma", key="own"), headers=OWNER).json()["id"]
    stop(client, True)
    assert refused(client.post(f"/v1/actions/{aid}/approve", headers=OWNER))
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert client.post(f"/v1/actions/{mine}/approve", headers=OWNER).status_code == 200  # a person's request still works
    stop(client, False)
    assert client.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()["state"] == "succeeded"


def test_survives_a_gateway_restart(settings, clock, executor):
    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        assert stop(c, True).status_code == 200
    with make_client(settings, clock) as c:
        assert c.get(PATH, headers=OWNER).json()["on"] is True
        assert refused(c.get("/v1/apps", headers=AGENT))
        stop(c, False)
    with make_client(settings, clock) as c:
        assert c.get("/v1/apps", headers=AGENT).status_code == 200


def test_refusals_are_audited_at_most_once_a_minute(client, clock, settings):
    stop(client, True)
    for _ in range(3):
        assert refused(client.get("/v1/nodes", headers=AGENT))
    lines = [e for e in audit(settings) if e["event"] == "agents.refused"]
    assert len(lines) == 1 and lines[0]["data"]["path"] == "/v1/nodes" and lines[0]["principal"]["id"] == "hermes"
    clock.advance(61)
    assert refused(client.get("/v1/apps", headers=AGENT))
    lines = [e for e in audit(settings) if e["event"] == "agents.refused"]
    assert len(lines) == 2 and lines[1]["data"]["suppressed_since_last"] == 2


def test_identity_issued_agent_token_is_refused(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as idc:
        setup_owner(idc)
        r = idc.post("/v1/tokens", json={"name": "hermes", "principal": {"kind": "agent", "id": "agent:hermes"}},
                     headers=csrf(idc))
        h = {"Authorization": "Bearer " + r.json()["one_time"]["token"]}
        assert idc.get("/v1/nodes", headers=h).status_code == 200
        r = idc.put(PATH, json={"on": True}, headers=csrf(idc))  # the owner's session
        assert r.status_code == 200 and r.json()["on"] is True
        assert refused(idc.get("/v1/nodes", headers=h))
        assert idc.get("/v1/nodes").status_code == 200  # the owner's session still works
