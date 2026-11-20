# SPDX-License-Identifier: Apache-2.0
"""FAM-01: real household sessions, durable controls and shared proxy boundaries."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.identity.scopes import _ROUTES
from onemind_core.proxy import AppProxy, AppRoute, sharing_check
from test_identity import audit_events, csrf, enrol, id_settings, idc, setup_owner, PASSWORD  # noqa: F401


@pytest.fixture
def family(idc):
    setup_owner(idc)
    child = enrol(idc, "child", "kid")
    uid = child.get("/v1/me").json()["principal"]["id"]
    r = idc.put("/v1/apps/whoami/access", headers=csrf(idc), json={"people": [uid]})
    assert r.status_code == 200
    return idc, child, uid


def put(owner, uid, **policy):
    return owner.put(f"/v1/family/profiles/{uid}", headers=csrf(owner), json=policy)


def apps(client):
    response = client.get("/v1/apps")
    assert response.status_code == 200, response.text
    return [a["id"] for a in response.json()]


def test_roles_allowlist_and_proxy(family):
    owner, child, uid = family
    assert apps(child) == ["whoami"]
    # Allowlisting never widens the existing app sharing grant.
    assert put(owner, uid, allowed_apps=[a["id"] for a in owner.get("/v1/apps").json()]).status_code == 200
    assert apps(child) == ["whoami"]
    assert put(owner, uid, allowed_apps=[]).status_code == 200
    assert apps(child) == []
    assert child.get("/v1/apps/whoami").status_code == 404
    svc = owner.app.state.identity
    principal = svc.principal_for(svc.user(uid))
    gateway = owner.app.state.gateway
    shared = sharing_check(gateway.authenticators, gateway.app_filters)
    headers = {"cookie": f"{svc.cookie}={child.cookies.get(svc.cookie)}"}
    proxy = AppProxy(gateway.catalog, lambda _: "installed", lambda *_: principal,
                     lambda *_: "upstream", box_domains=("onemind.local",), shared=shared)
    proxy.route_for = lambda _: AppRoute(app_id="whoami", host="upstream", port=80, access="signed_in", name="Whoami")
    assert proxy.decide(headers, "whoami")[0] == 404
    assert not shared(principal, "whoami", headers)
    assert put(owner, uid).status_code == 200
    assert shared(principal, "whoami", headers)
    assert proxy.decide(headers, "whoami")[0] == 204
    for access in ("adults", "owner"):
        proxy.route_for = lambda _, access=access: AppRoute(app_id="whoami", host="upstream", port=80, access=access, name="Whoami")
        assert proxy.decide(headers, "whoami")[0] == 403
    assert child.get("/v1/me").json()["principal"]["role"] == "child"
    assert owner.post("/v1/users", headers=csrf(owner), json={"display_name": "Teen", "role": "teen"}).status_code == 422


def test_ratings_tags_and_live_changes(family):
    owner, child, uid = family
    path = "/v1/family/apps/whoami"
    assert put(owner, uid, max_age_rating=12).status_code == 200
    assert apps(child) == []  # unknown classification fails closed
    for age, expected in [(13, []), (12, ["whoami"]), (0, ["whoami"])]:
        assert owner.put(path, headers=csrf(owner), json={"min_age": age, "tags": ["Violence"]}).status_code == 200
        assert apps(child) == expected
    assert put(owner, uid, blocked_tags=["violence"]).status_code == 200
    assert apps(child) == []
    assert owner.put(path, headers=csrf(owner), json={"min_age": 0, "tags": []}).status_code == 200
    assert apps(child) == ["whoami"]


@pytest.mark.parametrize("instant,allowed", [
    ("2026-11-16T21:59:59+00:00", False),  # Monday start exclusive before 22:00
    ("2026-11-16T22:00:00+00:00", True),
    ("2026-11-17T00:59:59+00:00", True),
    ("2026-11-17T01:00:00+00:00", False),
    ("2026-11-17T22:00:00+00:00", False),
])
def test_overnight_schedule(family, clock, instant, allowed):
    owner, child, uid = family
    assert put(owner, uid, windows=[{"days": [0], "start_minute": 1320, "end_minute": 60}]).status_code == 200
    clock.now = datetime.fromisoformat(instant)
    assert child.post("/v1/auth/login", json={"username": "kid", "password": PASSWORD}).status_code == 200
    assert ("whoami" in apps(child)) is allowed


def test_timezone_and_week_wrap(family, clock):
    owner, child, uid = family
    assert put(owner, uid, timezone="America/New_York", windows=[{"days": [6], "start_minute": 1380, "end_minute": 60}]).status_code == 200
    clock.now = datetime(2026, 11, 16, 5, 30, tzinfo=UTC)  # Monday 00:30, Sunday overnight window
    assert child.post("/v1/auth/login", json={"username": "kid", "password": PASSWORD}).status_code == 200
    assert owner.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    assert apps(child) == ["whoami"]
    clock.advance(1800)
    assert apps(child) == []
    assert put(owner, uid, windows=[]).status_code == 200
    assert apps(child) == []
    assert put(owner, uid, windows=None).status_code == 200
    assert apps(child) == ["whoami"]


def test_private_birth_date_permissions_and_persistence(family, settings, clock, executor):
    owner, child, uid = family
    path = f"/v1/family/profiles/{uid}"
    assert put(owner, uid, birth_date="2018-02-03").status_code == 200
    response = owner.get(path)
    assert response.json()["birth_date"] == "2018-02-03"
    assert response.headers["cache-control"] == "no-store"
    adult, guest = enrol(owner, "adult", "ana"), enrol(owner, "guest", "gus")
    for c in (child, adult, guest):
        assert c.get(path).status_code == 403
        assert put(c, uid).status_code == 403
        assert c.get("/v1/family/apps/whoami").status_code == 403
        assert c.put("/v1/family/apps/whoami", headers=csrf(c), json={}).status_code == 403
    assert owner.get(path, headers=AGENT).status_code == 403
    assert owner.put(path, headers=AGENT, json={}).status_code == 403
    assert owner.put(path, json={}).status_code == 403  # CSRF
    assert "2018-02-03" not in str(audit_events(settings))
    assert "birth_date" not in str(child.get("/v1/me").json())
    # A fresh gateway over the same database retains policy.
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as restarted:
        assert restarted.get(path, headers=OWNER).json()["birth_date"] == "2018-02-03"


def test_invalid_policies_and_owner_lockout(family):
    owner, child, uid = family
    for policy in [
        {"timezone": "Unknown/Zone"}, {"birth_date": "2100-01-01"},
        {"birth_date": "not-a-date"}, {"allowed_apps": ["missing-app"]},
        {"max_age_rating": -1}, {"blocked_tags": [""]},
        {"windows": [{"days": [7], "start_minute": 10, "end_minute": 20}]},
        {"windows": [{"days": [0], "start_minute": 10, "end_minute": 10}]},
    ]:
        assert put(owner, uid, **policy).status_code == 422
    oid = owner.get("/v1/me").json()["principal"]["id"]
    assert put(owner, oid, allowed_apps=[]).status_code == 422
    adult = enrol(owner, "adult", "ana")
    aid = adult.get("/v1/me").json()["principal"]["id"]
    assert put(owner, aid, birth_date="2000-01-01").status_code == 422
    assert put(owner, "missing").status_code == 404
    assert owner.get("/v1/family/apps/missing").status_code == 404


def test_scopes_registered_once(settings, clock, executor):
    before = len(_ROUTES)
    for _ in range(2):
        with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)):
            pass
    assert len(_ROUTES) == before


@pytest.mark.parametrize("instant,allowed", [
    ("2026-11-11T21:59:59+00:00", False),
    ("2026-11-11T22:00:00+00:00", True),
    ("2026-11-11T22:59:59+00:00", True),
    ("2026-11-11T23:00:00+00:00", False),
])
def test_same_day_boundaries(family, clock, instant, allowed):
    owner, child, uid = family
    assert put(owner, uid, windows=[{"days": [2], "start_minute": 1320, "end_minute": 1380}]).status_code == 200
    clock.now = datetime.fromisoformat(instant)
    assert ("whoami" in apps(child)) is allowed


def test_scoped_owner_token_cannot_manage_profiles(family):
    owner, child, uid = family
    r = owner.post("/v1/tokens", headers=csrf(owner), json={"name": "reader", "scopes": ["apps:read"]})
    assert r.status_code == 201
    bearer = {"Authorization": "Bearer " + r.json()["one_time"]["token"]}
    assert owner.get(f"/v1/family/profiles/{uid}", headers=bearer).status_code == 403
    assert owner.put(f"/v1/family/profiles/{uid}", headers=bearer, json={}).status_code == 403


def test_writes_require_passkey_step_up(family, clock):
    from test_identity import SoftAuthenticator, register_passkey

    owner, child, uid = family
    register_passkey(owner, SoftAuthenticator())
    # Registration proves presence; administration needs a fresh proof after its TTL.
    clock.advance(owner.app.state.identity.cfg.step_up_s + 1)
    assert put(owner, uid, allowed_apps=[]).status_code == 401
    assert owner.put("/v1/family/apps/whoami", headers=csrf(owner), json={"min_age": 0}).status_code == 401


def test_owned_agent_and_personal_tokens_inherit_family_policy(family):
    owner, child, uid = family
    adult = enrol(owner, "adult", "ana")
    aid = adult.get("/v1/me").json()["principal"]["id"]
    headers = []
    for principal in ("self", {"kind": "agent", "id": "agent:family-test"}):
        response = adult.post("/v1/tokens", headers=csrf(adult), json={
            "name": "family-test", "principal": principal, "scopes": ["apps:read"]})
        assert response.status_code == 201, response.text
        headers.append({"Authorization": "Bearer " + response.json()["one_time"]["token"]})
    assert put(owner, aid, allowed_apps=[]).status_code == 200
    for bearer in headers:
        assert owner.get("/v1/apps", headers=bearer).json() == []
        assert owner.get("/v1/apps/whoami", headers=bearer).status_code == 404
    assert put(owner, aid).status_code == 200
    for bearer in headers:
        assert owner.get("/v1/apps", headers=bearer).json()
