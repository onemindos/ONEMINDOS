# SPDX-License-Identifier: Apache-2.0
"""Real identity token authentication against the read-only plugin policy."""

from datetime import timedelta
import json

from fastapi import Depends
import pytest

from conftest import AGENT, OWNER
from onemind_core.auth import KINDS, Principal, parse_tokens
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.identity.models import TokenRow
from onemind_core.plugins.auth import allows_read, plugin_app_id


@pytest.fixture
def plugin(client, clock):
    """Seed only hashed credentials through the real identity repository (no issuer)."""
    token = new_secret("plg")
    row = TokenRow(id="tok_plugin_policy", prefix=token[:11], name="Installed plugin",
                   hash=sha256_hex(token), kind="plugin", principal_id="plugin:uptime-kuma",
                   owner_user_id=None, scopes=["nodes:read", "apps:read"], source="app-install",
                   created_by="owner", created_at=clock(), expires_at=clock() + timedelta(days=1))
    client.app.state.identity.repo.add(row)
    client.app.state.repo.set_app_state("uptime-kuma", "installed", clock())
    return client, {"Authorization": "Bearer " + token}, row


def update_token(client, row, **changes):
    client.app.state.identity.repo.update(TokenRow, [TokenRow.id == row.id], changes)


def test_installed_plugin_reads_use_real_identity_auth(plugin, clock):
    client, headers, row = plugin
    assert client.get("/v1/apps", headers=headers).status_code == 200
    assert client.get("/v1/nodes", headers=headers).status_code == 200
    # Known node route is authorized; the registry correctly reports no such node.
    assert client.get("/v1/nodes/nonexistent", headers=headers).status_code == 404
    client.app.state.repo.set_app_state("uptime-kuma", "stopped", clock())
    assert client.get("/v1/apps", headers=headers).status_code == 200
    # A live DB update narrows the token immediately; the catalog is not consulted.
    update_token(client, row, scopes=["nodes:read"])
    assert client.get("/v1/apps", headers=headers).status_code == 403
    assert client.get("/v1/nodes", headers=headers).status_code == 200


@pytest.mark.parametrize("status", [None, "removed", "removing", "installing", "updating", "failed", "unknown"])
def test_inactive_plugin_app_is_denied(plugin, clock, status):
    client, headers, _ = plugin
    client.app.state.repo.set_app_state("uptime-kuma", status, clock())
    r = client.get("/v1/apps", headers=headers)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied"


@pytest.mark.parametrize("changes", [
    {"source": "api"}, {"source": "file"}, {"source": ""},
    {"principal_id": "uptime-kuma"}, {"principal_id": "agent:uptime-kuma"},
    {"principal_id": "plugin:../uptime-kuma"}, {"principal_id": "plugin:other-app"},
    {"scopes": []}, {"scopes": ["*"]}, {"scopes": ["apps:read", "*"]},
    {"scopes": ["apps:read", "users:admin"]}, {"scopes": ["apps:read", "actions:approve"]},
    {"scopes": ["actions:request"]}, {"scopes": ["apps:read", "future:read"]},
    {"scopes": "apps:read"}, {"scopes": None}, {"scopes": [None]},
    {"scopes": ["apps:read", 42]}, {"scopes": {"apps:read": True}},
])
def test_unbound_or_overprivileged_plugin_tokens_fail_closed(plugin, changes):
    client, headers, row = plugin
    update_token(client, row, **changes)
    assert client.get("/v1/apps", headers=headers).status_code == 403


@pytest.mark.parametrize("method,path", [
    ("POST", "/v1/actions"), ("POST", "/v1/actions/arbitrary/approve"),
    ("POST", "/v1/actions/arbitrary/deny"), ("POST", "/v1/tokens"),
    ("DELETE", "/v1/tokens/arbitrary"), ("GET", "/v1/tokens"),
    ("GET", "/v1/me"), ("GET", "/v1/auth/sessions"),
    ("POST", "/mcp"), ("GET", "/mcp"), ("DELETE", "/mcp"),
    ("GET", "/v1/apps/uptime-kuma/credentials"),
    ("GET", "/v1/apps/uptime-kuma/access"), ("GET", "/v1/apps/uptime-kuma/plan"),
    ("GET", "/v1/actions"), ("GET", "/v1/users"),
])
def test_plugin_routes_are_deny_by_default(plugin, method, path):
    client, headers, _ = plugin
    r = client.request(method, path, headers=headers)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied", r.text


def test_new_authenticated_routes_are_not_inherited(plugin):
    client, headers, _ = plugin
    @client.app.get("/v1/policy-test-new-route")
    def added_route(p=Depends(client.app.state.gateway.principal)):
        return p.as_dict()
    # Mount before the dashboard fallback, as a future feature router would.
    client.app.router.routes.insert(0, client.app.router.routes.pop())
    assert client.get("/v1/policy-test-new-route", headers=headers).status_code == 403


def test_revocation_expiry_and_removal_take_effect(plugin, clock):
    client, headers, row = plugin
    update_token(client, row, revoked_at=clock())
    assert client.get("/v1/apps", headers=headers).status_code == 401
    update_token(client, row, revoked_at=None, expires_at=clock()-timedelta(seconds=1))
    assert client.get("/v1/apps", headers=headers).status_code == 401


def test_plugin_still_cannot_request_or_enter_static_tokens():
    p = Principal("plugin:uptime-kuma", "plugin", "plugin")
    assert not p.is_owner and not p.can_request_actions and "plugin" not in KINDS
    with pytest.raises(ValueError):
        parse_tokens({"tokens": {"fixture": p.as_dict()}})


def test_no_plugin_minter_is_added(plugin):
    client, _, _ = plugin
    r = client.post("/v1/tokens", headers=OWNER, json={"principal": {"kind": "plugin", "id": "plugin:test"},
                                                    "scopes": ["apps:read"]})
    assert r.status_code == 422
    # Static-v0 principals retain their existing behavior.
    assert client.get("/v1/apps", headers=AGENT).status_code == 200


def test_policy_denials_are_audited_without_token(plugin, settings):
    client, headers, _ = plugin
    assert client.get("/v1/users", headers=headers).status_code == 403
    records = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    assert any(r["event"] == "authz.denied" and "plugin_policy" in json.dumps(r) for r in records)
    assert headers["Authorization"].split()[1] not in settings.audit_path.read_text()


def test_pure_policy_rejects_unknown_paths_and_malformed_ids():
    assert plugin_app_id("plugin:"+"a"*60) is None
    assert plugin_app_id("plugin:Upper") is None
    for method,path in [("HEAD","/v1/apps"),("GET","/v1/nodes/id/extra"),("GET","/v1/apps/new")]:
        assert not allows_read(method=method,path=path,principal_id="plugin:test",source="app-install",
                               scopes=["apps:read","nodes:read"],app_status="installed")
