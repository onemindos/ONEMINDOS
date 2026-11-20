# SPDX-License-Identifier: Apache-2.0
"""Actor/type checks cover lifecycle and feature requests before filing/replay."""
import json
from datetime import timedelta

import pytest
from pydantic import BaseModel

from conftest import AGENT, OWNER, action_body
from onemind_core.actions import FeatureAction
from onemind_core.auth import Principal
from onemind_core.errors import ApiError


def test_lifecycle_checks_deny_new_requests_and_replays(client, clock, executor, settings):
    allowed = {"app.install"}
    service = client.app.state.actions
    service.request_checks.append(lambda p, type_: p.is_owner or type_ in allowed)
    first = client.post("/v1/actions", json=action_body(clock), headers=AGENT)
    assert first.status_code == 201 and first.json()["state"] == "awaiting_approval"
    assert executor.calls == []
    allowed.clear()
    for key in ("k1", "new-key"):
        r = client.post("/v1/actions", json=action_body(clock, key=key), headers=AGENT)
        assert r.status_code == 403
    rows = client.get("/v1/actions", headers=OWNER).json()
    assert len(rows) == 1 and rows[0]["id"] == first.json()["id"]
    assert rows[0]["state"] == "awaiting_approval" and executor.calls == []
    records = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    assert sum(row["event"] == "authz.denied" for row in records) == 2
    assert client.post("/v1/actions", json=action_body(clock, key="owner-key"), headers=OWNER).status_code == 201


def test_feature_checks_cover_both_request_entry_points(client, clock):
    class Params(BaseModel):
        value: str

    service = client.app.state.actions
    checked, ran = [], []
    service.register_type("demo.guarded", FeatureAction(
        risk="write", run=lambda a, finish: ran.append(a.id), requesters=frozenset({"person", "agent"}),
        params_model=Params, check_request=lambda params, p: checked.append(params),
    ))
    allowed = {"demo.guarded"}
    service.request_checks.append(lambda p, type_: p.is_owner or type_ in allowed)
    principal = Principal("agent:fixture", "agent", "agent")
    expiry = clock.now + timedelta(minutes=5)
    first, created = service.request_feature(principal, "demo.guarded", {"value": "one"},
                                            idempotency_key="feature", expires_at=expiry)
    assert created and first["state"] == "awaiting_approval" and ran == []
    allowed.clear()
    for key in ("feature", "feature-new"):
        with pytest.raises(ApiError) as error:
            service.request_feature(principal, "demo.guarded", {"value": "one"},
                                    idempotency_key=key, expires_at=expiry)
        assert error.value.status == 403
    response = client.post("/v1/actions", headers=AGENT, json={
        "type": "demo.guarded", "params": {"value": "one"}, "idempotency_key": "generic-new",
        "expires_at": expiry.isoformat(),
    })
    assert response.status_code == 403
    assert checked == [] and ran == []
    assert len(client.get("/v1/actions", headers=OWNER).json()) == 1


@pytest.mark.parametrize("result", [False, None, 1, "allow"])
def test_checks_require_explicit_boolean_true(client, clock, result):
    client.app.state.actions.request_checks.append(lambda p, type_: result)
    assert client.post("/v1/actions", json=action_body(clock), headers=AGENT).status_code == 403
    assert client.get("/v1/actions", headers=OWNER).json() == []


def test_plugin_snapshot_cannot_widen_or_approve(client, clock, executor):
    from onemind_core.actions import ActionRequest
    from onemind_core.plugins.principal import PluginPrincipal

    grants = {"app.install"}
    principal = PluginPrincipal("plugin:uptime-kuma", "plugin", "plugin", grants)
    grants.add("app.remove")  # A caller's mutable set cannot widen the frozen snapshot.
    assert not principal.is_owner and principal.can_request_actions
    service = client.app.state.actions
    action, created = service.create(principal, ActionRequest.model_validate(action_body(clock)))
    assert created and action["state"] == "awaiting_approval" and executor.calls == []
    with pytest.raises(ApiError) as error:
        service.create(principal, ActionRequest.model_validate(action_body(clock, type_="app.remove", key="remove")))
    assert error.value.status == 403
    with pytest.raises(ApiError) as error:
        service.approve(principal, action["id"])
    assert error.value.status == 403 and executor.calls == []
    assert len(client.get("/v1/actions", headers=OWNER).json()) == 1


@pytest.mark.parametrize("action_type", ["*", "app.*", "app..install", "app.install\n", "actions:approve"])
def test_plugin_grants_are_exact_types(action_type):
    from onemind_core.plugins.principal import PluginPrincipal

    with pytest.raises(ValueError):
        PluginPrincipal("plugin:uptime-kuma", "plugin", "plugin", {action_type})


def test_feature_path_enforces_plugin_exact_grants(client, clock):
    from onemind_core.plugins.principal import PluginPrincipal

    service = client.app.state.actions
    ran = []
    for type_ in ("demo.allowed", "demo.denied"):
        service.register_type(type_, FeatureAction(
            risk="write", requesters=frozenset({"plugin"}), run=lambda a, finish: ran.append(a.id),
        ))
    principal = PluginPrincipal("plugin:uptime-kuma", "plugin", "plugin", {"demo.allowed"})
    expiry = clock.now + timedelta(minutes=5)
    allowed, created = service.request_feature(principal, "demo.allowed", {}, idempotency_key="allowed", expires_at=expiry)
    assert created and allowed["state"] == "awaiting_approval"
    with pytest.raises(ApiError) as error:
        service.request_feature(principal, "demo.denied", {}, idempotency_key="denied", expires_at=expiry)
    assert error.value.status == 403
    assert ran == [] and len(client.get("/v1/actions", headers=OWNER).json()) == 1


@pytest.mark.parametrize("id_,kind,role", [
    ("plugin:uptime-kuma", "person", "owner"), ("plugin:uptime-kuma", "plugin", "owner"),
    ("agent:uptime-kuma", "plugin", "plugin"),
])
def test_plugin_identity_cannot_impersonate_owner(id_, kind, role):
    from onemind_core.plugins.principal import PluginPrincipal

    with pytest.raises(ValueError):
        PluginPrincipal(id_, kind, role, {"app.install"})
