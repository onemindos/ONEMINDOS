# SPDX-License-Identifier: Apache-2.0
"""D-028: releasing either safety switch requires an action-bound L2 approval."""

import pytest

from conftest import AGENT, OWNER, action_body, enroll_agent
from onemind_core.natsconf import new_user_key
from test_approve_remember import box  # noqa: F401 (pytest fixture)
from test_identity import csrf


@pytest.mark.real_mode_defaults
def test_resume_before_passkey_enrollment_leaves_agents_stopped(client):
    path = "/v1/agents/kill-switch"
    assert client.put(path, headers=OWNER, json={"on": True}).status_code == 200
    response = client.put(path, headers=OWNER, json={"on": False})
    assert response.status_code == 409 and response.json()["reason"] == "no_owner_passkey"
    assert client.get(path, headers=OWNER).json()["on"] is True


@pytest.mark.parametrize(("path", "flag", "action_type"), [
    ("/v1/agents/kill-switch", "on", "policy.agents.resume"),
    ("/v1/physical/lockout", "locked", "policy.motion.unlock"),
])
def test_safety_switch_release_checks_action_bound_l2_and_a_fresh_switch_state(box, monkeypatch, path, flag, action_type):
    client, key = box
    headers = csrf(client)

    def request_release():
        response = client.put(path, headers=headers, json={flag: False})
        assert response.status_code == 202, response.text
        action = response.json()
        assert action["type"] == action_type and action["state"] == "awaiting_approval"
        assert client.get(path, headers=headers).json()[flag] is True
        return f"/v1/actions/{action['id']}"

    def signed(url):
        options = client.post(f"{url}/approve-options", headers=headers)
        assert options.status_code == 200, options.text
        return {"webauthn": key.assert_(options.json()["challenge"])}

    assert client.put(path, headers=headers, json={flag: True}).status_code == 200
    first = request_release()
    l1 = client.post(f"{first}/approve", headers=headers, json=signed(first))
    assert l1.status_code == 409 and l1.json()["reason"] == "needs_proven_key", l1.text
    fresh_session = client.post(f"{first}/approve", headers=headers)
    assert fresh_session.status_code in (401, 409), fresh_session.text
    assert client.get(path, headers=headers).json()[flag] is True

    assert client.put(path, headers=headers, json={flag: True}).status_code == 200
    second = request_release()
    monkeypatch.setattr(client.app.state.identity, "passkey_verification_level", lambda _credential: 2)
    wrong = client.post(f"{second}/approve", headers=headers, json=signed(first))
    assert wrong.status_code == 401 and "another action" in wrong.json()["message"], wrong.text
    stale = client.post(f"{first}/approve", headers=headers, json=signed(first))
    assert stale.status_code == 200 and stale.json()["state"] == "failed", stale.text
    assert client.get(path, headers=headers).json()[flag] is True
    approved = client.post(f"{second}/approve", headers=headers, json=signed(second))
    assert approved.status_code == 200 and approved.json()["state"] == "succeeded", approved.text
    assert client.get(path, headers=headers).json()[flag] is False


@pytest.mark.real_mode_defaults
@pytest.mark.parametrize("kind", ["resume", "budget", "nats_key"])
def test_agent_permission_increase_needs_action_bound_l2(box, clock, monkeypatch, kind):
    client, key = box
    headers = csrf(client)
    path = "/v1/agents/hermes"

    if kind == "resume":
        assert client.post(f"{path}/cancel", headers=headers).status_code == 200
        method, url, body = "POST", f"{path}/resume", None
        field, before, after = "cancelled", True, False
        action_type = "policy.agent.resume"
    elif kind == "budget":
        assert client.put(f"{path}/budget", headers=headers, json={"budget_per_day": 0}).status_code == 200
        method, url, body = "PUT", f"{path}/budget", {"budget_per_day": 1}
        field, before, after = "budget_per_day", 0, 1
        action_type = "policy.agent.budget.raise"
    else:
        enroll_agent(client, "agent:aaa", headers)
        path = "/v1/agents/agent:aaa/nats-key"
        _, public_key = new_user_key()
        method, url, body = "PUT", path, {"nkey": public_key}
        field, before, after = "nkey", None, public_key
        action_type = "policy.agent.nats_key.set"

    def queue():
        r = client.request(method, url, headers=headers, json=body)
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == action_type and a["state"] == "awaiting_approval"
        assert a["params"]["agent"] == path.split("/")[3] and a["plan"]["params"] == a["params"]
        assert client.get(path, headers=headers).json()[field] == before
        return f"/v1/actions/{a['id']}"

    def signed(url):
        options = client.post(f"{url}/approve-options", headers=headers)
        assert options.status_code == 200, options.text
        return {"webauthn": key.assert_(options.json()["challenge"])}

    first, second = queue(), queue()
    unsigned = client.post(f"{first}/approve", headers=headers)
    assert unsigned.status_code == 401 and unsigned.json()["reason"] == "step_up_required", unsigned.text
    l1 = client.post(f"{first}/approve", headers=headers, json=signed(first))
    assert l1.status_code == 409 and l1.json()["reason"] == "needs_proven_key", l1.text
    monkeypatch.setattr(client.app.state.identity, "passkey_verification_level", lambda _credential: 2)
    wrong = client.post(f"{second}/approve", headers=headers, json=signed(first))
    assert wrong.status_code == 401 and "another action" in wrong.json()["message"], wrong.text
    assert client.get(path, headers=headers).json()[field] == before
    if kind == "budget":
        assert client.post("/v1/actions", headers=AGENT, json=action_body(clock, key="budget-block")).status_code == 429

    approved = client.post(f"{first}/approve", headers=headers, json=signed(first))
    assert approved.status_code == 200 and approved.json()["state"] == "succeeded", approved.text
    assert client.get(path, headers=headers).json()[field] == after
    if kind == "budget":
        assert client.post("/v1/actions", headers=AGENT, json=action_body(clock, key="budget-allowed")).status_code == 201
    stale = client.post(f"{second}/approve", headers=headers, json=signed(second))
    assert stale.status_code == 200 and stale.json()["state"] == "failed", stale.text
    assert "agent settings changed" in stale.json()["result"]["message"]
