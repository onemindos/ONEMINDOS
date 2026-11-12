# SPDX-License-Identifier: Apache-2.0
"""THE authorization policy table: every gateway route x every principal kind -> expected status.

test_authz_matrix.py enumerates the live app's routes (app.routes) and runs one request per cell.
A route with no row here fails the suite, so a new endpoint cannot ship without someone writing
down who may call it. A row whose route is not on this tree yet carries `pending` (the stream that
adds it); its cells skip until the route exists and then run with the statuses below.

Each cell is one of:
- an int: the exact HTTP status;
- a frozenset of ints: any of these (used only for kinds that do not exist yet, where the contract
  fixes the outcome class but not the code);
- DECIDE: the contract leaves it to the stream that creates the kind. The cell fails as soon as
  the kind exists, so that stream writes the status down here.

Sources: contract §3 (who may call each v0 route), §11.2-§11.3 (agent principals, /mcp), §12.1
(principal kinds), §12.6 (roles, scopes, tokens, sharing). Column meanings: sec_world.DESCRIBE.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import sec_world as w
from sec_world import IDENTITY_STREAM, KINDS

DECIDE = "decide"
DENIED = frozenset({401, 403})
NOT_2XX = frozenset({401, 403, 404, 405})


@dataclass(frozen=True)
class Row:
    expect: dict[str, int | frozenset[int] | str]
    probe: Callable
    why: str
    pending: str | None = None
    # Known defects, kind -> reason. Those cells are strict xfail: they fail loudly once fixed,
    # so the marker is removed in the fixing PR.
    gaps: dict[str, str] | None = None


def cells(default, **over) -> dict:
    """Every column set to `default`, then the overrides (python names: app_agent -> app-agent)."""
    out = {k: default for k in KINDS}
    for k, v in over.items():
        k = k.replace("_", "-")
        assert k in out, f"unknown principal kind {k}"
        out[k] = v
    return out


GONE = dict(none=401, expired=401, revoked=401, revoked_agent=401)  # no valid credential: 401 first
OPEN = cells(200)
# §3 "any principal". A household child has only instance:read, apps:read, notifications:read and
# alerts:read (§12.6 role defaults), so the reads it lacks are 403.
ANY_PRINCIPAL = cells(200, **GONE, plugin=DECIDE, automation=DECIDE, node=DECIDE)
CHILD_CANNOT = cells(200, **GONE, child=403, plugin=DECIDE, automation=DECIDE, node=DECIDE)
# §3: owner or agent may request; §12.1: a node requests only node.join, never app actions.
REQUEST = cells(403, **GONE, owner=201, agent=201, app_agent=201, plugin=DECIDE, automation=DECIDE, node=DENIED)
# §3 and §12.1: only a person with role owner approves or denies. Everybody else, always.
OWNER_ONLY = cells(403, **GONE, owner=200, plugin=DENIED, automation=DENIED, node=DENIED)
# §11.3: kind agent only, anything else 403.
AGENTS_ONLY = cells(403, **GONE, agent=200, app_agent=200, plugin=DENIED, automation=DENIED, node=DENIED)
# GET/DELETE /mcp: no server stream and no sessions (405) once authenticated.
MCP_OTHER = cells(405, **GONE, child=403, plugin=NOT_2XX, automation=NOT_2XX, node=NOT_2XX)

POLICY: dict[tuple[str, str], Row] = {
    # ---- open (§3: only /healthz and /openapi.json; the dashboard shell is static) ------------------
    ("GET", "/healthz"): Row(OPEN, w.p_static("/healthz"), "§3 open health check"),
    ("GET", "/openapi.json"): Row(OPEN, w.p_static("/openapi.json"), "§3 OpenAPI is published"),
    ("HEAD", "/openapi.json"): Row(OPEN, w.p_static("/openapi.json"), "§3 OpenAPI is published"),
    ("GET", "/{full_path:path}"): Row(OPEN, w.p_static("/"), "§3 static dashboard with SPA fallback"),
    # ---- reads (§3) ---------------------------------------------------------------------------------
    ("GET", "/v1/instance"): Row(ANY_PRINCIPAL, w.p_static("/v1/instance"), "§3; §12.6 instance:read for all"),
    ("GET", "/v1/nodes"): Row(CHILD_CANNOT, w.p_static("/v1/nodes"), "§3; §12.6 child has no nodes:read"),
    ("GET", "/v1/nodes/{node_id}"): Row(CHILD_CANNOT, w.p_node, "§3; §12.6 child has no nodes:read"),
    ("GET", "/v1/apps"): Row(ANY_PRINCIPAL, w.p_static("/v1/apps"), "§3; §12.6 apps:read (shared apps for a child)"),
    ("GET", "/v1/actions"): Row(CHILD_CANNOT, w.p_static("/v1/actions"), "§3; §12.6 child has no actions:read"),
    ("GET", "/v1/actions/{action_id}"): Row(CHILD_CANNOT, w.p_action, "§3; §12.6 child has no actions:read"),
    # ---- the approval path (§3, §11.2: AI requests, a person approves) -------------------------------
    ("POST", "/v1/actions"): Row(REQUEST, w.p_request, "§3 owner or agent requests"),
    ("POST", "/v1/actions/{action_id}/approve"): Row(OWNER_ONLY, w.p_approve, "§3 owner only; agents 403"),
    ("POST", "/v1/actions/{action_id}/deny"): Row(OWNER_ONLY, w.p_deny, "§3 owner only"),
    # ---- MCP (§11.3) ----------------------------------------------------------------------------------
    ("POST", "/mcp"): Row(AGENTS_ONLY, w.p_mcp_ping, "§11.3 kind agent only"),
    ("GET", "/mcp"): Row(MCP_OTHER, w.p_static("/mcp"), "§11.3 no server-initiated stream"),
    ("DELETE", "/mcp"): Row(MCP_OTHER, w.p_static("/mcp"), "§11.3 no sessions to end"),
}

# ---- household identity: feat/identity (PR #41) --------------------------------------------------------
# Static-file principals keep v0 behaviour (§12.6 lists them read-only, source: file) and hold no
# session, so the routes that change sign-in credentials refuse them; the child and expired columns
# are household accounts. Objects of other people answer 404 (no existence oracle).
ID = IDENTITY_STREAM
SIGNED_IN = ANY_PRINCIPAL
ACCOUNT_ADMIN = cells(403, **GONE, owner=200, plugin=DENIED, automation=DENIED, node=DENIED)
NO_AUDIT = ("finding in feat/identity (PR #41): this 403 writes no authz.denied audit record "
            "(contract §3: every decision is audited)")
STATIC_TOKENS = ("owner", "adult", "guest", "agent", "app-agent")
UNAUDITED = {k: NO_AUDIT for k in STATIC_TOKENS}
PENDING_DENY = dict(plugin=DENIED, automation=DENIED, node=DENIED)


def own_credentials(child: int) -> dict:
    """Routes that change the caller's own sign-in credentials: a session only (§12.6, H-16)."""
    return cells(403, **GONE, child=child, **PENDING_DENY)


