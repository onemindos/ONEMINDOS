# SPDX-License-Identifier: Apache-2.0
"""Only approved settings from an installed, offline schema reach a fixed ConfigMap."""
import json
from pathlib import Path

import pytest
import yaml

from conftest import AGENT, OWNER, FakeKubectl, action_body, make_client
from onemind_core.executors import KubernetesExecutor
from onemind_core.plugins.models import PluginInstallRow, PluginSettingsRow
from onemind_core.plugins.settings_schema import compile_schema
from test_plugin_workload import plugin_settings  # noqa: F401
from test_plugin_credentials import approve, request

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"greeting": {"type": "string", "maxLength": 40}}, "required": ["greeting"]}
PATH = "/v1/plugins/uptime-kuma/settings"


@pytest.fixture
def configured(plugin_settings, clock):
    app = Path(plugin_settings.apps_dir) / "uptime-kuma"
    doc = yaml.safe_load((app / "onemind.app.yaml").read_text())
    doc["spec"]["extensions"]["settings"] = {"schema": "settings.schema.json"}
    (app / "onemind.app.yaml").write_text(yaml.safe_dump(doc))
    (app / "settings.schema.json").write_text(json.dumps(SCHEMA))
    with make_client(plugin_settings, clock) as client:
        assert approve(client, request(client, clock, "app.install"))["state"] == "succeeded"
        yield client


def body(client, clock, key="configure", **settings):
    return {"settings": settings or {"greeting": "Hello"}, "idempotency_key": key,
            "bundle_sha256": client.get(PATH, headers=OWNER).json()["bundle_sha256"],
            "expires_at": action_body(clock)["expires_at"]}


def test_settings_change_stays_pending_and_uses_installed_snapshot(configured, clock):
    client = configured
    app = Path(client.app.state.settings.apps_dir) / "uptime-kuma"
    # Mutable catalog files cannot widen the schema used by the gateway.
    (app / "settings.schema.json").write_text('{"type":"object"}')
    r = client.post(PATH, headers=OWNER, json=body(client, clock))
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["state"] == "awaiting_approval"
    assert client.get(PATH, headers=OWNER).json()["settings"] == {}
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
    assert approve(client, action["id"])["state"] == "succeeded"
    assert client.get(PATH, headers=OWNER).json()["settings"] == {"greeting": "Hello"}


def test_real_executor_applies_fixed_configmap_only_after_approval(configured, clock):
    client = configured
    run = FakeKubectl()
    client.app.state.gateway.executor = KubernetesExecutor(runner=run)
    r = client.post(PATH, headers=OWNER, json=body(client, clock))
    assert r.status_code == 202 and run.calls == []
    assert approve(client, r.json()["id"])["state"] == "succeeded"
    assert len(run.calls) == 1
    argv, stdin = run.calls[0]
    assert argv == ["kubectl", "apply", "--server-side", "--field-manager=onemind-gateway",
                    "--force-conflicts", "-n", "app-uptime-kuma", "-f", "-"]
    doc = json.loads(stdin)
    assert doc["metadata"]["name"] == "plugin-settings"
    assert json.loads(doc["data"]["settings.json"]) == {"greeting": "Hello"}


@pytest.mark.parametrize("generic", [False, True])
def test_invalid_values_rejected_even_through_generic_actions(configured, clock, generic):
    client = configured
    data = body(client, clock, surprise="undeclared")
    if generic:
        data = {"type": "plugin.configure", "params": {"app_id": "uptime-kuma",
                "settings": data["settings"], "bundle_sha256": data["bundle_sha256"]},
                "idempotency_key": data["idempotency_key"], "expires_at": data["expires_at"]}
    r = client.post("/v1/actions" if generic else PATH, headers=OWNER, json=data)
    assert r.status_code == 422, r.text
    assert client.get(PATH, headers=OWNER).json()["settings"] == {}


@pytest.mark.parametrize("change", ["removed", "receipt"])
def test_stale_receipt_or_removed_plugin_blocks_approval(configured, clock, change):
    client = configured
    r = client.post(PATH, headers=OWNER, json=body(client, clock))
    if change == "removed":
        client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())
    else:
        client.app.state.identity.repo.update(PluginInstallRow, [PluginInstallRow.app_id == "uptime-kuma"],
                                             {"bundle_sha256": "sha256:" + "f" * 64})
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).status_code == 409
    assert client.app.state.identity.repo.get(PluginSettingsRow, "uptime-kuma") is None


