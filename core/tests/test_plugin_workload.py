# SPDX-License-Identifier: Apache-2.0
"""Install-created scoped plugin principals use the existing executor secret channel."""
import base64
import json
from pathlib import Path

import pytest
from sqlalchemy import select
import yaml

from conftest import OWNER, ScriptedExecutor, action_body, make_client
from onemind_core.identity.crypto import sha256_hex
from onemind_core.identity.models import TokenRow
from onemind_core.plugins.models import PluginInstallRow
from test_plugin_credentials import approve, request


@pytest.fixture
def plugin_settings(settings):
    path = Path(settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["plugin"] = {"principal": True, "secret": "plugin-identity",
                             "backend": {"service": "uptime-kuma", "port": 3001}}
    doc["spec"]["extensions"] = {"tools": []}
    doc["spec"]["permissions"] = ["apps:read", "actions:request:app.install"]
    path.write_text(yaml.safe_dump(doc))
    return settings


def tokens(client):
    return client.app.state.identity.repo.all(select(TokenRow).where(TokenRow.kind == "plugin"))


def bearer(grant):
    return {"Authorization": "Bearer " + grant.token}


def test_install_issues_only_after_approval_and_hands_scoped_secret(plugin_settings, clock):
    executor = ScriptedExecutor()
    with make_client(plugin_settings, clock, executor) as client:
        action_id = request(client, clock, "app.install")
        assert tokens(client) == []
        assert approve(client, action_id)["state"] == "succeeded"
        grant = executor.agents[-1]
        rows = tokens(client)
        assert len(rows) == 1 and rows[0].hash == sha256_hex(grant.token)
        assert rows[0].source == "app-install" and rows[0].principal_id == "plugin:uptime-kuma"
        assert rows[0].scopes == ["actions:read:own", "actions:request:app.install", "apps:read"]
        doc = json.loads(grant.manifest("app-uptime-kuma", "uptime-kuma"))
        data = {k: base64.b64decode(v).decode() for k, v in doc["data"].items()}
        assert data["ONEMIND_PLUGIN_TOKEN"] == grant.token
        assert "ONEMIND_AGENT_TOKEN" not in data
        assert data["ONEMIND_DISPATCH_PUBKEY"].startswith("-----BEGIN PUBLIC KEY-----")
        assert doc["metadata"]["labels"]["onemind.io/plugin-principal"] == "true"
        assert client.get("/v1/apps", headers=bearer(grant)).status_code == 200
        r = client.post("/v1/actions", headers=bearer(grant),
                        json=action_body(clock, app_id="whoami", key="plugin-requests"))
        assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
        own = client.get("/v1/actions", headers=bearer(grant))
        assert own.status_code == 200 and [a["id"] for a in own.json()] == [r.json()["id"]]
        assert client.get(f"/v1/actions/{action_id}", headers=bearer(grant)).status_code == 404
        assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=bearer(grant)).status_code == 403
        assert client.post("/mcp", headers=bearer(grant), json={}).status_code == 403
        stored = client.app.state.identity.repo.get(PluginInstallRow, "uptime-kuma")
        assert stored.secret_name == "plugin-identity" and stored.bundle_sha256.startswith("sha256:")
        assert grant.token not in plugin_settings.audit_path.read_text()
        assert grant.token not in repr(grant)
        assert client.post(f"/v1/tokens/{rows[0].id}/rotate", headers=OWNER,
                           json={"grace_s": 0}).status_code == 403


@pytest.mark.parametrize("outcome", ["failed", "outcome_unknown"])
def test_install_failure_retires_issued_token(plugin_settings, clock, outcome):
    with make_client(plugin_settings, clock, ScriptedExecutor(outcome)) as client:
        assert approve(client, request(client, clock, "app.install"))["state"] == outcome
        assert len(tokens(client)) == 1 and tokens(client)[0].revoked_at is not None


