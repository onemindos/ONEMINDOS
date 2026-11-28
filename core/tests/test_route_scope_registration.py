# SPDX-License-Identifier: Apache-2.0
"""CORE-HYG-01 (#323): app creation must not grow the global scope registry."""

import ast
import re
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core import routers
from onemind_core.app import create_app
from onemind_core.identity.scopes import _ROUTES, required_scopes


def test_route_scope_registry_stays_stable_across_startups_and_requests(settings, clock):
    # Importing the app discovers the routers before the first gateway is created.
    registered = tuple(_ROUTES)
    routes = None
    for _ in range(2):
        app = create_app(settings, clock=clock)
        with TestClient(app) as client:
            assert tuple(_ROUTES) == registered
            mounted = [(route.path, route.methods) for route in app.routes]
            if routes is None:
                routes = mounted
            assert mounted == routes
            for path in ("/v1/me/home", "/v1/machines/capabilities"):
                assert client.get(path, headers=OWNER).status_code == 200
                assert tuple(_ROUTES) == registered
        assert tuple(_ROUTES) == registered


def test_each_method_and_route_pattern_is_registered_once():
    counts = Counter((method, pattern.pattern) for methods, pattern, _ in _ROUTES for method in methods)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    assert not duplicates, f"duplicate route scopes: {duplicates}"


def test_routers_do_not_register_scopes_from_functions():
    # Cover handlers beyond the two requests exercised above.
    late = []
    for path in sorted(Path(routers.__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and ast.unparse(call.func).split(".")[-1] == "register_route_scope":
                    late.append(f"{path.name}:{call.lineno}")
    assert not late, f"register route scopes at module level: {sorted(set(late))}"


@pytest.mark.parametrize(("method", "path", "expected"), [
    ("GET", "/v1/me/home", None),
    ("HEAD", "/v1/me/home", None),
    ("PUT", "/v1/me/home", None),
    ("GET", "/v1/me/devices", None),  # #715: self-service, the handler requires a person's own session
    ("HEAD", "/v1/me/devices", None),
    ("DELETE", "/v1/me/devices/mdv_0123", None),
    ("POST", "/v1/me/devices", ("*",)),
    ("GET", "/v1/machines/capabilities", ("nodes:read",)),
    ("HEAD", "/v1/machines/capabilities", ("nodes:read",)),
    ("POST", "/v1/machines/enable", ("machines:admin",)),
    ("GET", "/v1/machines", ("nodes:read",)),
    ("HEAD", "/v1/machines", ("nodes:read",)),
    ("GET", "/v1/machines/my-vm", ("nodes:read",)),
    ("HEAD", "/v1/machines/my-vm", ("nodes:read",)),
    ("POST", "/v1/machines/my-vm/console", ("machines:admin",)),
    ("GET", "/v1/agents/kill-switch", ("instance:read",)),
    ("HEAD", "/v1/agents/kill-switch", ("instance:read",)),
    ("PUT", "/v1/agents/kill-switch", ("*",)),
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
    ("GET", "/v1/files/quotas"),
    ("GET", "/v1/mesh"),
    ("GET", "/v1/migrate/plans"),
    ("GET", "/v1/migrate/plans/{plan_id}"),
    ("GET", "/v1/migrate/plans/{plan_id}/helper"),
    ("GET", "/v1/migrate/repo/{plan_id}/config"),
    ("GET", "/v1/migrate/repo/{plan_id}/{typ}/"),
    ("GET", "/v1/migrate/repo/{plan_id}/{typ}/{name}"),
    ("GET", "/v1/onboarding/settings"),
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
    ("POST", "/v1/approval-policies"),
    ("POST", "/v1/approval-policies/{policy_id}/confirm"),
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
    ("POST", "/v1/files/requests/{request_id}/approve"),
    ("POST", "/v1/files/requests/{request_id}/deny"),
    ("POST", "/v1/migrate/plans"),
    ("POST", "/v1/migrate/plans/{plan_id}/copy"),
    ("POST", "/v1/migrate/plans/{plan_id}/cutover"),
    ("POST", "/v1/migrate/plans/{plan_id}/import"),
    ("POST", "/v1/migrate/plans/{plan_id}/revert"),
    ("POST", "/v1/migrate/repo/{plan_id}"),
    ("POST", "/v1/migrate/repo/{plan_id}/"),
    ("POST", "/v1/migrate/repo/{plan_id}/config"),
    ("POST", "/v1/migrate/repo/{plan_id}/{typ}/{name}"),
    ("POST", "/v1/onboarding/restore/apps"),
    ("POST", "/v1/onboarding/restore/candidates"),
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


_LINK = "oms_" + "A" * 43  # the share-link secret shape (routers/share_links.py TOKEN)


@pytest.mark.parametrize(("method", "path", "expected"), [
    # The share sheet (#612) keeps apps:read although the anonymous share links (#237) register later.
    ("GET", "/v1/share/types", ("apps:read",)),
    ("GET", "/v1/share/targets", ("apps:read",)),
    # Only the link-secret shape takes no principal at all.
    ("GET", f"/v1/share/{_LINK}", None),
    ("HEAD", f"/v1/share/{_LINK}/items/0", None),
])
def test_share_sheet_keeps_its_scope_beside_anonymous_share_links(settings, clock, method, path, expected):
    with TestClient(create_app(settings, clock=clock)):  # every router registers its route scopes
        assert required_scopes(method, path) == expected
