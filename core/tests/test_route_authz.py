# SPDX-License-Identifier: Apache-2.0
"""Scripted route inventory (threat model §5): every route the app registers is either on the short
public list below or answers 401 without a credential, and the routes that decide who may do what
refuse every non-owner credential.

A new route that forgets `Depends(principal)` fails the first test; a route made public on purpose
has to be added to PUBLIC here, in the same PR, where a reviewer sees it."""

from __future__ import annotations

import re

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER

# (method, path) of routes that answer without a bearer token, and why.
PUBLIC = {
    ("GET", "/healthz"),                       # liveness probe for the health gate
    ("GET", "/openapi.json"),                  # the contract; reveals the version only
    ("POST", "/v1/auth/setup"),                # first owner; needs the install token in the body
    ("POST", "/v1/auth/login/options"),        # WebAuthn challenge; bounded (MAX_OPEN_LOGIN_CHALLENGES)
    ("POST", "/v1/auth/login"),                # the sign-in itself; rate limited per source
    ("POST", "/v1/auth/enrol"),                # one-time enrolment code in the body; rate limited
    ("POST", "/v1/auth/refresh"),              # refresh token in the body; rate limited
    ("GET", "/signin"),                        # static sign-in page
    ("GET", "/{full_path:path}"),              # the dashboard's static files (never the API tree)
}


def inventory(app):
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            yield method, route.path


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


def test_every_route_needs_a_credential_unless_listed_public(client):
    routes = list(inventory(client.app))
    assert len(routes) > 60  # the inventory really walked the app
    seen_public = set()
    for method, path in routes:
        if (method, path) in PUBLIC:
            seen_public.add((method, path))
            continue
        r = client.request(method, concrete(path), json={})
        assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a credential"
    assert seen_public == PUBLIC  # a stale entry in PUBLIC is a failure too


def test_api_tree_is_never_served_by_the_static_fallback(client):
    for path in ("/v1/", "/v1/nope", "/mcp"):
        assert client.get(path).status_code in (401, 404, 405)


@pytest.mark.parametrize("who", [AGENT, GUEST, ADULT], ids=["agent", "guest", "adult"])
def test_owner_only_routes_refuse_everyone_else(client, clock, who):
    from conftest import action_body

    aid = client.post("/v1/actions", headers=OWNER, json=action_body(clock)).json()["id"]
    refused = [
        ("POST", f"/v1/actions/{aid}/approve", None),
        ("POST", f"/v1/actions/{aid}/deny", None),
        ("POST", f"/v1/actions/{aid}/approve-options", None),
        ("GET", "/v1/users", None),
        ("POST", "/v1/users", {"display_name": "x", "role": "adult"}),
        ("PATCH", "/v1/users/x", {"role": "owner"}),
        ("POST", "/v1/users/x/disable", None),
        ("PUT", "/v1/apps/whoami/access", {"roles": ["guest"], "people": []}),
        ("POST", "/v1/alerts/x/resolve", None),
    ]
    for method, path, body in refused:
        r = client.request(method, path, headers=who, json=body)
        assert r.status_code == 403, f"{method} {path} gave {r.status_code} to a non-owner"
    # and the action is exactly as it was
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