def test_remove_uses_installed_secret_even_after_catalog_declaration_disappears(plugin_settings, clock):
    executor = ScriptedExecutor()
    with make_client(plugin_settings, clock, executor) as client:
        approve(client, request(client, clock, "app.install"))
        grant = executor.agents[-1]
        path = Path(plugin_settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
        doc = yaml.safe_load(path.read_text())
        doc["spec"].pop("plugin")
        path.write_text(yaml.safe_dump(doc))
        approve(client, request(client, clock, "app.remove", "remove"))
        assert executor.agents[-1].name == "plugin-identity"
        assert executor.agents[-1].token is None
        assert client.get("/v1/apps", headers=bearer(grant)).status_code == 401


@pytest.mark.parametrize("permissions", [["*"], ["actions:approve"], ["actions:request"],
                                        ["events:subscribe:evt.*"], ["apps:read", 3]])
def test_unsupported_grants_block_install_before_issuance(plugin_settings, clock, permissions):
    path = Path(plugin_settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text()); doc["spec"]["permissions"] = permissions
    path.write_text(yaml.safe_dump(doc))
    with make_client(plugin_settings, clock) as client:
        r = client.post("/v1/actions", headers=OWNER, json=action_body(clock))
        assert r.status_code == 422
        assert tokens(client) == []


def test_secret_uses_persistent_dispatch_public_key(plugin_settings, clock):
    executor = ScriptedExecutor()
    with make_client(plugin_settings, clock, executor) as client:
        approve(client, request(client, clock, "app.install"))
        first = executor.agents[-1]
        approve(client, request(client, clock, "app.remove", "remove"))
        approve(client, request(client, clock, "app.install", "reinstall"))
        second = executor.agents[-1]
        assert first.dispatch_pubkey == second.dispatch_pubkey
        assert first.token != second.token
        assert client.get("/v1/apps", headers=bearer(first)).status_code == 401
        assert client.get("/v1/apps", headers=bearer(second)).status_code == 200
        assert (plugin_settings.audit_path.parent / "plugins" / "dispatch.key").stat().st_mode & 0o777 == 0o600


def test_dual_agent_identity_is_refused_before_legacy_issuance(plugin_settings, clock):
    path = Path(plugin_settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["agent"] = {"principal": True, "secret": "legacy-agent"}
    path.write_text(yaml.safe_dump(doc))
    with make_client(plugin_settings, clock) as client:
        r = client.post("/v1/actions", headers=OWNER, json=action_body(clock))
        assert r.status_code == 422
        assert tokens(client) == []


def test_credential_secret_cannot_overwrite_an_app_secret(plugin_settings, clock):
    path = Path(plugin_settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["secrets"] = [{"name": "plugin-identity", "keys": [{"key": "API_KEY"}]}]
    path.write_text(yaml.safe_dump(doc))
    with make_client(plugin_settings, clock) as client:
        r = client.post("/v1/actions", headers=OWNER, json=action_body(clock))
        assert r.status_code == 422
        assert tokens(client) == []


def test_registry_projects_installed_receipt_after_catalog_changes(plugin_settings, clock):
    from conftest import make_client, ScriptedExecutor
    from test_plugin_credentials import approve, request

    with make_client(plugin_settings, clock, ScriptedExecutor()) as client:
        approve(client, request(client, clock, "app.install"))
        path = plugin_settings.apps_dir / "uptime-kuma" / "onemind.app.yaml"
        manifest = yaml.safe_load(path.read_text())
        manifest["spec"].pop("plugin"); manifest["spec"].pop("extensions")
        manifest["metadata"]["name"] = "Catalog changed"
        path.write_text(yaml.safe_dump(manifest))
        r = client.get("/v1/plugins/uptime-kuma", headers=OWNER)
        assert r.status_code == 200 and r.json()["name"] == "Uptime Kuma"


def test_install_plan_shows_every_grant_the_plugin_token_will_hold(plugin_settings, clock):
    """#409: the owner approves a plan that names the grants, and the plan hash binds them."""
    with make_client(plugin_settings, clock, ScriptedExecutor()) as client:
        action_id = request(client, clock, "app.install")
        action = client.get(f"/v1/actions/{action_id}", headers=OWNER).json()
        obj = action["plan"]["objects"][0]
        assert obj["plugin_grants"] == ["actions:read:own", "actions:request:app.install", "apps:read"]
        text = " ".join(action["plan"]["warnings"])
        assert "action app.install, which still needs your approval" in text
        assert "list of apps" in text
        stored = client.app.state.identity.repo.get(PluginInstallRow, "uptime-kuma")
        assert stored is None


def test_plan_without_a_plugin_declaration_carries_no_grants(settings, clock):
    with make_client(settings, clock, ScriptedExecutor()) as client:
        action_id = request(client, clock, "app.install")
        plan = client.get(f"/v1/actions/{action_id}", headers=OWNER).json()["plan"]
        assert "plugin_grants" not in plan["objects"][0]
