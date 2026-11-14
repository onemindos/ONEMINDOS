# SPDX-License-Identifier: Apache-2.0
"""Board item CORE-SEC-11 (security suite: every route has a written policy row, tested per role).

Scripted route inventory (threat model §5): every route the app registers is either on the short
public list below or answers 401 without a credential, and the routes that decide who may do what
refuse every non-owner credential.

A new route that forgets `Depends(principal)` fails the first test; a route made public on purpose
has to be added to PUBLIC here, in the same PR, where a reviewer sees it.

The second half of this file is the authorization matrix from the security attack suite (PR #56, rebuilt
under D1): every route of the live gateway x every principal kind, against one policy table
(core/tests/sec_policy.py). It is one route-authz test file, not two: PUBLIC stays the only list of public
routes, and test_policy_open_rows_are_all_listed_public ties the table to it.

Why the matrix: "AI never actuates without human approval" holds only if *every* route refuses every caller
the contract does not name, and a hand-written list goes stale the day someone adds a route. Each cell
(route, principal) builds a fresh gateway, mints the principal, sends one valid request and checks:
- the status is the one in the policy table, and never a 5xx;
- a 401 or 403 uses the contract section 3 error envelope (401 also carries WWW-Authenticate);
- a 401 or 403 changed nothing: same actions, same states, same app states;
- a 403 is written to the audit log as authz.denied (section 3: every decision is audited)."""

from __future__ import annotations

import re

import pytest

import sec_policy
import sec_world
from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core import auth
from sec_policy import DECIDE, POLICY
from sec_world import DESCRIBE, KINDS, MINTABLE, PENDING_KINDS, World, route_methods

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
        # app secrets: only an owner changes or rotates them; the F-7 override card is owner only
        ("POST", "/v1/apps/whoami/secrets", {}),
        ("GET", "/v1/apps/whoami/owner-override", None),
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


# ---- the authorization matrix --------------------------------------------------------------------------
METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
ERROR_CODE = {401: "unauthenticated", 403: "permission_denied"}


@pytest.fixture
def world(settings, clock, tmp_path):
    with World(settings, clock, tmp_path) as w:
        yield w


# ---- the table covers the app ---------------------------------------------------------------------------
def test_every_route_has_a_policy_row(world):
    missing = sorted(world.routes() - POLICY.keys())
    assert not missing, (
        "routes with no row in core/tests/sec_policy.py (write down who may call them): "
        + ", ".join(f"{m} {p}" for m, p in missing)
    )


def test_every_row_is_a_live_route_or_names_its_stream(world):
    stale = sorted(k for k, row in POLICY.items() if k not in world.routes() and not row.pending)
    assert not stale, f"policy rows for routes that do not exist (and are not pending): {stale}"


def test_every_row_has_every_column():
    for key, row in POLICY.items():
        assert set(row.expect) == set(KINDS), (key, set(KINDS) ^ set(row.expect))
        assert row.why, f"{key}: say which contract section the row follows"


def test_every_principal_kind_has_a_column():
    """A kind or role the gateway can authenticate must be a minted column of the matrix."""
    columns = {"person": {"owner", "adult", "guest", "child"}, "agent": {"agent", "app-agent"}}
    for kind in auth.KINDS:
        cols = columns.get(kind, {kind})
        assert cols <= set(KINDS), f"principal kind {kind!r} has no matrix column"
        assert cols <= MINTABLE, f"principal kind {kind!r} exists now: write its mint() in sec_world.py"
    for role in auth.ROLES - {"agent"}:
        assert role in KINDS and role in MINTABLE, f"role {role!r} exists now: add and mint its column"


def test_the_matrix_is_not_vacuous(world):
    """Guards the guard: the table really reaches the routes that matter."""
    live = world.routes()
    for key in [("POST", "/v1/actions"), ("POST", "/v1/actions/{action_id}/approve"), ("POST", "/mcp")]:
        assert key in live and key in POLICY
    assert len(live & POLICY.keys()) >= 14


# ---- one test per (route, principal) -----------------------------------------------------------------------
CELLS = [(m, p, k) for (m, p) in POLICY for k in KINDS]
_ROUTES: set[tuple[str, str]] = set()  # the app's routes, filled by the first cell (same code in every world)


