# SPDX-License-Identifier: Apache-2.0
"""FAM-01: real household sessions, durable controls and shared proxy boundaries."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.identity.scopes import _ROUTES
from onemind_core.proxy import SESSION_COOKIE, AppProxy, AppRoute, gateway_session_resolver, sharing_check
from test_identity import (  # noqa: F401
    PASSWORD, SoftAuthenticator, audit_events, csrf, enrol, id_settings, idc, register_passkey, setup_owner, stepped,
)


@pytest.fixture
def family(idc):
    setup_owner(idc)
    child = enrol(idc, "child", "kid")
    uid = child.get("/v1/me").json()["principal"]["id"]
    r = stepped(idc, "PUT", "/v1/apps/whoami/access", json={"people": [uid]})
    assert r.status_code == 200
    assert put(idc, uid).status_code == 200  # clear the default age rating: these tests start unrestricted
    return idc, child, uid


def put(owner, uid, **policy):
    return owner.put(f"/v1/family/profiles/{uid}", headers=csrf(owner), json=policy)


def fresh_passkey(owner):
    options = owner.post("/v1/auth/login/options")
    assert options.status_code == 200, options.text
    assertion = owner.passkey.assert_(options.json()["publicKey"]["challenge"])
    signed_in = owner.post("/v1/auth/login", json={"passkey": assertion})
    assert signed_in.status_code == 200, signed_in.text


def apps(client):
    response = client.get("/v1/apps")
    assert response.status_code == 200, response.text
    return [a["id"] for a in response.json()]


def app_session(client, username):
    # The app-host cookie carries a bearer session, unlike the dashboard's HttpOnly cookie.
    signed_in = client.post("/v1/auth/login", json={"username": username, "password": PASSWORD, "client": "app"})
    assert signed_in.status_code == 200, signed_in.text
    return {"cookie": f"{SESSION_COOKIE}={signed_in.json()['access_token']}"}


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
    headers = app_session(child, "kid")
    resolve = gateway_session_resolver(gateway.tokens, gateway.authenticators)
    proxy = AppProxy(gateway.catalog, lambda _: "installed", resolve,
                     lambda *_: "upstream", box_domains=("onemind.local",), shared=shared,
                     path_aware_sessions=True)
    proxy.route_for = lambda _: AppRoute(app_id="whoami", host="upstream", port=80, access="signed_in", name="Whoami")
    assert proxy.decide(headers, "whoami", "lan")[0] == 404
    assert not shared(principal, "whoami", headers, "lan")
    assert put(owner, uid).status_code == 200
    assert shared(principal, "whoami", headers, "lan")
    assert proxy.decide(headers, "whoami", "lan")[0] == 204
    assert not shared(principal, "whoami", headers, "mesh")  # a password-only session is LAN-only
    assert proxy.decide(headers, "whoami", "mesh")[0] == 401
    for access in ("adults", "owner"):
        proxy.route_for = lambda _, access=access: AppRoute(app_id="whoami", host="upstream", port=80, access=access, name="Whoami")
        assert proxy.decide(headers, "whoami", "lan")[0] == 403
    assert child.get("/v1/me").json()["principal"]["role"] == "child"
    assert stepped(owner, "POST", "/v1/users", json={"display_name": "Nobody", "role": "toddler"}).status_code == 422


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
    fresh_passkey(owner)
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
    owner, child, uid = family
    # The fixture has confirmed sharing. Administration needs a fresh proof after its TTL.
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


@pytest.fixture
def teen_family(idc):
    setup_owner(idc)
    teen = enrol(idc, "teen", "tess")
    uid = teen.get("/v1/me").json()["principal"]["id"]
    assert stepped(idc, "PUT", "/v1/apps/whoami/access", json={"people": [uid]}).status_code == 200
    assert put(idc, uid).status_code == 200  # clear the default age rating: these tests start unrestricted
    return idc, teen, uid


def test_teen_creation_is_owner_only(idc):
    setup_owner(idc)
    register_passkey(idc, SoftAuthenticator())
    r = stepped(idc, "POST", "/v1/users", json={"display_name": "Tess", "role": "teen"})
    assert r.status_code == 201 and r.json()["role"] == "teen"
    adult, guest = enrol(idc, "adult", "ana"), enrol(idc, "guest", "gus")
    for c in (adult, guest):
        assert c.post("/v1/users", headers=csrf(c), json={"display_name": "Tim", "role": "teen"}).status_code == 403
    teen = enrol(idc, "teen", "tess2")
    assert teen.post("/v1/users", headers=csrf(teen), json={"display_name": "Tim", "role": "adult"}).status_code == 403
    assert teen.patch(f"/v1/users/{r.json()['id']}", headers=csrf(teen), json={"role": "owner"}).status_code == 403
    assert teen.get("/v1/me").json()["principal"]["role"] == "teen"
    # The owner can move a person between roles, and unknown roles stay refused.
    assert stepped(idc, "PATCH", f"/v1/users/{r.json()['id']}", json={"role": "child"}).json()["role"] == "child"
    assert stepped(idc, "PATCH", f"/v1/users/{r.json()['id']}", json={"role": "adult"}).json()["role"] == "adult"


def test_teen_has_child_scopes_and_no_owner_or_pro_routes(teen_family):
    from onemind_core.identity import scopes as sc

    owner, teen, uid = teen_family
    assert sc.role_scopes("teen") == sc.role_scopes("child")
    assert not {"actions:approve", "users:admin", "users:read", "tokens:admin", "nodes:read", "logs:read"} & sc.role_scopes("teen")
    assert teen.get("/v1/apps").status_code == 200
    # Nothing here may be reached by a teen: Pro screens' data, owner administration, approvals.
    for method, path in [
        ("GET", "/v1/nodes"), ("GET", "/v1/users"), ("GET", f"/v1/family/profiles/{uid}"),
        ("GET", "/v1/family/apps/whoami"), ("GET", "/v1/actions"), ("GET", "/v1/backups/status"),
        ("GET", "/v1/tokens"), ("GET", "/v1/audit/verify"),
    ]:
        assert teen.request(method, path).status_code == 403, (method, path)
    for path in ("/v1/actions/act_missing/approve", "/v1/actions/act_missing/deny"):
        assert teen.post(path, headers=csrf(teen), json={}).status_code == 403, path
    assert teen.put(f"/v1/family/profiles/{uid}", headers=csrf(teen), json={}).status_code == 403
    assert teen.put("/v1/family/apps/whoami", headers=csrf(teen), json={}).status_code == 403


def test_teen_is_filtered_by_family_limits_and_sharing(teen_family):
    owner, teen, uid = teen_family
    assert apps(teen) == ["whoami"]
    assert put(owner, uid, allowed_apps=[]).status_code == 200
    assert apps(teen) == []
    assert teen.get("/v1/apps/whoami").status_code == 404
    assert put(owner, uid, max_age_rating=16).status_code == 200
    assert apps(teen) == []  # unclassified apps fail closed, as for a child
    path = "/v1/family/apps/whoami"
    for age, expected in [(17, []), (16, ["whoami"]), (13, ["whoami"])]:
        assert owner.put(path, headers=csrf(owner), json={"min_age": age, "tags": ["Violence"]}).status_code == 200
        assert apps(teen) == expected
    assert put(owner, uid, max_age_rating=16, blocked_tags=["violence"]).status_code == 200
    assert apps(teen) == []
    assert put(owner, uid, max_age_rating=16, windows=[]).status_code == 200
    assert apps(teen) == []
    # Family limits never grant access: an app not shared with the teen stays hidden.
    assert owner.put("/v1/apps/whoami/access", headers=csrf(owner), json={"people": []}).status_code == 200
    assert owner.put(path, headers=csrf(owner), json={"min_age": 0, "tags": []}).status_code == 200
    assert put(owner, uid).status_code == 200
    assert apps(teen) == []
    assert stepped(owner, "PUT", "/v1/apps/whoami/access", json={"roles": ["teen"]}).status_code == 200
    assert apps(teen) == ["whoami"]


def test_teen_proxy_and_birth_date(teen_family):
    owner, teen, uid = teen_family
    svc = owner.app.state.identity
    principal = svc.principal_for(svc.user(uid))
    assert principal.role == "teen"
    gateway = owner.app.state.gateway
    shared = sharing_check(gateway.authenticators, gateway.app_filters)
    headers = app_session(teen, "tess")
    resolve = gateway_session_resolver(gateway.tokens, gateway.authenticators)
    proxy = AppProxy(gateway.catalog, lambda _: "installed", resolve,
                     lambda *_: "upstream", box_domains=("onemind.local",), shared=shared,
                     path_aware_sessions=True)
    for access, status in (("signed_in", 204), ("adults", 403), ("owner", 403)):
        proxy.route_for = lambda _, access=access: AppRoute(app_id="whoami", host="upstream", port=80, access=access, name="Whoami")
        assert proxy.decide(headers, "whoami", "lan")[0] == status, access
    # Age assurance: a teen carries a private birth date like a child; adults and guests do not.
    assert put(owner, uid, birth_date="2011-05-06").status_code == 200
    assert owner.get(f"/v1/family/profiles/{uid}").json()["birth_date"] == "2011-05-06"
    assert put(owner, uid, birth_date="2100-01-01").status_code == 422
    assert "birth_date" not in str(teen.get("/v1/me").json())
    guest = enrol(owner, "guest", "gus")
    gid = guest.get("/v1/me").json()["principal"]["id"]
    assert put(owner, gid, birth_date="2000-01-01").status_code == 422


@pytest.mark.parametrize("value", [False, True, "12", 12.5])
def test_ages_and_minutes_must_be_json_integers(family, value):
    # api-fuzz (schemathesis ST201) sent {"min_age": false, "tags": []}; lax mode stored age 0.
    owner, _child, uid = family
    r = owner.put("/v1/family/apps/whoami", headers=csrf(owner), json={"min_age": value, "tags": []})
    assert r.status_code == 422, r.text
    assert put(owner, uid, max_age_rating=value).status_code == 422
    window = {"days": [0], "start_minute": value, "end_minute": 60}
    assert put(owner, uid, windows=[window]).status_code == 422


def rating(owner, uid):
    r = owner.get(f"/v1/family/profiles/{uid}")
    assert r.status_code == 200, r.text
    return r.json()["max_age_rating"]


def new_person(owner, role, name="Pat"):
    if getattr(owner, "passkey", None) is None:
        register_passkey(owner, SoftAuthenticator())
    r = stepped(owner, "POST", "/v1/users", json={"display_name": name, "role": role})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_new_child_and_teen_get_default_age_ratings(idc):
    setup_owner(idc)
    child, teen = new_person(idc, "child"), new_person(idc, "teen")
    assert rating(idc, child) == 12
    assert rating(idc, teen) == 16
    for role in ("adult", "guest"):
        assert rating(idc, new_person(idc, role)) is None
    # A preset is only a start: the owner can raise it or clear it, and it stays that way.
    assert put(idc, child, max_age_rating=7).status_code == 200
    assert put(idc, teen).status_code == 200
    assert (rating(idc, child), rating(idc, teen)) == (7, None)
    # An unclassified app is blocked by a preset rating (existing fail-closed rule).
    kid = enrol(idc, "child", "kid")
    assert apps(kid) == []


def test_preset_events_never_carry_a_birth_date(idc, settings):
    setup_owner(idc)
    uid = new_person(idc, "teen")
    assert put(idc, uid, birth_date="2011-05-06", max_age_rating=16).status_code == 200
    events = [e for e in audit_events(settings) if "family" in str(e)]
    preset = [e for e in events if "preset_applied" in str(e)]
    assert len(preset) == 1 and preset[0]["event"] == "family.profile.preset_applied"
    assert preset[0]["data"]["payload"] == {"user_id": uid, "role": "teen", "max_age_rating": 16}
    assert "2011" not in str(events) and "birth" not in str(events)


def test_role_change_applies_the_preset_only_when_no_profile_exists(idc):
    setup_owner(idc)
    adult = new_person(idc, "adult")
    assert rating(idc, adult) is None
    assert stepped(idc, "PATCH", f"/v1/users/{adult}", json={"role": "teen"}).status_code == 200
    assert rating(idc, adult) == 16
    # Teen to child keeps the existing profile, even though the child preset is stricter.
    assert stepped(idc, "PATCH", f"/v1/users/{adult}", json={"role": "child"}).status_code == 200
    assert rating(idc, adult) == 16
    # A profile the owner cleared is a profile: a later role change does not bring the preset back.
    assert put(idc, adult).status_code == 200
    assert stepped(idc, "PATCH", f"/v1/users/{adult}", json={"role": "teen"}).status_code == 200
    assert rating(idc, adult) is None
    # Becoming an adult adds nothing, and renaming alone adds nothing.
    other = new_person(idc, "adult")
    assert stepped(idc, "PATCH", f"/v1/users/{other}", json={"display_name": "Sam"}).status_code == 200
    assert stepped(idc, "PATCH", f"/v1/users/{other}", json={"role": "guest"}).status_code == 200
    assert rating(idc, other) is None
    # A person who gets a profile before a role change keeps it.
    third = new_person(idc, "guest")
    assert put(idc, third, max_age_rating=10).status_code == 200
    assert stepped(idc, "PATCH", f"/v1/users/{third}", json={"role": "teen"}).status_code == 200
    assert rating(idc, third) == 10


def rate_manifest(settings, rating):
    """Give the whoami test app a manifest age_rating (or none), as a catalog entry would carry."""
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    lines = [ln for ln in path.read_text().splitlines() if not ln.startswith("  age_")]
    if rating is not None:
        i = next(n for n, ln in enumerate(lines) if ln.startswith("  category:"))
        lines[i + 1:i + 1] = [f"  age_rating: {rating}", '  age_reason: "Test reason."']
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def preset_kids(idc):
    """A child (preset 12) and a teen (preset 16), both with whoami shared, presets left in place."""
    setup_owner(idc)
    clients, ids = [], []
    for role in ("child", "teen"):
        client = enrol(idc, role, role)
        ids.append(client.get("/v1/me").json()["principal"]["id"])
        clients.append(client)
    assert stepped(idc, "PUT", "/v1/apps/whoami/access", json={"people": ids}).status_code == 200
    return idc, clients[0], clients[1]


def test_unrated_app_stays_hidden_under_a_limit(preset_kids, settings):
    _, child, teen = preset_kids
    rate_manifest(settings, None)
    assert apps(child) == [] and apps(teen) == []


def test_manifest_rating_is_the_default_classification(preset_kids, settings):
    owner, child, teen = preset_kids
    for rating, child_sees, teen_sees in [(0, True, True), (12, True, True), (16, False, True), (18, False, False)]:
        rate_manifest(settings, rating)
        assert (apps(child) == ["whoami"], apps(teen) == ["whoami"]) == (child_sees, teen_sees), rating
    # The owner sees the rating in the catalog; it is the manifest's own value.
    rate_manifest(settings, 12)
    entry = next(a for a in owner.get("/v1/apps").json() if a["id"] == "whoami")
    assert (entry["age_rating"], entry["age_reason"]) == (12, "Test reason.")
    rate_manifest(settings, None)
    entry = next(a for a in owner.get("/v1/apps").json() if a["id"] == "whoami")
    assert (entry["age_rating"], entry["age_reason"]) == (None, None)


def test_owner_classification_overrides_the_manifest_rating(preset_kids, settings):
    owner, child, teen = preset_kids
    path = "/v1/family/apps/whoami"
    # Manifest says 12 (a child may see it); the owner says 16: the owner wins and the child loses it.
    rate_manifest(settings, 12)
    assert owner.put(path, headers=csrf(owner), json={"min_age": 16}).status_code == 200
    assert apps(child) == [] and apps(teen) == ["whoami"]
    # Manifest says 18 (nobody under a limit); the owner says 0: the owner wins and both see it.
    rate_manifest(settings, 18)
    assert owner.put(path, headers=csrf(owner), json={"min_age": 0}).status_code == 200
    assert apps(child) == ["whoami"] and apps(teen) == ["whoami"]
    # An owner classification with only tags leaves the age to the manifest.
    assert owner.put(path, headers=csrf(owner), json={"tags": ["games"]}).status_code == 200
    assert apps(child) == [] and apps(teen) == []
    rate_manifest(settings, 12)
    assert apps(child) == ["whoami"]
