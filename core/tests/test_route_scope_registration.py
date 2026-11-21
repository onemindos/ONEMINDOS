# SPDX-License-Identifier: Apache-2.0
"""CORE-HYG-01 (#323): app creation must not grow the global scope registry."""

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
