# SPDX-License-Identifier: Apache-2.0
"""THE authorization policy table: every gateway route x every principal kind -> expected status.

test_route_authz.py (the matrix half) enumerates the live app's routes (app.routes) and runs one request per cell.
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
    # The scheme a 401 offers in WWW-Authenticate (the restic data plane takes Basic, everything else Bearer).
    challenge: str = "bearer"


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

# ---- notifications, alerts and push: feat/notify-monitor (contract §12.14) ----------------------------
# People only for the inbox, channels, preferences and push devices, each their own (another
# person's object is 404); a child holds notifications:read and alerts:read but no :write. Agents
# read owner-addressed alerts and may file an alert's fix as a normal request, never approve it.
NOTIFY = "feat/notify-monitor (contract §12.14)"
AGENTS_DENIED = dict(agent=403, app_agent=403, **PENDING_DENY)
PEOPLE_READ = cells(200, **GONE, **AGENTS_DENIED)
PEOPLE_WRITE = cells(200, **GONE, child=403, **AGENTS_DENIED)


def own_object(owner: int) -> dict:
    """Another person's channel, device or notification: only its holder (the owner here) acts."""
    return cells(404, **GONE, owner=owner, child=403, **AGENTS_DENIED)


ALERT_READ = cells(200, **GONE, plugin=DECIDE, automation=DECIDE, node=DECIDE)
POLICY |= {
    ("GET", "/v1/alerts"): Row(ALERT_READ, w.p_static("/v1/alerts"), "§12.14 any principal, filtered by audience"),
    ("GET", "/v1/alerts/{alert_id}"): Row(
        cells(404, **GONE, owner=200, agent=200, app_agent=200, plugin=DECIDE, automation=DECIDE, node=DECIDE),
        w.p_alert("app.scan_blocked"), "§12.14 owners' alert: owners and agents read it, others 404 (audience)"),
    ("POST", "/v1/alerts/{alert_id}/ack"): Row(
        cells(403, **GONE, owner=200, adult=200, **PENDING_DENY), w.p_alert("app.unhealthy", "/ack"),
        "§12.14 owners and adults acknowledge; agents never"),
    ("POST", "/v1/alerts/{alert_id}/resolve"): Row(
        cells(403, **GONE, owner=200, **PENDING_DENY), w.p_alert("action.outcome_unknown", "/resolve"),
        "§12.14 owners resolve alerts with no automatic condition"),
    ("POST", "/v1/alerts/{alert_id}/fix"): Row(
        cells(403, **GONE, owner=202, agent=202, app_agent=202, **PENDING_DENY), w.p_alert("app.scan_blocked", "/fix"),
        "§12.14 owners and agents file the fix as a request (awaiting approval); approve=true is owner only"),
    ("GET", "/v1/notifications"): Row(PEOPLE_READ, w.p_static("/v1/notifications"), "§12.14 own inbox, people only"),
    ("GET", "/v1/notifications/{notification_id}"): Row(
        cells(404, **GONE, owner=200, **AGENTS_DENIED), w.p_notification(), "§12.14 own inbox; others 404"),
    ("POST", "/v1/notifications/{notification_id}/read"): Row(
        cells(404, **GONE, owner=200, **AGENTS_DENIED), w.p_notification("/read"),
        "§12.14 own inbox (a child marks its own notifications read: notifications:read is enough)"),
    ("POST", "/v1/notifications/read-all"): Row(PEOPLE_READ, w.p_static("/v1/notifications/read-all"),
                                                "§12.14 own inbox; notifications:read is enough to mark it read"),
    ("GET", "/v1/notifications/channels"): Row(PEOPLE_READ, w.p_static("/v1/notifications/channels"),
                                               "§12.14 own channels (owner: all, others' config hidden)"),
    ("POST", "/v1/notifications/channels"): Row(
        cells(201, **GONE, child=403, **AGENTS_DENIED), w.p_channel_create,
        "§12.14 people add their own channels; LAN destinations owner only (SSRF probe in test_injection_traversal)"),
    ("PATCH", "/v1/notifications/channels/{channel_id}"): Row(
        own_object(200), w.p_channel(body={"label": "renamed"}), "§12.14 own channels only"),
    ("DELETE", "/v1/notifications/channels/{channel_id}"): Row(own_object(204), w.p_channel(), "§12.14 own channels only"),
    ("POST", "/v1/notifications/channels/{channel_id}/test"): Row(
        own_object(200), w.p_channel("/test"), "§12.14 own channels only; rate-limited outbound request"),
    ("GET", "/v1/notifications/preferences"): Row(PEOPLE_READ, w.p_static("/v1/notifications/preferences"),
                                                  "§12.14 own preferences"),
    ("PUT", "/v1/notifications/preferences"): Row(PEOPLE_WRITE, w.p_preferences_put,
                                                  "§12.14 own preferences; a child holds no notifications:write"),
    ("POST", "/v1/notifications/send"): Row(
        cells(403, **GONE, agent=202, **PENDING_DENY), w.p_send,
        "§12.14 agents only, under their own plugin.<id> topic (the probe uses the static agent's)"),
    ("GET", "/v1/push/vapid-public-key"): Row(cells(200, **GONE, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                              w.p_static("/v1/push/vapid-public-key"), "§12.14 a public key, any principal"),
    ("POST", "/v1/push/registrations"): Row(
        cells(201, **GONE, child=403, **AGENTS_DENIED), w.p_device_create, "§12.14 people register their own devices"),
    ("GET", "/v1/push/registrations"): Row(PEOPLE_READ, w.p_static("/v1/push/registrations"), "§12.14 own devices"),
    ("DELETE", "/v1/push/registrations/{device_id}"): Row(own_object(204), w.p_device_delete, "§12.14 own devices"),
}

# ---- monitoring: feat/notify-monitor (contract §12.15) ---------------------------------------------------
POLICY |= {
    ("GET", "/v1/apps/{app_id}"): Row(cells(200, **GONE, child=404, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                      w.p_static(f"/v1/apps/{w.TARGET_APP}"),
                                      "§12.15 any principal; an app not shared with a child is 404 (§12.6)"),
    ("GET", "/v1/apps/{app_id}/logs"): Row(
        cells(403, **GONE, owner=404, adult=404, **PENDING_DENY), w.p_static(f"/v1/apps/{w.TARGET_APP}/logs"),
        "§12.15 owners and adults only (the probe app is not installed: 404); agents need a logs grant"),
    ("GET", "/v1/apps/{app_id}/metrics"): Row(CHILD_CANNOT, w.p_static(f"/v1/apps/{w.TARGET_APP}/metrics"),
                                              "§12.15 any principal, sharing applies; a child has no monitoring:read"),
    ("GET", "/v1/nodes/{node_id}/metrics"): Row(CHILD_CANNOT, w.p_node_metrics, "§12.15; a child has no monitoring:read"),
    ("GET", "/v1/monitoring/summary"): Row(CHILD_CANNOT, w.p_static("/v1/monitoring/summary"),
                                           "§12.15; a child has no monitoring:read"),
}

# ---- audit and events: feat/devsurface (contract §12.8, §12.16) -----------------------------------------
AUDIT_READ = cells(403, **GONE, owner=200, adult=200, agent=200, app_agent=200, **PENDING_DENY)
POLICY |= {
    ("GET", "/v1/audit/events"): Row(AUDIT_READ, w.p_static("/v1/audit/events"),
                                     "§12.16 owners and adults all; agents their own; guests and children never"),
    ("GET", "/v1/audit/events/{seq}"): Row(
        cells(403, **GONE, owner=200, adult=200, agent=404, app_agent=404, **PENDING_DENY), w.p_audit_record,
        "§12.16 the owner's record: an agent sees only its own (404)"),
    ("GET", "/v1/audit/verify"): Row(cells(403, **GONE, owner=200, adult=200, **PENDING_DENY), w.p_static("/v1/audit/verify"),
                                     "§12.16 full readers only: the head hash covers the whole chain"),
    ("GET", "/v1/events"): Row(CHILD_CANNOT, w.p_events, "§12.8 any principal, filtered per event; events:read not a child scope"),
}

# ---- routes added after the first matrix (rows follow docs/leap/dev/API.md and main's own tests) --------
# One line per route: owner, adult, guest, child, agent (an app's agent token answers like the static agent).
# A kind that cannot exist yet (plugin, automation, node) is DENIED where the agent is refused and DECIDE
# where it is allowed, so the stream that creates it writes the status down here.
WHO = "owner, adult, guest, child, agent"


def grid(owner, adult, guest, child, agent) -> dict:
    tail = DENIED if agent == 403 else DECIDE
    return cells(403, **GONE, owner=owner, adult=adult, guest=guest, child=child, agent=agent, app_agent=agent,
                 plugin=tail, automation=tail, node=tail)


OWNER_ONLY_404 = grid(404, 403, 403, 403, 403)   # owner reaches the (missing) object, nobody else does
READ_ANY_404 = grid(404, 404, 404, 403, 404)     # §5.5 "any": a missing object is 404 for every reader
READ_ANY = grid(200, 200, 200, 403, 200)
HOUSEHOLD = grid(200, 200, 403, 403, 200)        # backups/migrate reads: owner, adult, agent; not guests or children
HOUSEHOLD_404 = grid(404, 404, 403, 403, 404)
OWNER_ADULT = grid(200, 200, 403, 403, 403)      # databases, trash: owner and adult only
ONLY_OWNER = grid(200, 403, 403, 403, 403)
# A backup, restore or migration is a request: allowed callers file an action, the owner approves it. The matrix
# gateway runs with BACKUPS switched off, so a caller that reaches the service is told 503 "unavailable"
# (backups_disabled); the role gate that runs before the switch still answers 403 (test_backups.py has the
# switched-on paths).
OFF = grid(503, 503, 503, 403, 503)
OFF_OWNER_ONLY = grid(503, 403, 403, 403, 403)
OFF_HOUSEHOLD = grid(503, 503, 403, 403, 503)
# The restic REST data plane takes only a plan's scoped Basic credential, never a bearer token.
BASIC_ONLY = cells(401)

_AUTOMATION = "docs/leap/dev/API.md §5.5; core/tests/test_automation.py"
_BACKUPS = "docs/leap/dev/API.md §5.2 backups; core/tests/test_backups.py"
_FILES = "docs/leap/dev/API.md files; core/tests/test_files_*.py"
POLICY |= {
    # ---- automation, standing approvals and windows ------------------------------------------------------
    ("GET", "/v1/approval-policies"): Row(READ_ANY, w.p_static("/v1/approval-policies"), f"{_AUTOMATION}: any reader"),
    ("POST", "/v1/approval-policies"): Row(grid(201, 403, 403, 403, 403), w.p_policy_create,
                                           f"{_AUTOMATION}: only the owner grants a standing approval"),
    ("DELETE", "/v1/approval-policies/{policy_id}"): Row(OWNER_ONLY_404, w.p_missing("/v1/approval-policies/{policy}"),
                                                         f"{_AUTOMATION}: only the owner revokes one"),
    ("GET", "/v1/automation/rules"): Row(READ_ANY, w.p_static("/v1/automation/rules"), f"{_AUTOMATION}: any reader"),
    ("POST", "/v1/automation/rules"): Row(grid(201, 403, 403, 403, 403), w.p_rule_create,
                                          f"{_AUTOMATION}: only the owner writes rules (an agent is refused)"),
    ("GET", "/v1/automation/rules/{rule_id}"): Row(READ_ANY_404, w.p_missing("/v1/automation/rules/{rule}"),
                                                   f"{_AUTOMATION}: any reader"),
    ("PATCH", "/v1/automation/rules/{rule_id}"): Row(OWNER_ONLY_404, w.p_missing("/v1/automation/rules/{rule}", json={"name": "x"}),
                                                     f"{_AUTOMATION}: owner only"),
    ("POST", "/v1/automation/rules/{rule_id}/enable"): Row(OWNER_ONLY_404, w.p_missing("/v1/automation/rules/{rule}/enable"),
                                                           f"{_AUTOMATION}: owner only; nothing turns a rule on for itself"),
    ("POST", "/v1/automation/rules/{rule_id}/disable"): Row(grid(404, 403, 403, 403, 404), w.p_missing("/v1/automation/rules/{rule}/disable"),
                                                            f"{_AUTOMATION}: owner or agent (turning a rule off is always safe)"),
    ("DELETE", "/v1/automation/rules/{rule_id}"): Row(OWNER_ONLY_404, w.p_missing("/v1/automation/rules/{rule}"),
                                                      f"{_AUTOMATION}: owner only"),
    ("POST", "/v1/automation/rules/{rule_id}/dry-run"): Row(grid(404, 403, 403, 403, 404), w.p_missing("/v1/automation/rules/{rule}/dry-run", json={}),
                                                            f"{_AUTOMATION}: owner or agent; no side effects"),
    ("GET", "/v1/automation/runs"): Row(READ_ANY, w.p_static("/v1/automation/runs"), f"{_AUTOMATION}: any reader"),
    ("GET", "/v1/automation/schedules"): Row(READ_ANY, w.p_static("/v1/automation/schedules"), f"{_AUTOMATION}: any reader"),
    ("GET", "/v1/automation/state"): Row(READ_ANY, w.p_static("/v1/automation/state"), f"{_AUTOMATION}: any reader"),
    ("POST", "/v1/automation/pause"): Row(ONLY_OWNER, w.p_missing("/v1/automation/pause", json={}),
                                          "§12.5: agents never change the kill switch"),
    ("POST", "/v1/automation/resume"): Row(ONLY_OWNER, w.p_missing("/v1/automation/resume", json={}),
                                           "§12.5: agents never change the kill switch"),
    ("GET", "/v1/windows"): Row(READ_ANY, w.p_static("/v1/windows"), f"{_AUTOMATION}: any reader"),
    ("PUT", "/v1/windows/{window_id}"): Row(ONLY_OWNER, w.p_window_put, f"{_AUTOMATION}: only the owner edits windows"),
    # ---- backups and restores (an agent may request, never approve; reads are household only) ---------------
    ("GET", "/v1/backups/status"): Row(HOUSEHOLD, w.p_static("/v1/backups/status"), f"{_BACKUPS}: owner, adult, agent read"),
    ("GET", "/v1/backups/destinations"): Row(grid(200, 200, 403, 403, 403), w.p_static("/v1/backups/destinations"),
                                             f"{_BACKUPS}: destination labels are for owner and adult"),
    ("POST", "/v1/backups/destinations"): Row(grid(422, 403, 403, 403, 403),
                                              w.p_missing("/v1/backups/destinations", json={"kind": "usb", "label": "x", "config": {}}),
                                              f"{_BACKUPS}: only the owner changes where backups go"),
    ("DELETE", "/v1/backups/destinations/{dest_id}"): Row(OWNER_ONLY_404, w.p_missing("/v1/backups/destinations/{dest}"),
                                                          f"{_BACKUPS}: only the owner changes where backups go"),
    ("POST", "/v1/backups/runs"): Row(OFF, w.p_missing("/v1/backups/runs", json={}), f"{_BACKUPS}: request; owner approves"),
    ("GET", "/v1/backups/runs"): Row(HOUSEHOLD, w.p_static("/v1/backups/runs"), f"{_BACKUPS}: household read"),
    ("GET", "/v1/backups/runs/{run_id}"): Row(HOUSEHOLD_404, w.p_missing("/v1/backups/runs/{run}"), f"{_BACKUPS}: household read"),
    ("GET", "/v1/backups/snapshots"): Row(OFF_HOUSEHOLD, w.p_static("/v1/backups/snapshots"), f"{_BACKUPS}: household read"),
    ("GET", "/v1/backups/snapshots/{snapshot_id}"): Row(OFF_HOUSEHOLD, w.p_missing("/v1/backups/snapshots/{snap}"),
                                                        f"{_BACKUPS}: household read"),
    ("GET", "/v1/backups/snapshots/{snapshot_id}/tree"): Row(OFF_OWNER_ONLY, w.p_missing("/v1/backups/snapshots/{snap}/tree"),
                                                             f"{_BACKUPS}: browsing a snapshot's files is owner only"),
    ("GET", "/v1/backups/snapshots/{snapshot_id}/file"): Row(OFF_OWNER_ONLY, w.p_missing("/v1/backups/snapshots/{snap}/file?path=/a"),
                                                             f"{_BACKUPS}: reading a snapshot's files is owner only"),
    ("POST", "/v1/backups/verify"): Row(OFF, w.p_missing("/v1/backups/verify", json={}), f"{_BACKUPS}: request; owner approves"),
    ("GET", "/v1/backups/verifications"): Row(OFF_HOUSEHOLD, w.p_static("/v1/backups/verifications"), f"{_BACKUPS}: household read"),
    ("POST", "/v1/restores"): Row(OFF_OWNER_ONLY, w.p_missing("/v1/restores", json={"snapshot_id": "abcdef0123456789", "scope": {"app_id": "whoami"}}),
                                  f"{_BACKUPS}: only the owner asks for a restore"),
    ("GET", "/v1/restores"): Row(HOUSEHOLD, w.p_static("/v1/restores"), f"{_BACKUPS}: household read"),
    ("GET", "/v1/restores/{restore_id}"): Row(HOUSEHOLD_404, w.p_missing("/v1/restores/{restore}"), f"{_BACKUPS}: household read"),
    ("GET", "/v1/backups/kit"): Row(ONLY_OWNER, w.p_static("/v1/backups/kit"), f"{_BACKUPS}: the emergency kit is owner only"),
    ("POST", "/v1/backups/kit"): Row(OFF_OWNER_ONLY, w.p_static("/v1/backups/kit"), f"{_BACKUPS}: the emergency kit is owner only"),
    ("POST", "/v1/backups/kit/confirm"): Row(OWNER_ONLY_404, w.p_missing("/v1/backups/kit/confirm", json={"answers": {}}),
                                             f"{_BACKUPS}: the emergency kit is owner only"),
    # ---- first-run settings (contract 12.41) ----------------------------------------------------------------
    ("GET", "/v1/onboarding/settings"): Row(ONLY_OWNER, w.p_static("/v1/onboarding/settings"), "contract 12.41: owner only, audited"),
    ("PUT", "/v1/onboarding/settings"): Row(ONLY_OWNER, w.p_missing("/v1/onboarding/settings", json={
        "box_name": "home-hub", "time_zone": "UTC", "backup_choice": "later"}), "contract 12.41: owner only, audited"),
    # ---- apps, plans, databases -----------------------------------------------------------------------------
    ("GET", "/v1/databases"): Row(OWNER_ADULT, w.p_static("/v1/databases"), "owner and adult list databases; never a password"),
    ("GET", "/v1/apps/{app_id}/credentials"): Row(OWNER_ONLY_404, w.p_static(f"/v1/apps/{w.TARGET_APP}/credentials"),
                                                  "contract 12.40: the generated login is owner only"),
    ("GET", "/v1/apps/{app_id}/plan"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/plan"),
                                           "a preview of an install: any reader; a child sees only shared apps (404)"),
    ("POST", "/v1/plans"): Row(grid(200, 403, 403, 403, 200), w.p_missing("/v1/plans", json={"type": "app.install", "params": {"app_id": w.TARGET_APP}}),
                               "an owner or agent may preview an action; a plan changes nothing"),
    # ---- app store depth (contract 12.22) ---------------------------------------------------------------------
    ("GET", "/v1/apps/{app_id}/settings"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/settings"),
                                               "12.22: any reader; values only for owner and adult"),
    ("GET", "/v1/apps/{app_id}/dependencies"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/dependencies"), "12.22: any reader"),
    ("GET", "/v1/apps/{app_id}/host-ports"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/host-ports"), "12.22: any reader"),
    ("GET", "/v1/apps/{app_id}/exposure"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/exposure"), "12.22: any reader"),
    ("GET", "/v1/sources"): Row(READ_ANY, w.p_static("/v1/sources"), "12.22: any reader"),
    ("GET", "/v1/sources/{source_id}"): Row(READ_ANY_404, w.p_static("/v1/sources/src_00000000000000000000000000"), "12.22: any reader; missing is 404"),
    ("POST", "/v1/deploy/compose"): Row(grid(422, 403, 403, 403, 403), w.p_missing("/v1/deploy/compose", json={"app_id": "imp", "compose": "x"}),
                                        "12.22: Compose import is owner only; the probe's text is not Compose (422)"),
    # ---- files ----------------------------------------------------------------------------------------------
    ("GET", "/v1/files/roots"): Row(grid(200, 200, 200, 403, 200), w.p_static("/v1/files/roots"), f"{_FILES}: people list their spaces"),
    ("GET", "/v1/files/list"): Row(grid(200, 200, 200, 403, 403), w.p_static("/v1/files/list?root=shared&path=/"),
                                   f"{_FILES}: people browse; an agent needs a grant (none here)"),
    ("GET", "/v1/files/stat"): Row(grid(200, 200, 200, 403, 403), w.p_static("/v1/files/stat?root=shared&path=/"),
                                   f"{_FILES}: people browse; an agent needs a grant"),
    ("GET", "/v1/files/preview"): Row(grid(404, 404, 404, 403, 403), w.p_static("/v1/files/preview?root=shared&path=/a"),
                                      f"{_FILES}: people browse; an agent needs a grant"),
    ("GET", "/v1/files/download"): Row(grid(404, 404, 404, 403, 403), w.p_static("/v1/files/download?root=shared&path=/a"),
                                       f"{_FILES}: people browse; an agent needs a grant"),
    ("POST", "/v1/files/ops"): Row(grid(200, 200, 403, 403, 403), w.p_missing("/v1/files/ops", json={"op": "mkdir", "root": "shared", "path": "/probe"}),
                                   f"{_FILES}: owner and adult write; guests read only; an agent needs a grant"),
    ("GET", "/v1/files/trash"): Row(OWNER_ADULT, w.p_static("/v1/files/trash"), f"{_FILES}: owner and adult"),
    ("GET", "/v1/files/quotas"): Row(ONLY_OWNER, w.p_static("/v1/files/quotas"), f"{_FILES}: owner only"),
    ("PUT", "/v1/files/quotas/{person_id}"): Row(ONLY_OWNER, w.p_missing("/v1/files/quotas/owner", json={"limit_bytes": 1}),
                                                 f"{_FILES}: owner only"),
    ("POST", "/v1/files/grants"): Row(grid(202, 403, 403, 403, 403), w.p_missing(
        "/v1/files/grants", json={"subject": {"kind": "app", "id": "whoami"}, "root": "shared", "path": "/", "access": "r"}),
        f"{_FILES}: only the owner asks to open files to an app or agent, and it waits for approval"),
    ("POST", "/v1/files/trash/empty"): Row(grid(202, 202, 403, 403, 403), w.p_missing("/v1/files/trash/empty", json={}),
                                           f"{_FILES}: owner and adult request; destroying needs approval"),
    ("GET", "/v1/files/requests"): Row(READ_ANY, w.p_static("/v1/files/requests"), f"{_FILES}: each sees their own"),
    ("GET", "/v1/files/requests/{request_id}"): Row(READ_ANY_404, w.p_missing("/v1/files/requests/{request}"), f"{_FILES}: each sees their own"),
    ("POST", "/v1/files/requests/{request_id}/approve"): Row(OWNER_ONLY_404, w.p_missing("/v1/files/requests/{request}/approve"),
                                                             f"{_FILES}: only the owner approves; agents never"),
    ("POST", "/v1/files/requests/{request_id}/deny"): Row(OWNER_ONLY_404, w.p_missing("/v1/files/requests/{request}/deny"),
                                                          f"{_FILES}: only the owner denies"),
    ("POST", "/v1/files/requests/{request_id}/cancel"): Row(READ_ANY_404, w.p_missing("/v1/files/requests/{request}/cancel"),
                                                            f"{_FILES}: a requester cancels their own"),
    ("GET", "/v1/files/grants"): Row(READ_ANY, w.p_static("/v1/files/grants"), f"{_FILES}: each sees their own"),
    ("DELETE", "/v1/files/grants/{grant_id}"): Row(READ_ANY_404, w.p_missing("/v1/files/grants/{grant}"), f"{_FILES}: revoking what you hold"),
    ("OPTIONS", "/v1/files/uploads"): Row(cells(204), w.p_static("/v1/files/uploads"), "tus capability discovery is open and read only"),
    ("POST", "/v1/files/uploads"): Row(grid(201, 201, 403, 403, 403), w.p_missing(
        "/v1/files/uploads", headers={**w.TUS, "Upload-Length": "1", "Upload-Metadata": w.UPLOAD_META}),
        f"{_FILES}: owner and adult upload; guests read only; an agent needs a grant"),
    ("HEAD", "/v1/files/uploads/{upload_id}"): Row(READ_ANY_404, w.p_missing("/v1/files/uploads/{upload}", headers=w.TUS), f"{_FILES}: your own upload"),
    ("GET", "/v1/files/uploads/{upload_id}"): Row(READ_ANY_404, w.p_missing("/v1/files/uploads/{upload}"), f"{_FILES}: your own upload"),
    ("PATCH", "/v1/files/uploads/{upload_id}"): Row(READ_ANY_404, w.p_missing(
        "/v1/files/uploads/{upload}", content=b"x",
        headers={**w.TUS, "Content-Type": "application/offset+octet-stream", "Upload-Offset": "0"}), f"{_FILES}: your own upload"),
    ("DELETE", "/v1/files/uploads/{upload_id}"): Row(READ_ANY_404, w.p_missing("/v1/files/uploads/{upload}", headers=w.TUS), f"{_FILES}: your own upload"),
    # ---- migration (another cluster's namespace comes in; the owner decides every step) -----------------------
    ("POST", "/v1/migrate/plans"): Row(grid(422, 403, 403, 403, 403), w.p_missing(
        "/v1/migrate/plans", json={"kubeconfig": w.KUBECONFIG, "namespace": "old"}), "only the owner reads another cluster"),
    ("GET", "/v1/migrate/plans"): Row(HOUSEHOLD, w.p_static("/v1/migrate/plans"), "household read"),
    ("GET", "/v1/migrate/plans/{plan_id}"): Row(HOUSEHOLD_404, w.p_missing("/v1/migrate/plans/{plan}"), "household read"),
    ("GET", "/v1/migrate/plans/{plan_id}/helper"): Row(grid(422, 422, 422, 403, 422), w.p_missing("/v1/migrate/plans/{plan}/helper"),
                                                       "the helper script needs its own query parameters before any role is checked"),
    ("POST", "/v1/migrate/plans/{plan_id}/import"): Row(OWNER_ONLY_404, w.p_missing("/v1/migrate/plans/{plan}/import", json={}),
                                                        "a request the owner approves; only the owner files it"),
    ("POST", "/v1/migrate/plans/{plan_id}/copy"): Row(OWNER_ONLY_404, w.p_missing("/v1/migrate/plans/{plan}/copy", json={"kubeconfig": w.KUBECONFIG}),
                                                      "a request the owner approves; only the owner files it"),
    ("POST", "/v1/migrate/plans/{plan_id}/cutover"): Row(OWNER_ONLY_404, w.p_missing("/v1/migrate/plans/{plan}/cutover", json={"kubeconfig": w.KUBECONFIG}),
                                                         "a request the owner approves; only the owner files it"),
    ("POST", "/v1/migrate/plans/{plan_id}/revert"): Row(OWNER_ONLY_404, w.p_missing("/v1/migrate/plans/{plan}/revert", json={"kubeconfig": w.KUBECONFIG}),
                                                        "a request the owner approves; only the owner files it"),
}
_REPO = "the restic data plane takes only a plan's scoped Basic credential, never a bearer token"
POLICY |= {
    (m, p): Row(BASIC_ONLY, w.p_missing(path, content=b"x" if m == "POST" and ("{name}" in p or p.endswith("/config")) else None),
                _REPO, challenge="basic")
    for (m, p, path) in [
        ("POST", "/v1/migrate/repo/{plan_id}", "/v1/migrate/repo/{plan}?create=true"),
        ("POST", "/v1/migrate/repo/{plan_id}/", "/v1/migrate/repo/{plan}/?create=true"),
        ("GET", "/v1/migrate/repo/{plan_id}/config", "/v1/migrate/repo/{plan}/config"),
        ("HEAD", "/v1/migrate/repo/{plan_id}/config", "/v1/migrate/repo/{plan}/config"),
        ("POST", "/v1/migrate/repo/{plan_id}/config", "/v1/migrate/repo/{plan}/config"),
        ("GET", "/v1/migrate/repo/{plan_id}/{typ}/", "/v1/migrate/repo/{plan}/data/"),
        ("GET", "/v1/migrate/repo/{plan_id}/{typ}/{name}", "/v1/migrate/repo/{plan}/data/ab"),
        ("HEAD", "/v1/migrate/repo/{plan_id}/{typ}/{name}", "/v1/migrate/repo/{plan}/data/ab"),
        ("POST", "/v1/migrate/repo/{plan_id}/{typ}/{name}", "/v1/migrate/repo/{plan}/data/ab"),
        ("DELETE", "/v1/migrate/repo/{plan_id}/{typ}/{name}", "/v1/migrate/repo/{plan}/data/ab"),
    ]
}