def test_claim_serializes_with_removal_and_restores_stopped_status(configured, clock):
    client = configured
    client.app.state.repo.set_app_state("uptime-kuma", "stopped", clock())
    fake = FakeKubectl()

    def run(argv, **kwargs):
        assert client.app.state.repo.get_app_state("uptime-kuma").status == "configuring"
        remove = client.post("/v1/actions", headers=OWNER,
                             json=action_body(clock, type_="app.remove", key="while-configuring"))
        assert remove.status_code == 409
        return fake(argv, **kwargs)

    client.app.state.gateway.executor = KubernetesExecutor(runner=run)
    r = client.post(PATH, headers=OWNER, json=body(client, clock))
    assert approve(client, r.json()["id"])["state"] == "succeeded"
    assert client.app.state.repo.get_app_state("uptime-kuma").status == "stopped"


@pytest.mark.parametrize("schema", [
    {"type": "object", "$ref": "https://example.com/private"},
    {"type": "object", "$ref": "file:///etc/passwd"},
    {"type": "object", "$ref": "#"},
    {"type": "object", "properties": {"text": {"type": "string", "pattern": "(a+)+$"}}},
])
def test_hostile_schemas_are_offline_and_bounded(schema):
    with pytest.raises(ValueError):
        compile_schema(schema)


def test_local_nonrecursive_reference_is_supported():
    validator = compile_schema({"type": "object", "$defs": {"g": {"type": "string"}},
                                "properties": {"greeting": {"$ref": "#/$defs/g"}}})
    validator.validate({"greeting": "Hello"})


def update_manifest(client, version="2.0.3", permissions=None):
    path = client.app.state.settings.apps_dir / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"]["version"] = version
    if permissions is not None:
        doc["spec"]["permissions"] = permissions
    path.write_text(yaml.safe_dump(doc))


def test_update_preserves_credential_and_publishes_new_receipt(configured, clock):
    from sqlalchemy import select
    from onemind_core.identity.models import TokenRow
    client = configured
    repo = client.app.state.identity.repo
    before = repo.all(select(TokenRow).where(TokenRow.kind == "plugin"))[0]
    update_manifest(client)
    assert approve(client, request(client, clock, "app.update", "update"))["state"] == "succeeded"
    row = repo.get(PluginInstallRow, "uptime-kuma")
    assert row.manifest["metadata"]["version"] == "2.0.3"
    assert row.bundle_sha256 == client.app.state.repo.get_runtime("uptime-kuma").bundle_sha256
    after = repo.all(select(TokenRow).where(TokenRow.kind == "plugin"))
    assert len(after) == 1 and after[0].hash == before.hash and after[0].revoked_at is None
    assert client.get(PATH, headers=OWNER).status_code == 200


def test_changed_update_grants_require_fresh_approved_install(configured, clock):
    client = configured
    update_manifest(client, permissions=["apps:read", "nodes:read"])
    r = client.post("/v1/actions", headers=OWNER,
                    json=action_body(clock, type_="app.update", key="changed-grants"))
    assert r.status_code == 409
    assert "fresh approved install" in r.json()["message"]


def test_only_an_owner_reads_stored_values_back(configured, clock):
    client = configured
    assert approve(client, client.post(PATH, headers=OWNER, json=body(client, clock)).json()["id"])["state"] == "succeeded"
    assert client.get(PATH, headers=OWNER).json()["settings"] == {"greeting": "Hello"}
    seen = client.get(PATH, headers=AGENT)
    assert seen.status_code == 200 and seen.json()["settings"] == {}


@pytest.mark.parametrize("prop", [
    {"apiKey": {"type": "string"}}, {"smtp_password": {"type": "string"}}, {"botToken": {"type": "string"}},
    {"x": {"type": "string", "writeOnly": True}}, {"x": {"type": "string", "format": "password"}},
])
def test_schemas_cannot_ask_for_secrets(prop):
    with pytest.raises(ValueError, match="secrets"):
        compile_schema({"type": "object", "properties": prop})
