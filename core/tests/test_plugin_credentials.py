# SPDX-License-Identifier: Apache-2.0
"""Managed plugin credentials retire before effects and stay retired across retries."""
import json
from unittest.mock import patch

import pytest

from conftest import OWNER, action_body, make_client
from onemind_core.identity.models import TokenRow
from test_plugin_token_policy import plugin, update_token  # noqa: F401


def request(client, clock, type_, key="lifecycle"):
    r = client.post("/v1/actions", headers=OWNER, json=action_body(clock, type_=type_, key=key))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def approve(client, action_id):
    r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


def revoked(client, row):
    return client.app.state.identity.repo.get(TokenRow, row.id).revoked_at


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "outcome_unknown", "crash"])
def test_remove_retires_before_executor_for_every_outcome(plugin, clock, executor, outcome):
    client, headers, row = plugin
    action_id = request(client, clock, "app.remove")
    # Merely asking, or waiting for approval, cannot revoke a workload credential.
    assert revoked(client, row) is None
    original = executor.run

    def run(*args, **kwargs):
        assert revoked(client, row) is not None
        assert client.get("/v1/apps", headers=headers).status_code == 401
        return original(*args, **kwargs)

    executor.outcome = outcome
    executor.raise_exc = outcome == "crash"
    executor.run = run
    result = approve(client, action_id)
    assert result["state"] == ("outcome_unknown" if outcome == "crash" else outcome)
    retired = revoked(client, row)
    # Even restored app state can never reactivate the old bearer (or rotated previous hash).
    client.app.state.repo.set_app_state("uptime-kuma", "installed", clock())
    assert client.get("/v1/apps", headers=headers).status_code == 401
    assert revoked(client, row) == retired


def test_denied_request_and_rejected_approval_do_not_revoke(plugin, clock):
    client, _, row = plugin
    action_id = request(client, clock, "app.remove")
    r = client.post(f"/v1/actions/{action_id}/approve", headers={})
    assert r.status_code == 401
    assert revoked(client, row) is None


def test_reinstall_revokes_old_snapshot_even_without_plugin_declaration(plugin, clock, executor):
    client, headers, row = plugin
    client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())
    action_id = request(client, clock, "app.install")
    assert revoked(client, row) is None
    assert approve(client, action_id)["state"] == "succeeded"
    assert executor.calls == [("app.install", "uptime-kuma")]
    assert revoked(client, row) is not None
    assert client.get("/v1/apps", headers=headers).status_code == 401


def test_storage_failure_prevents_removal_executor(plugin, clock, executor):
    client, _, row = plugin
    action_id = request(client, clock, "app.remove")
    repo = client.app.state.identity.repo
    with patch.object(repo, "update", side_effect=RuntimeError("storage unavailable")):
        result = approve(client, action_id)
    assert result["state"] == "failed"
    assert executor.calls == []
    assert revoked(client, row) is None


@pytest.mark.parametrize("status", [None, "removed", "removing", "installing", "failed", "unknown"])
def test_gateway_recovery_persistently_retires_inactive_credentials(plugin, settings, clock, status):
    client, headers, row = plugin
    client.app.state.repo.set_app_state("uptime-kuma", status, clock())
    with make_client(settings, clock) as restarted:
        assert revoked(restarted, row) is not None
        restarted.app.state.repo.set_app_state("uptime-kuma", "installed", clock())
        assert restarted.get("/v1/apps", headers=headers).status_code == 401


@pytest.mark.parametrize("status", ["installed", "stopped"])
def test_gateway_recovery_preserves_live_snapshots(plugin, settings, clock, status):
    client, headers, row = plugin
    client.app.state.repo.set_app_state("uptime-kuma", status, clock())
    with make_client(settings, clock) as restarted:
        assert revoked(restarted, row) is None
        assert restarted.get("/v1/apps", headers=headers).status_code == 200


@pytest.mark.parametrize("changes", [{"kind": "agent"}, {"source": "api"},
                                        {"principal_id": "plugin:another-app"}])
def test_removal_does_not_revoke_unrelated_tokens(plugin, clock, changes):
    client, _, row = plugin
    update_token(client, row, **changes)
    assert approve(client, request(client, clock, "app.remove"))["state"] == "succeeded"
    assert revoked(client, row) is None


@pytest.mark.parametrize("outcome", ["failed", "outcome_unknown"])
def test_failed_install_retires_credentials_created_during_preparation(plugin, clock, executor, outcome):
    from onemind_core.actions import InstallHook

    client, _, row = plugin
    client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())

    def later_issuer(app, action):
        # Exercise cleanup after a subsequent install hook creates a live credential.
        update_token(client, row, revoked_at=None)
        return []

    client.app.state.actions.install_hooks.append(InstallHook("fixture-issuer", later_issuer))
    executor.outcome = outcome
    result = approve(client, request(client, clock, "app.install"))
    assert result["state"] == outcome
    assert revoked(client, row) is not None


def _declare(client, name="uptime-kuma"):
    r = client.put(f"/v1/agents/plugin:{name}/inputs", headers=OWNER, json={"external_inputs": ["web"]})
    assert r.status_code == 200, r.text
    return client.app.state.agent_inputs


def test_removing_a_plugin_clears_what_the_owner_declared_for_it(plugin, clock, executor):
    client, _, _ = plugin
    ins = _declare(client)
    assert ins.view("plugin:uptime-kuma")["declared"] is True
    assert approve(client, request(client, clock, "app.remove"))["state"] == "succeeded"
    v = ins.view("plugin:uptime-kuma")
    assert v["declared"] is False and v["exposed"] is True  # a plugin installed later starts fail-closed again
    cleared = [r for r in client.app.state.settings.audit_path.read_text().splitlines() if "agent.inputs.cleared" in r]
    assert cleared and json.loads(cleared[-1])["principal"]["kind"] == "plugin"


@pytest.mark.parametrize("outcome", ["failed", "outcome_unknown"])
def test_a_failed_plugin_install_clears_the_declaration(plugin, clock, executor, outcome):
    client, _, _ = plugin
    client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())
    ins = _declare(client)
    executor.outcome = outcome
    approve(client, request(client, clock, "app.install"))
    assert ins.view("plugin:uptime-kuma")["declared"] is False


def test_a_successful_plugin_install_keeps_the_declaration(plugin, clock, executor):
    client, _, _ = plugin
    client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())
    ins = _declare(client)
    assert approve(client, request(client, clock, "app.install"))["state"] == "succeeded"
    assert ins.view("plugin:uptime-kuma")["declared"] is True
