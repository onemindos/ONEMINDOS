# SPDX-License-Identifier: Apache-2.0
"""D-028: releasing either safety switch requires an action-bound L2 approval."""

import pytest

from conftest import OWNER
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
