# SPDX-License-Identifier: Apache-2.0
"""Actual approved installation receipts drive tool calls, never mutable catalog files."""
import base64
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import httpx
import pytest
import yaml

from conftest import AGENT, GUEST, OWNER, make_client
from onemind_core.identity.models import AppAccessRow, TokenRow, UserRow
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.plugins import dispatch
from onemind_core.plugins.models import PluginInstallRow
from test_plugin_credentials import approve, request
from test_plugin_workload import plugin_settings  # noqa: F401
from test_identity import SoftAuthenticator, csrf, id_settings, register_passkey, setup_owner

PATH = "/v1/plugins/uptime-kuma/tools"
CLOSED = {"type": "object", "additionalProperties": False}


@pytest.fixture
def tools(plugin_settings, clock, monkeypatch):
    path = Path(plugin_settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["extensions"]["tools"] = [
        {"name": name, "title": name.title(), "description": "untrusted plugin text", "effect": effect,
         "input": deepcopy(CLOSED), "output": deepcopy(CLOSED), "exposure": {"rest": True}}
        for name, effect in (("status", "read"), ("change", "write"), ("erase", "destructive"))
    ]
    path.write_text(yaml.safe_dump(doc))
    settings = id_settings(plugin_settings, require_passkey_approval=False)
    with make_client(settings, clock) as client:
        approve(client, request(client, clock, "app.install"))
        calls = []
        def backend(req):
            calls.append(req)
            return httpx.Response(200, json={})
        monkeypatch.setattr(dispatch, "client", lambda: httpx.Client(transport=httpx.MockTransport(backend), trust_env=False))
        yield client, calls, path


def call(client, name, *, headers=AGENT, key=None):
    body = {"arguments": {}}
    if key:
        body["idempotency_key"] = key
    return client.post(PATH + "/" + name, headers=headers, json=body)


def test_read_is_immediate_audited_and_uses_installed_snapshot(tools):
    client, calls, path = tools
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["plugin"]["backend"] = {"service": "changed", "port": 9999}
    doc["spec"]["extensions"]["tools"] = []
    path.write_text(yaml.safe_dump(doc))
    rows = client.get(PATH, headers=OWNER).json()
    assert {r["name"] for r in rows} == {"status", "change", "erase"}
    assert "From the plugin:" in rows[0]["description"]
    assert call(client, "status").json() == {"output": {}}
    assert len(calls) == 1 and calls[0].url.host == "uptime-kuma.app-uptime-kuma.svc.cluster.local"
    assert calls[0].headers["authorization"] != AGENT["Authorization"]
    assert any(json.loads(line)["event"] == "plugin.tool.read"
               for line in client.app.state.settings.audit_path.read_text().splitlines())


def test_mutation_stays_pending_then_signed_once_and_cannot_self_approve(tools):
    client, calls, _ = tools
    result = call(client, "change", key="change")
    assert result.status_code == 201, result.text
    action = result.json()
    assert action["state"] == "awaiting_approval" and action["risk"] == "write" and calls == []
    assert call(client, "change", key="change").json()["id"] == action["id"]
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
    assert approve(client, action["id"])["state"] == "succeeded" and len(calls) == 1
    token = calls[0].headers["authorization"].removeprefix("Bearer ")
    encoded = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert claims["action_id"] == action["id"] and claims["tool"] == "change"
    assert claims["args_sha256"] == dispatch.arguments_hash({})
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).status_code == 409
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["digest", "state", "args", "risk"])
def test_changed_preconditions_and_action_tampering_prevent_dispatch(tools, clock, change):
    client, calls, _ = tools
    action = call(client, "change").json()
    if change == "digest":
        client.app.state.identity.repo.update(PluginInstallRow, [PluginInstallRow.app_id == "uptime-kuma"],
                                               {"bundle_sha256": "sha256:" + "f" * 64})
    elif change == "state":
        client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())
    else:
        from onemind_core.ledger import ActionRow
        with client.app.state.repo._session() as session, session.begin():
            row = session.get(ActionRow, action["id"])
            if change == "args":
                row.params = {**row.params, "args": {"new": True}}
            else:
                row.risk = "destructive"
    response = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert response.status_code in {401, 409}
    assert calls == []


