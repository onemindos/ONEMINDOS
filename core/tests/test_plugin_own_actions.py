# SPDX-License-Identifier: Apache-2.0
"""Real plugin tokens can poll their own requests without reading other actors' ledger."""
import pytest

from conftest import OWNER, action_body
from onemind_core.plugins.auth import allows_own_action_read
from test_plugin_token_policy import plugin, update_token  # noqa: F401


def file_request(client, clock, headers, *, app_id="whoami", key="own"):
    r = client.post("/v1/actions", headers=headers, json=action_body(clock, app_id=app_id, key=key))
    assert r.status_code == 201, r.text
    return r.json()


def read_grant(client, row, *extra):
    update_token(client, row, scopes=["actions:read:own", *extra])


def test_lists_only_same_plugin_and_polls_own_action(plugin, clock):
    client, headers, row = plugin
    read_grant(client, row, "actions:request:app.install")
    own = file_request(client, clock, headers)
    owner = file_request(client, clock, OWNER, app_id="hermes-like", key="owner")
    assert [a["id"] for a in client.get("/v1/actions", headers=headers).json()] == [own["id"]]
    r = client.get(f"/v1/actions/{own['id']}", headers=headers)
    assert r.status_code == 200 and r.json()["state"] == "awaiting_approval"
    denied = client.get(f"/v1/actions/{owner['id']}", headers=headers)
    missing = client.get("/v1/actions/nonexistent", headers=headers)
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()
    assert len(client.get("/v1/actions", headers=OWNER).json()) == 2


def test_other_plugin_cannot_read_original_plugin_request(plugin, clock):
    client, headers, row = plugin
    read_grant(client, row, "actions:request:app.install")
    own = file_request(client, clock, headers)
    update_token(client, row, principal_id="plugin:second-plugin")
    client.app.state.repo.set_app_state("second-plugin", "installed", clock())
    assert client.get("/v1/actions", headers=headers).json() == []
    assert client.get(f"/v1/actions/{own['id']}", headers=headers).status_code == 404


def test_read_only_grant_cannot_request_or_approve(plugin, clock):
    client, headers, row = plugin
    action = file_request(client, clock, OWNER)
    read_grant(client, row)
    assert client.get("/v1/actions", headers=headers).status_code == 200
    assert client.post("/v1/actions", headers=headers, json=action_body(clock)).status_code == 403
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=headers).status_code == 403
    assert client.post("/mcp", headers=headers, json={}).status_code == 403


@pytest.mark.parametrize("scopes", [["apps:read"], ["actions:request:app.install"],
                                  ["actions:read"], ["actions:read:all"],
                                  ["actions:read:self"], ["actions:read:own", "*"]])
def test_only_exact_internal_own_snapshot_authorizes_reads(plugin, scopes):
    client, headers, row = plugin
    update_token(client, row, scopes=scopes)
    assert client.get("/v1/actions", headers=headers).status_code == 403
    assert client.get("/v1/actions/nonexistent", headers=headers).status_code == 403


def test_grant_revocation_and_live_app_state_apply_to_polling(plugin, clock):
    client, headers, row = plugin
    read_grant(client, row, "actions:request:app.install")
    own = file_request(client, clock, headers)
    client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())
    assert client.get(f"/v1/actions/{own['id']}", headers=headers).status_code == 403
    client.app.state.repo.set_app_state("uptime-kuma", "installed", clock())
    read_grant(client, row)
    assert client.get(f"/v1/actions/{own['id']}", headers=headers).status_code == 200
    update_token(client, row, scopes=["apps:read"])
    assert client.get(f"/v1/actions/{own['id']}", headers=headers).status_code == 403


@pytest.mark.parametrize("change", [
    {"operation_id": "actions.future_admin"}, {"path": "/v1/actions/nonexistent/approve"},
    {"method": "POST"}, {"source": "api"}, {"app_status": "removed"},
    {"principal_id": "agent:uptime-kuma"},
])
def test_own_read_policy_does_not_expand_with_future_routes(change):
    policy = dict(method="GET", path="/v1/actions/nonexistent", operation_id="actions.get",
                  source="app-install", app_status="installed", principal_id="plugin:uptime-kuma",
                  scopes=["actions:read:own"])
    assert allows_own_action_read(**policy)
    assert not allows_own_action_read(**(policy | change))


def test_own_read_respects_owning_person_effective_cap(plugin, clock):
    from onemind_core.identity.models import UserRow

    client, headers, row = plugin
    identity = client.app.state.identity
    user = UserRow(id="own-reader-creator", display_name="Fixture", role="guest",
                   created_at=clock(), updated_at=clock())
    identity.repo.add(user)
    update_token(client, row, scopes=["actions:read:own"], owner_user_id=user.id)
    assert client.get("/v1/actions", headers=headers).status_code == 403