@pytest.mark.parametrize(("method", "path", "kind"), CELLS, ids=[f"{m} {p} as {k}" for m, p, k in CELLS])
def test_cell(method, path, kind, request):
    row = POLICY[(method, path)]
    # Skip before building a gateway when the answer is already known (keeps CI fast).
    if kind not in MINTABLE:
        pytest.skip(PENDING_KINDS[kind])
    if _ROUTES and (method, path) not in _ROUTES and row.pending:
        pytest.skip(f"route arrives with {row.pending}")
    world = request.getfixturevalue("world")
    _ROUTES.update(world.routes())
    if row.gaps and kind in row.gaps:
        request.applymarker(pytest.mark.xfail(strict=True, reason=row.gaps[kind]))
    if (method, path) not in world.routes():
        if row.pending:
            pytest.skip(f"route arrives with {row.pending}")
        pytest.fail(f"{method} {path} has a policy row but no route (see the stale-row test)")
    want = row.expect[kind]
    headers = world.mint(kind)  # skips while the kind cannot exist on this tree
    if want == DECIDE:
        pytest.fail(f"principal kind {kind!r} exists now: decide {method} {path} for it in sec_policy.py")
    req = row.probe(world)
    before = world.snapshot()
    audited = len(world.audit())
    r = world.send(method, req, headers)

    who = f"{method} {path} as {kind} ({DESCRIBE[kind]}); policy: {row.why}"
    switched_off = r.status_code == 503 and want == 503 and r.headers.get("content-type", "").startswith("application/json") \
        and r.json().get("error") == "unavailable"  # a feature that is off says so in the envelope; it is not a crash
    assert r.status_code < 500 or switched_off, f"{who}: server error {r.status_code}: {r.text[:300]}"
    ok = r.status_code == want if isinstance(want, int) else r.status_code in want
    assert ok, f"{who}: expected {want}, got {r.status_code}: {r.text[:300]}"

    if r.status_code in ERROR_CODE:
        if row.challenge == "bearer" and method != "HEAD":  # restic's data plane answers a bare status; HEAD has no body
            body = r.json()
            assert body.get("error") == ERROR_CODE[r.status_code] and isinstance(body.get("message"), str), body
        if r.status_code == 401:
            assert r.headers.get("www-authenticate", "").lower().startswith(row.challenge), who
        assert world.snapshot() == before, f"{who}: a refused request changed state"
        if r.status_code == 403:
            events = [rec.get("event") for rec in world.audit()[audited:]]
            assert "authz.denied" in events, f"{who}: 403 not audited (got {events})"


# ---- methods a route does not declare ----------------------------------------------------------------------
def test_undeclared_methods_never_succeed(world):
    """PUT on a GET route, GET on a POST route, HEAD and OPTIONS: never 2xx, never 5xx, for anyone."""
    live = route_methods(world.app)
    by_path: dict[str, set[str]] = {}
    for m, p in live:
        by_path.setdefault(p, set()).add(m)
    tried = 0
    for path, declared in sorted(by_path.items()):
        key = next(((m, path) for m in sorted(declared) if (m, path) in POLICY), None)
        if key is None or path == "/{full_path:path}":
            continue  # unknown routes fail test_every_route_has_a_policy_row; the SPA takes every GET
        concrete = POLICY[key].probe(world).path
        for method in METHODS:
            if method in declared or (method == "HEAD" and "GET" in declared and path == "/openapi.json"):
                continue
            for kind in ("none", "owner"):
                r = world.client.request(method, concrete, headers=world.mint(kind))
                tried += 1
                assert r.status_code < 500, (method, concrete, kind, r.status_code)
                assert not 200 <= r.status_code < 300, (method, concrete, kind, r.status_code, r.text[:200])
    assert tried > 20


def test_policy_module_lists_kinds_in_report_order():
    assert sec_world.KINDS[0] == "none" and set(sec_policy.cells(0)) == set(KINDS)


def test_policy_open_rows_are_all_listed_public():
    """No second public-route allowlist: a policy row that lets a caller with no credential in (anything but
    401) must be a route on PUBLIC above. HEAD and OPTIONS are the same route's read-only companions."""
    open_rows = {
        key for key, row in POLICY.items()
        if row.expect["none"] != 401 and key[0] not in ("HEAD", "OPTIONS")
    }
    assert open_rows <= PUBLIC, sorted(open_rows - PUBLIC)
