# SPDX-License-Identifier: Apache-2.0
"""Actual hashed plugin tokens can only request explicitly granted action types."""
from datetime import timedelta

import pytest
from pydantic import BaseModel

from conftest import OWNER, action_body
from onemind_core.actions import FeatureAction
from onemind_core.identity.models import TokenRow, UserRow
from test_plugin_token_policy import plugin, update_token  # noqa: F401


def grant(client, row, *types):
    update_token(client, row, scopes=["apps:read", *("actions:request:" + t for t in types)])


def test_exact_request_stays_pending_and_cannot_approve(plugin, clock, executor):
    client, headers, row = plugin
    grant(client, row, "app.install")
    body = action_body(clock, app_id="whoami")
    first = client.post("/v1/actions", json=body, headers=headers)
    assert first.status_code == 201, first.text
    action = first.json()
    assert action["state"] == "awaiting_approval" and action["requested_by"]["kind"] == "plugin"
    assert executor.calls == []
    assert client.post("/v1/actions", json=body, headers=headers).status_code == 200
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=headers).status_code == 403
    grant(client, row, "app.remove")
    # A surviving narrow grant cannot authorize replay of a formerly allowed type.
    assert client.post("/v1/actions", json=body, headers=headers).status_code == 403
    assert executor.calls == [] and len(client.get("/v1/actions", headers=OWNER).json()) == 1


@pytest.mark.parametrize("type_", ["app.remove", "app.delete_data", "os.update.apply"])
def test_other_types_are_never_implied(plugin, clock, type_):
    client, headers, row = plugin
    grant(client, row, "app.install")
    r = client.post("/v1/actions", json=action_body(clock, type_=type_), headers=headers)
    assert r.status_code in (403, 422)  # unknown generic types fail body validation, never file
    assert client.get("/v1/actions", headers=OWNER).json() == []


def test_even_an_explicit_grant_does_not_override_owner_only_actions(plugin, clock):
    client, headers, row = plugin
    grant(client, row, "app.delete_data")
    body = action_body(clock, type_="app.delete_data")
    body["params"]["confirm"] = "uptime-kuma"
    assert client.post("/v1/actions", json=body, headers=headers).status_code == 403
    assert client.get("/v1/actions", headers=OWNER).json() == []


def test_feature_requester_policy_is_independent(plugin, clock):
    client, headers, row = plugin
    class Params(BaseModel):
        value: str
    ran = []
    service = client.app.state.actions
    for type_, requesters in (("demo.allowed", {"plugin"}), ("demo.owner_only", {"person"})):
        service.register_type(type_, FeatureAction(risk="write", requesters=frozenset(requesters), params_model=Params,
                                                   run=lambda a, finish: ran.append(a.id)))
    grant(client, row, "demo.allowed", "demo.owner_only")
    for type_, expected in (("demo.allowed", 201), ("demo.owner_only", 403)):
        r = client.post("/v1/actions", headers=headers, json={"type": type_, "params": {"value": "one"},
                        "idempotency_key": type_, "expires_at": (clock.now + timedelta(minutes=5)).isoformat()})
        assert r.status_code == expected, r.text
    assert ran == [] and len(client.get("/v1/actions", headers=OWNER).json()) == 1


@pytest.mark.parametrize("path", ["/mcp", "/v1/tokens", "/v1/apps/uptime-kuma/access"])
def test_request_grants_cannot_authorize_other_endpoints(plugin, path):
    client, headers, row = plugin
    grant(client, row, "app.install")
    assert client.post(path, headers=headers, json={}).status_code in (403, 405)


def test_effective_owner_cap_is_preserved(plugin, clock):
    client, headers, row = plugin
    identity = client.app.state.identity
    user = UserRow(id="policy-creator", display_name="Fixture", role="guest", created_at=clock(), updated_at=clock())
    identity.repo.add(user)
    grant(client, row, "app.install")
    update_token(client, row, owner_user_id=user.id)
    assert client.get("/v1/apps", headers=headers).status_code == 200
    assert client.post("/v1/actions", headers=headers, json=action_body(clock)).status_code == 403


def test_app_removed_after_authentication_cannot_file(plugin, clock, monkeypatch):
    client, headers, row = plugin
    grant(client, row, "app.install")
    service = client.app.state.actions
    create = service._create
    def removed_before_filing(principal, req, reason=None):
        client.app.state.repo.set_app_state("uptime-kuma", "removed", clock())
        return create(principal, req, reason)
    monkeypatch.setattr(service, "_create", removed_before_filing)
    assert client.post("/v1/actions", json=action_body(clock, app_id="whoami"), headers=headers).status_code == 403
    assert client.get("/v1/actions", headers=OWNER).json() == []
