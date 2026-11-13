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
        ("GET", "/v1/onboarding/settings", None),
        ("PUT", "/v1/onboarding/settings", {"box_name": "home-hub", "time_zone": "UTC", "backup_choice": "later"}),
        ("POST", f"/v1/actions/{aid}/approve", None),
        ("POST", f"/v1/actions/{aid}/deny", None),
        ("POST", f"/v1/actions/{aid}/approve-options", None),
        ("GET", "/v1/users", None),
        ("POST", "/v1/users", {"display_name": "x", "role": "adult"}),
        ("PATCH", "/v1/users/x", {"role": "owner"}),
        ("POST", "/v1/users/x/disable", None),
        ("PUT", "/v1/apps/whoami/access", {"roles": ["guest"], "people": []}),
        ("POST", "/v1/alerts/x/resolve", None),
        # Backups: destination changes, restores, the emergency kit and browsing a snapshot's files
        # are owner-only (an agent may request a run or a verify, never these).
        ("POST", "/v1/backups/destinations", {"kind": "usb", "label": "x", "config": {"path": "/run/onemind/backup/x"}}),
        ("DELETE", "/v1/backups/destinations/dst_0123456789abcdef", None),
        ("POST", "/v1/restores", {"snapshot_id": "abcdef0123456789", "scope": {"app_id": "whoami"}}),
        ("GET", "/v1/backups/kit", None),
        ("POST", "/v1/backups/kit", None),
        ("POST", "/v1/files/requests/frq_x/approve", None),
        ("POST", "/v1/files/requests/frq_x/deny", None),
        ("GET", "/v1/files/quotas", None),
        ("PUT", "/v1/files/quotas/owner", {"limit_bytes": 1}),
        ("POST", "/v1/backups/kit/confirm", {}),
        ("GET", "/v1/backups/snapshots/abcdef0123456789/tree", None),
        ("GET", "/v1/backups/snapshots/abcdef0123456789/file?path=/a", None),
        # app lifecycle: the generated login is owner only (never an agent), and deleting data is
        # owner only to plan or request (contract 12.40)
        ("GET", "/v1/apps/whoami/credentials", None),
        ("POST", "/v1/plans", {"type": "app.delete_data", "params": {"app_id": "whoami", "confirm": "whoami"}}),
        # storage: full disk identities and the LUKS recovery key are owner only (STORAGE-ACT-1)
        ("GET", "/v1/storage/devices", None),
        ("POST", "/v1/storage/recovery-key", None),
    ]
    for method, path, body in refused:
        r = client.request(method, path, headers=who, json=body)
        assert r.status_code == 403, f"{method} {path} gave {r.status_code} to a non-owner"
    # and the action is exactly as it was
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_plan_routes_need_a_credential_and_agents_may_plan_but_not_approve(client, clock):
    from conftest import action_body

    assert client.get("/v1/apps/whoami/plan").status_code == 401
    assert client.post("/v1/plans", json={}).status_code == 401
    # an agent may preview and request a lifecycle action, never decide it
    body = action_body(clock, type_="app.install")
    assert client.post("/v1/plans", headers=AGENT, json={"type": body["type"], "params": body["params"]}).status_code == 200
    r = client.post("/v1/actions", headers=AGENT, json=body)
    assert r.status_code == 201
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
