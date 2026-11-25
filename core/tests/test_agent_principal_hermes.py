# SPDX-License-Identifier: Apache-2.0
"""AIG-03 (#167): Hermes as a gateway agent principal: budget, cancel, and never approving."""

from datetime import timedelta

from fastapi.testclient import TestClient

from conftest import AGENT, OWNER, action_body, make_client
from onemind_core.app import create_app
from test_identity import csrf, idc, setup_owner  # noqa: F401  (idc is a fixture)

HERMES = "hermes"  # the static-file agent principal's id in the test world


def file_actions(client, clock, n, headers=AGENT):
    return [client.post("/v1/actions", json=action_body(clock, key=f"k{i}"), headers=headers) for i in range(n)]


def test_hermes_requests_an_action_and_cannot_approve_it(client, clock):
    r = client.post("/v1/actions", json=action_body(clock), headers=AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    aid = r.json()["id"]
    assert client.post(f"/v1/actions/{aid}/approve", headers=AGENT).status_code == 403
    assert client.post(f"/v1/actions/{aid}/deny", headers=AGENT).status_code == 403
    assert client.get(f"/v1/actions/{aid}", headers=AGENT).json()["state"] == "awaiting_approval"


def test_approval_is_bound_to_the_exact_plan_hermes_proposed(client, clock):
    a = client.post("/v1/actions", json=action_body(clock), headers=AGENT).json()
    r = client.post(f"/v1/actions/{aid_of(a)}/approve", json={"plan_sha256": "0" * 64}, headers={**OWNER, "OneMind-API-Version": "1"})
    assert r.status_code == 409  # a plan the owner did not read is never accepted
    assert client.get(f"/v1/actions/{aid_of(a)}", headers=OWNER).json()["state"] == "awaiting_approval"
    ok = client.post(f"/v1/actions/{aid_of(a)}/approve", json={"plan_sha256": a["plan_sha256"]},
                     headers={**OWNER, "OneMind-API-Version": "1"})
    assert ok.status_code == 200


def aid_of(a):
    return a["id"]


def test_budget_refuses_requests_past_the_daily_limit_and_resets_after_24h(client, clock):
    b = client.put(f"/v1/agents/{HERMES}/budget", json={"budget_per_day": 2}, headers=OWNER)
    assert b.status_code == 200 and b.json()["budget_per_day"] == 2
    codes = [r.status_code for r in file_actions(client, clock, 3)]
    assert codes == [201, 201, 429]
    # an idempotent replay of a request already filed is not a new request
    assert client.post("/v1/actions", json=action_body(clock, key="k0"), headers=AGENT).status_code == 200
    assert client.get(f"/v1/agents/{HERMES}", headers=OWNER).json()["used_24h"] == 2
    clock.advance(25 * 3600)
    assert client.post("/v1/actions", json=action_body(clock, key="late"), headers=AGENT).status_code == 201


def test_budget_does_not_limit_the_owner(client, clock):
    client.put(f"/v1/agents/{HERMES}/budget", json={"budget_per_day": 0}, headers=OWNER)
    assert client.post("/v1/actions", json=action_body(clock), headers=AGENT).status_code == 429
    assert client.post("/v1/actions", json=action_body(clock, key="o"), headers=OWNER).status_code == 201


def test_cancel_stops_requests_and_withdraws_what_is_waiting(client, clock, settings):
    first = file_actions(client, clock, 2)
    ids = [r.json()["id"] for r in first]
    r = client.post(f"/v1/agents/{HERMES}/cancel", headers=OWNER)
    assert r.status_code == 200 and r.json()["requests_cancelled"] == 2 and r.json()["cancelled"] is True
    for i in ids:
        assert client.get(f"/v1/actions/{i}", headers=OWNER).json()["state"] == "cancelled"
    refused = client.post("/v1/actions", json=action_body(clock, key="more"), headers=AGENT)
    assert refused.status_code == 403 and refused.json()["reason"] == "agent_cancelled"
    lines = settings.audit_path.read_text()
    assert "agent.cancelled" in lines and "agent_cancelled" in lines
    assert client.post(f"/v1/agents/{HERMES}/resume", headers=OWNER).json()["cancelled"] is False
    assert client.post("/v1/actions", json=action_body(clock, key="again"), headers=AGENT).status_code == 201


def test_cancel_revokes_the_agents_identity_tokens(idc, clock):
    setup_owner(idc)
    tok = idc.post("/v1/tokens", json={"name": "hermes", "principal": {"kind": "agent", "id": "agent:hermes"},
                                       "scopes": ["instance:read", "actions:request", "actions:read"]},
                   headers=csrf(idc)).json()["one_time"]["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert idc.get("/v1/me", headers=h).status_code == 200
    assert idc.post("/v1/actions", json=action_body(clock), headers=h).status_code == 201
    r = idc.post("/v1/agents/agent:hermes/cancel", headers=csrf(idc))
    assert r.status_code == 200 and r.json()["tokens_revoked"] == 1 and r.json()["requests_cancelled"] == 1
    assert idc.get("/v1/me", headers=h).status_code == 401


def test_only_the_owner_runs_the_agent_controls(client, clock):
    file_actions(client, clock, 1)
    for method, path, body in (("GET", "/v1/agents", None), ("GET", f"/v1/agents/{HERMES}", None),
                               ("PUT", f"/v1/agents/{HERMES}/budget", {"budget_per_day": 999}),
                               ("POST", f"/v1/agents/{HERMES}/cancel", None), ("POST", f"/v1/agents/{HERMES}/resume", None)):
        r = client.request(method, path, json=body, headers=AGENT)
        assert r.status_code == 403, (method, path)
    listing = client.get("/v1/agents", headers=OWNER).json()
    assert [a["id"] for a in listing] == [HERMES] and listing[0]["pending_approvals"] == 1


def test_bad_agent_id_and_budget_are_422(client):
    assert client.get("/v1/agents/BAD%20ID", headers=OWNER).status_code == 422
    assert client.put(f"/v1/agents/{HERMES}/budget", json={"budget_per_day": -1}, headers=OWNER).status_code == 422
