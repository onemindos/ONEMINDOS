# SPDX-License-Identifier: Apache-2.0
"""The app SDK's refusal contract, using the actual gateway and real authorization."""
from conftest import ADULT, AGENT, OWNER, action_body
from test_plugin_token_policy import plugin  # noqa: F401 (pytest fixture)


def test_app_sdk_approval_boundary_and_cross_app_secrets(plugin, clock):
    client, other_app, _ = plugin
    filed = client.post("/v1/actions", headers=AGENT, json=action_body(clock, app_id="whoami"))
    assert filed.status_code == 201, filed.text
    action = filed.json()
    assert action["state"] == "awaiting_approval"
    for headers in (ADULT, AGENT, other_app):
        refused = client.post(f"/v1/actions/{action['id']}/approve", headers=headers, json={})
        assert refused.status_code == 403 and refused.json()["error"] == "permission_denied", refused.text
    assert client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    refused = client.get("/v1/apps/whoami/secrets", headers=other_app)
    assert refused.status_code == 403 and refused.json()["error"] == "permission_denied", refused.text