def others_objects(owner: int, child: int = 404) -> dict:
    """Another person's session or token: the owner acts, the rest cannot even see it."""
    return cells(404, **GONE, owner=owner, child=child, **PENDING_DENY)


POLICY |= {
    ("POST", "/v1/auth/setup"): Row(cells(401, owner=201), w.p_setup, "§12.6 first owner needs the install owner token", ID),
    ("POST", "/v1/auth/login/options"): Row(OPEN, w.p_static("/v1/auth/login/options"), "§12.6 anyone", ID),
    ("POST", "/v1/auth/login"): Row(OPEN, w.p_login, "§12.6 anyone, by password", ID),
    ("POST", "/v1/auth/enrol"): Row(cells(201), w.p_enrol, "§12.6 anyone holding an enrolment code", ID),
    ("POST", "/v1/auth/refresh"): Row(OPEN, w.p_refresh, "§12.6 anyone holding a refresh token", ID),
    ("POST", "/v1/auth/logout"): Row(cells(409, **GONE, child=204, plugin=NOT_2XX | {409}, automation=NOT_2XX | {409},
                                           node=NOT_2XX | {409}), w.p_static("/v1/auth/logout"),
                                     "§12.6 the session; a token is not a session (409 not_a_session)", ID),
    ("GET", "/v1/auth/sessions"): Row(SIGNED_IN, w.p_static("/v1/auth/sessions"), "§12.6 own; owner all", ID),
    ("DELETE", "/v1/auth/sessions/{session_id}"): Row(others_objects(owner=204), w.p_session_delete, "§12.6 own; owner all", ID),
    ("POST", "/v1/auth/passkeys/register/options"): Row(own_credentials(200), w.p_static("/v1/auth/passkeys/register/options"),
                                                        "§12.6 a signed-in person", ID, UNAUDITED),
    ("POST", "/v1/auth/passkeys/register"): Row(own_credentials(422), w.p_passkey_register,
                                                "§12.6 a signed-in person (the probe's credential is not a real WebAuthn one)", ID, UNAUDITED),
    ("GET", "/v1/auth/passkeys"): Row(own_credentials(200), w.p_static("/v1/auth/passkeys"), "§12.6 own passkeys", ID, UNAUDITED),
    ("DELETE", "/v1/auth/passkeys/{credential_id}"): Row(own_credentials(404), w.p_static("/v1/auth/passkeys/no-such-credential"),
                                                         "§12.6 own passkeys", ID, UNAUDITED),
    ("POST", "/v1/auth/password"): Row(own_credentials(204), w.p_password, "§12.6 own credentials", ID, UNAUDITED),
    ("POST", "/v1/auth/totp/setup"): Row(own_credentials(200), w.p_static("/v1/auth/totp/setup"), "§12.6 own credentials", ID, UNAUDITED),
    ("POST", "/v1/auth/totp/confirm"): Row(own_credentials(409), w.p_totp_confirm, "§12.6 own credentials (no setup started: 409)", ID, UNAUDITED),
    ("POST", "/v1/auth/totp/disable"): Row(own_credentials(204), w.p_totp_disable, "§12.6 own credentials", ID, UNAUDITED),
    ("GET", "/v1/me"): Row(SIGNED_IN, w.p_static("/v1/me"), "§12.6 any principal", ID),
    ("GET", "/v1/users"): Row(ACCOUNT_ADMIN, w.p_static("/v1/users"), "§12.6 users:read is owner only", ID),
    ("POST", "/v1/users"): Row(cells(403, **GONE, owner=201, **PENDING_DENY), w.p_user_create, "§12.6 owner", ID),
    ("PATCH", "/v1/users/{user_id}"): Row(ACCOUNT_ADMIN, w.p_user_patch, "§12.6 owner", ID),
    ("POST", "/v1/users/{user_id}/disable"): Row(ACCOUNT_ADMIN, w.p_user_disable, "§12.6 owner", ID),
    ("GET", "/v1/tokens"): Row(cells(200, **GONE, child=403, **PENDING_DENY), w.p_static("/v1/tokens"),
                               "§12.6 owner all, others own; a child's role defaults hold no tokens scope", ID),
    ("POST", "/v1/tokens"): Row(cells(403, **GONE, **PENDING_DENY), w.p_token_create,
                                "§12.6 tokens:self for a household person; static-file principals hold no API tokens", ID,
                                {"owner": NO_AUDIT, "adult": NO_AUDIT}),
    ("POST", "/v1/tokens/{token_id}/rotate"): Row(others_objects(owner=403, child=403), w.p_token_rotate,
                                                  "§12.6 only the holder rotates", ID),
    ("DELETE", "/v1/tokens/{token_id}"): Row(others_objects(owner=204, child=403), w.p_token_delete,
                                             "§12.6 the owner revokes any token", ID),
    ("GET", "/v1/apps/{app_id}/access"): Row(ANY_PRINCIPAL, w.p_static(f"/v1/apps/{w.TARGET_APP}/access"),
                                             "§12.6 owner; a person sees own entry", ID),
    ("PUT", "/v1/apps/{app_id}/access"): Row(ACCOUNT_ADMIN, w.p_access_put, "§12.6 owner, direct and audited", ID),
    ("POST", "/v1/actions/{action_id}/approve-options"): Row(OWNER_ONLY, w.p_approve_options, "§12.4 owner", ID),
    ("GET", "/signin"): Row(OPEN, w.p_static("/signin"), "the sign-in page is public", ID),
}
