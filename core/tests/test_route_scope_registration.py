# SPDX-License-Identifier: Apache-2.0
"""CORE-HYG-01 (#323): app creation must not grow the global scope registry."""

import re

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.identity.scopes import _ROUTES, required_scopes


def test_create_app_twice_keeps_route_scope_registry_stable(settings, clock):
    # Use the noop, SQLite settings fixture and close each app's resources via its lifespan.
    first = create_app(settings, clock=clock)
    with TestClient(first):
        registered = tuple(_ROUTES)
        routes = [(route.path, route.methods) for route in first.routes]

    second = create_app(settings, clock=clock)
    with TestClient(second):
        assert len(_ROUTES) == len(registered)
        assert tuple(_ROUTES) == registered
        assert [(route.path, route.methods) for route in second.routes] == routes


@pytest.mark.parametrize(("method", "path", "expected"), [
    ("GET", "/v1/me/home", None),
    ("HEAD", "/v1/me/home", None),
    ("PUT", "/v1/me/home", None),
    ("GET", "/v1/machines/capabilities", ("nodes:read",)),
    ("HEAD", "/v1/machines/capabilities", ("nodes:read",)),
    ("POST", "/v1/machines/enable", ("machines:admin",)),
    ("GET", "/v1/machines", ("nodes:read",)),
    ("HEAD", "/v1/machines", ("nodes:read",)),
    ("GET", "/v1/machines/my-vm", ("nodes:read",)),
    ("HEAD", "/v1/machines/my-vm", ("nodes:read",)),
    ("POST", "/v1/machines/my-vm/console", ("machines:admin",)),
    ("POST", "/v1/me/home", ("*",)),
    ("GET", "/v1/me/home/123", ("*",)),
    ("POST", "/v1/machines/my-vm", ("*",)),
    ("GET", "/v1/machines/my-vm/console", ("*",)),
    ("POST", "/v1/machines/my-vm/console/extra", ("*",)),
])
def test_home_and_machine_scope_contract(method, path, expected):
    # Characterize the existing allow/deny table, including HEAD and fail-closed fallbacks.
    assert required_scopes(method, path) == expected