def test_undeclared_and_unexposed_tools_and_bad_arguments_are_refused(tools):
    client, calls, _ = tools
    assert call(client, "missing").status_code == 404
    assert client.post(PATH + "/status", headers=AGENT, json={"arguments": {"bad": True}}).status_code == 422
    row = client.app.state.identity.repo.get(PluginInstallRow, "uptime-kuma")
    manifest = deepcopy(row.manifest)
    manifest["spec"]["extensions"]["tools"][0]["exposure"]["rest"] = False
    client.app.state.identity.repo.update(PluginInstallRow, [PluginInstallRow.app_id == row.app_id], {"manifest": manifest})
    assert call(client, "status").status_code == 404 and calls == []


def test_scoped_apps_reader_cannot_request_mutation_and_sharing_is_checked(tools, clock):
    client, calls, _ = tools
    token = new_secret("pat")
    client.app.state.identity.repo.add(UserRow(id="reader", display_name="Reader", role="guest",
        created_at=clock(), updated_at=clock()))
    client.app.state.identity.repo.add(TokenRow(id="reader-token", prefix=token[:11], hash=sha256_hex(token),
        name="Read apps", kind="person", principal_id="reader", owner_user_id="reader", scopes=["apps:read"],
        source="api", created_by="owner", created_at=clock()))
    headers = {"Authorization": "Bearer " + token}
    assert call(client, "status", headers=headers).status_code == 404
    client.app.state.identity.repo.add(AppAccessRow(app_id="uptime-kuma", roles=["guest"], people=[],
        auth="onemind", updated_by="owner", updated_at=clock()))
    assert call(client, "status", headers=headers).status_code == 200
    assert call(client, "change", headers=headers).status_code == 403
    assert len(calls) == 1


def test_destructive_requires_verified_action_bound_passkey_even_when_optional(tools, clock):
    client, calls, _ = tools
    setup_owner(client)
    key = SoftAuthenticator()
    register_passkey(client, key)
    action = call(client, "erase", headers=OWNER).json()
    assert action["risk"] == "destructive"
    route = f"/v1/actions/{action['id']}/approve"
    assert client.post(route, headers=OWNER).status_code == 401
    assert client.post(route, headers=OWNER, json={"webauthn": {"fake": True}}).status_code == 401
    other = call(client, "change", headers=OWNER).json()
    options = client.post(f"/v1/actions/{other['id']}/approve-options", headers=OWNER).json()
    assert client.post(route, headers=OWNER, json={"webauthn": key.assert_(options["challenge"])}).status_code == 401
    assert calls == []
    options = client.post(f"/v1/actions/{action['id']}/approve-options", headers=OWNER).json()
    response = client.post(route, headers=OWNER, json={"webauthn": key.assert_(options["challenge"])})
    assert response.status_code == 200 and response.json()["state"] == "succeeded", response.text
    assert len(calls) == 1


def test_mutating_dispatch_serializes_against_app_removal(tools, clock, monkeypatch):
    from conftest import action_body
    client, calls, _ = tools

    def backend(req):
        calls.append(req)
        assert client.app.state.repo.get_app_state("uptime-kuma").status == "configuring"
        r = client.post("/v1/actions", headers=OWNER,
                        json=action_body(clock, type_="app.remove", key="concurrent-remove"))
        assert r.status_code == 409
        return httpx.Response(200, json={})

    monkeypatch.setattr(dispatch, "client", lambda: httpx.Client(transport=httpx.MockTransport(backend), trust_env=False))
    action = call(client, "change").json()
    assert approve(client, action["id"])["state"] == "succeeded"
    assert client.app.state.repo.get_app_state("uptime-kuma").status == "installed"