# Routes that still rely on the fail-closed fallback in required_scopes() (owner only) because no
# register_route_scope() row was written for them. This is a ratchet: it may only shrink. Give a route
# its own row at module level in its router, then delete its line here (the test fails on a stale line).
FALLBACK_BASELINE: set[tuple[str, str]] = {
    ("DELETE", "/v1/approval-policies/{policy_id}"),
    ("DELETE", "/v1/automation/rules/{rule_id}"),
    ("DELETE", "/v1/backups/destinations/{dest_id}"),
    ("DELETE", "/v1/fabric/join-tickets/{ticket_id}"),
    ("DELETE", "/v1/files/grants/{grant_id}"),
    ("DELETE", "/v1/files/uploads/{upload_id}"),
    ("DELETE", "/v1/migrate/repo/{plan_id}/{typ}/{name}"),
    ("GET", "/v1/approval-policies"),
    ("GET", "/v1/automation/rules"),
    ("GET", "/v1/automation/rules/{rule_id}"),
    ("GET", "/v1/automation/runs"),
    ("GET", "/v1/automation/schedules"),
    ("GET", "/v1/automation/state"),
    ("GET", "/v1/backups/destinations"),
    ("GET", "/v1/backups/kit"),
    ("GET", "/v1/backups/runs"),
    ("GET", "/v1/backups/runs/{run_id}"),
    ("GET", "/v1/backups/snapshots"),
    ("GET", "/v1/backups/snapshots/{snapshot_id}"),
    ("GET", "/v1/backups/snapshots/{snapshot_id}/file"),
    ("GET", "/v1/backups/snapshots/{snapshot_id}/tree"),
    ("GET", "/v1/backups/status"),
    ("GET", "/v1/backups/verifications"),
    ("GET", "/v1/databases"),
    ("GET", "/v1/fabric"),
    ("GET", "/v1/fabric/join-tickets"),
    ("GET", "/v1/files/download"),
    ("GET", "/v1/files/grants"),
    ("GET", "/v1/files/list"),
    ("GET", "/v1/files/preview"),
    ("GET", "/v1/files/quotas"),
    ("GET", "/v1/files/requests"),
    ("GET", "/v1/files/requests/{request_id}"),
    ("GET", "/v1/files/roots"),
    ("GET", "/v1/files/stat"),
    ("GET", "/v1/files/trash"),
    ("GET", "/v1/files/uploads/{upload_id}"),
    ("GET", "/v1/mesh"),
    ("GET", "/v1/migrate/plans"),
    ("GET", "/v1/migrate/plans/{plan_id}"),
    ("GET", "/v1/migrate/plans/{plan_id}/helper"),
    ("GET", "/v1/migrate/repo/{plan_id}/config"),
    ("GET", "/v1/migrate/repo/{plan_id}/{typ}/"),
    ("GET", "/v1/migrate/repo/{plan_id}/{typ}/{name}"),
    ("GET", "/v1/onboarding/settings"),
    ("GET", "/v1/photos/sources/{source_id}/coverage"),
    ("GET", "/v1/photos/sources/{source_id}/receipts"),
    ("GET", "/v1/restores"),
    ("GET", "/v1/restores/{restore_id}"),
    ("GET", "/v1/secrets/public-key"),
    ("GET", "/v1/sources"),
    ("GET", "/v1/sources/{source_id}"),
    ("GET", "/v1/storage"),
    ("GET", "/v1/storage/devices"),
    ("GET", "/v1/storage/operations/{action_id}"),
    ("GET", "/v1/tls"),
    ("GET", "/v1/windows"),
    ("PATCH", "/v1/automation/rules/{rule_id}"),
    ("PATCH", "/v1/files/uploads/{upload_id}"),
    ("PATCH", "/v1/photos/uploads/{upload_id}"),
    ("POST", "/v1/approval-policies"),
    ("POST", "/v1/apps/{app_id}/secrets"),
    ("POST", "/v1/automation/pause"),
    ("POST", "/v1/automation/resume"),
    ("POST", "/v1/automation/rules"),
    ("POST", "/v1/automation/rules/{rule_id}/disable"),
    ("POST", "/v1/automation/rules/{rule_id}/dry-run"),
    ("POST", "/v1/automation/rules/{rule_id}/enable"),
    ("POST", "/v1/backups/destinations"),
    ("POST", "/v1/backups/kit"),
    ("POST", "/v1/backups/kit/confirm"),
    ("POST", "/v1/backups/runs"),
    ("POST", "/v1/backups/verify"),
    ("POST", "/v1/deploy/compose"),
    ("POST", "/v1/fabric/join-tickets"),
    ("POST", "/v1/files/grants"),
    ("POST", "/v1/files/ops"),
    ("POST", "/v1/files/requests/{request_id}/approve"),
    ("POST", "/v1/files/requests/{request_id}/cancel"),
    ("POST", "/v1/files/requests/{request_id}/deny"),
    ("POST", "/v1/files/trash/empty"),
    ("POST", "/v1/files/uploads"),
    ("POST", "/v1/migrate/plans"),
    ("POST", "/v1/migrate/plans/{plan_id}/copy"),
    ("POST", "/v1/migrate/plans/{plan_id}/cutover"),
    ("POST", "/v1/migrate/plans/{plan_id}/import"),
    ("POST", "/v1/migrate/plans/{plan_id}/revert"),
    ("POST", "/v1/migrate/repo/{plan_id}"),
    ("POST", "/v1/migrate/repo/{plan_id}/"),
    ("POST", "/v1/migrate/repo/{plan_id}/config"),
    ("POST", "/v1/migrate/repo/{plan_id}/{typ}/{name}"),
    ("POST", "/v1/onboarding/restore/candidates"),
    ("POST", "/v1/photos/sources"),
    ("POST", "/v1/photos/sources/{source_id}/check"),
    ("POST", "/v1/photos/uploads"),
    ("POST", "/v1/restores"),
    ("POST", "/v1/storage/actions"),
    ("POST", "/v1/storage/plans"),
    ("POST", "/v1/storage/recovery-key"),
    ("PUT", "/v1/files/quotas/{person_id}"),
    ("PUT", "/v1/onboarding/settings"),
    ("PUT", "/v1/windows/{window_id}"),
}


def _unregistered(app) -> set[tuple[str, str]]:
    from test_route_authz import PUBLIC, inventory

    out = set()
    for method, path in inventory(app):
        if (method, path) in PUBLIC:
            continue
        probe = re.sub(r"\{[^}]+\}", "x", path)
        if not any(method in methods and rx.match(probe) for methods, rx, _ in _ROUTES):
            out.add((method, path))
    return out


def test_new_routes_must_register_a_scope(settings, clock):
    """An unregistered route silently falls back to owner only (ALL): safe, but it hides a forgotten
    register_route_scope(). A route added without one fails here; do not add it to the baseline."""
    app = create_app(settings, clock=clock)
    assert len(_unregistered(app) | FALLBACK_BASELINE) > 0 and len(app.routes) > 60  # the app was really walked
    new = sorted(_unregistered(app) - FALLBACK_BASELINE)
    assert not new, (
        "routes with no register_route_scope() row (call it at module level in the router): "
        + ", ".join(f"{m} {p}" for m, p in new)
    )
    stale = sorted(FALLBACK_BASELINE - _unregistered(app))
    assert not stale, f"now registered (or gone): delete from FALLBACK_BASELINE: {stale}"
