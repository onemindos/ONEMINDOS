# SPDX-License-Identifier: Apache-2.0
"""THE authorization policy table: every gateway route x every principal kind -> expected status.
Part of board item CORE-SEC-11 (security suite).

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
from onemind_core.natsconf import new_user_key
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
    if "teen" not in over:
        out["teen"] = out["child"]  # FAM-01: a teen holds the same API scopes as a child; rows override with teen=
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
    ("GET", "/v1/instance/name"): Row(OPEN, w.p_static("/v1/instance/name"), "the box name alone, so the sign-in page can show it"),
    ("GET", "/v1/protocol"): Row(OPEN, w.p_static("/v1/protocol"), "protocol generations served (#697), so an app too old to sign in can say Update needed"),
    ("GET", "/openapi.json"): Row(OPEN, w.p_static("/openapi.json"), "§3 OpenAPI is published"),
    ("HEAD", "/openapi.json"): Row(OPEN, w.p_static("/openapi.json"), "§3 OpenAPI is published"),
    ("GET", "/{full_path:path}"): Row(OPEN, w.p_static("/"), "§3 static dashboard with SPA fallback"),
    # ---- reads (§3) ---------------------------------------------------------------------------------
    ("GET", "/v1/instance"): Row(ANY_PRINCIPAL, w.p_static("/v1/instance"), "§3; §12.6 instance:read for all"),
    ("GET", "/v1/nodes"): Row(CHILD_CANNOT, w.p_static("/v1/nodes"), "§3; §12.6 child has no nodes:read"),
    ("GET", "/v1/nodes/{node_id}"): Row(CHILD_CANNOT, w.p_node, "§3; §12.6 child has no nodes:read"),
    ("GET", "/v1/nodes/{node_id}/wake"): Row(CHILD_CANNOT, lambda world: w.Req(f"/v1/nodes/{world.heartbeat()}/wake"),
                                             "#251 wake availability only; nodes:read, no actuation"),
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
    # #702 phone approver keys: registering needs an owner session with a fresh passkey (a child is refused
    # and audited; static tokens hold no session); listing and revoking are the caller's own keys.
    ("POST", "/v1/auth/approver-keys"): Row(cells(403, **GONE, **PENDING_DENY), w.p_approver_key,
                                            "#702 an owner session with a fresh passkey", ID, UNAUDITED),
    ("GET", "/v1/auth/approver-keys"): Row(own_credentials(200), w.p_static("/v1/auth/approver-keys"),
                                           "#702 own approver keys", ID, UNAUDITED),
    ("DELETE", "/v1/auth/approver-keys/{key_id}"): Row(own_credentials(404), w.p_static("/v1/auth/approver-keys/apk_none"),
                                                       "#702 own approver keys", ID, UNAUDITED),
    ("GET", "/v1/auth/methods"): Row(own_credentials(200), w.p_static("/v1/auth/methods"), "§12.6 own sign-in methods", ID, UNAUDITED),
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
    # D-014 rescue console step-up: the owner is refused only on the merits (no passkey on the box: 409; a bad
    # assertion: 401), every other principal 403. They open nothing, so there is no 200 for anyone.
    ("POST", "/v1/auth/rescue/options"): Row({**OWNER_ONLY, "owner": 409}, w.p_rescue_options,
                                              "D-014 owner; 409 until a passkey is registered", ID),
    ("POST", "/v1/auth/rescue/verify"): Row({**OWNER_ONLY, "owner": 401}, w.p_rescue_verify,
                                             "D-014 owner; the probe's assertion does not verify", ID),
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
    ("GET", "/v1/notifications/summary"): Row(PEOPLE_READ, w.p_static("/v1/notifications/summary"),
                                              "§12.14 own unread summary (#682), people only"),
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
    ("GET", "/v1/notifications/sources"): Row(PEOPLE_READ, w.p_static("/v1/notifications/sources"),
                                              "§12.14 #613 people read the notification sources (App notifications page)"),
    ("PUT", "/v1/notifications/sources/{source_id}"): Row(
        cells(403, **GONE, owner=200, **PENDING_DENY),
        lambda _: w.Req("/v1/notifications/sources/plugin:probe", json={"muted": True}),
        "§12.14 #613 only owners mute or unmute a source; an agent never lifts its own mute"),
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
    ("GET", "/v1/metrics"): Row(CHILD_CANNOT, w.p_static("/v1/metrics"),
                                "Prometheus text of node, app and alert numbers; a child has no monitoring:read"),
    ("GET", "/v1/map/packs"): Row(cells(200, **GONE, child=403, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                  w.p_static("/v1/map/packs"),
                                  "Map uses nodes:read; no pack volume is configured in the security fixture, so the list is empty"),
    ("GET", "/v1/work/tasks"): Row(cells(403, **GONE, owner=200, adult=200, child=200),
                                    w.p_static("/v1/work/tasks"), "Work lists only visible tasks"),
    ("GET", "/v1/work/projects/{project_id}/tasks/{task_id}"): Row(
        cells(403, **GONE, owner=404, adult=404, child=404),
        w.p_static("/v1/work/projects/missing/tasks/missing"), "Work hides missing and other users' tasks"),
    ("POST", "/v1/work/projects"): Row(cells(403, **GONE, owner=422, adult=422, child=422),
                                         w.p_static("/v1/work/projects"), "Work project creation is people-only"),
    ("POST", "/v1/work/capture"): Row(cells(403, **GONE, owner=422, adult=422, child=422),
                                        w.p_static("/v1/work/capture"), "Work capture is people-only"),
    ("POST", "/v1/work/quick-add"): Row(cells(403, **GONE, owner=422, adult=422, child=422),
                                          w.p_static("/v1/work/quick-add"), "Work quick-add is people-only"),
    ("PATCH", "/v1/work/projects/{project_id}/tasks/{task_id}"): Row(
        cells(403, **GONE, owner=422, adult=422, child=422),
        w.p_static("/v1/work/projects/missing/tasks/missing"), "Work revision edits are people-only"),
    ("DELETE", "/v1/work/projects/{project_id}/tasks/{task_id}"): Row(
        cells(403, **GONE, owner=422, adult=422, child=422),
        w.p_static("/v1/work/projects/missing/tasks/missing"), "Work revision deletion is people-only"),
    ("GET", "/v1/series"): Row(CHILD_CANNOT, w.p_static("/v1/series?node_id=node1&metric=cpu_pct"),
                               "Node metric history, with the same monitoring:read scope as live metrics"),
    ("GET", "/v1/monitoring/summary"): Row(CHILD_CANNOT, w.p_static("/v1/monitoring/summary"),
                                           "§12.15; a child has no monitoring:read"),
    # UMB-P11 (#429): the heartbeat numbers /v1/nodes shows plus per-app usage; sharing filters the apps.
    ("GET", "/v1/usage"): Row(CHILD_CANNOT, w.p_static("/v1/usage"),
                              "UMB-P11 live usage: read-only, monitoring:read like app metrics (a child has none); unshared apps are left out"),
    # #619 Engine feed: read-only NATS monitor numbers. The owner sees all; a node its own account, link and outbox
    # (nodes:report); adults, guests and agents a summary; plugins and automations nothing.
    ("GET", "/v1/engine"): Row(cells(200, **GONE, child=403, plugin=403, automation=403, node=200), w.p_static("/v1/engine"),
                               "#619 engine feed: monitoring:read (a child has none) or a node's nodes:report; scope cut in engine/feed.py"),
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
    ("GET", "/v1/me/dashboard-card"): Row(
        cells(403, **GONE, owner=200, adult=200, guest=200, child=200), w.p_static("/v1/me/dashboard-card"),
        "#667 each person reads only their own saved card; no card yet"),
    ("PUT", "/v1/me/dashboard-card"): Row(
        cells(403, **GONE, owner=200, adult=200),
        lambda world: w.Req("/v1/me/dashboard-card", json={"source": {"kind": "subject", "subject": "onemind.event.backup.run.finished"}}),
        "#667 save checks the domain scope; guests and children have no backups:read"),
    ("GET", "/v1/me/dashboard-card/events"): Row(
        cells(403, **GONE, owner=404, adult=404, guest=404, child=404),
        w.p_static("/v1/me/dashboard-card/events"), "#667 the person's own stream requires a saved card"),

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
_WOPI = "issue #675; core/tests/test_files_wopi.py"
_WOPI_FILE = "/v1/files/wopi/files/wf_0123456789abcdef"
_PHOTOS = "docs/leap/core/PHOTOS.md section 2; core/tests/test_photos.py"
PHOTOS_404 = grid(404, 404, 403, 403, 403)  # owner and adult own a library; a missing object is 404 for them
_TIPS = "issue #669; core/tests/test_tips.py"
POLICY |= {
    # ---- automation, standing approvals and windows ------------------------------------------------------
    ("GET", "/v1/approval-policies"): Row(ONLY_OWNER, w.p_static("/v1/approval-policies"),
                                          f"{_AUTOMATION}: only the owner reads the rules (gateway permissions gap 3)"),
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
    # ---- AI agent principals (AIG-03 #167): the owner's budget, cancel and resume controls -------------------------
    ("GET", "/v1/agents"): Row(ONLY_OWNER, w.p_static("/v1/agents"), "AIG-03: only the owner lists agents"),
    ("GET", "/v1/agents/{name}"): Row(ONLY_OWNER, w.p_static("/v1/agents/hermes"), "AIG-03: only the owner reads an agent"),
    ("PUT", "/v1/agents/{name}/budget"): Row(ONLY_OWNER, w.p_missing("/v1/agents/hermes/budget", json={"budget_per_day": 50}),
                                             "AIG-03: an agent never raises its own budget"),
    ("POST", "/v1/agents/{name}/cancel"): Row(ONLY_OWNER, w.p_missing("/v1/agents/hermes/cancel", json={}),
                                              "AIG-03: only the owner cancels an agent"),
    ("POST", "/v1/agents/{name}/resume"): Row(ONLY_OWNER, w.p_missing("/v1/agents/hermes/resume", json={}),
                                              "AIG-03: an agent never resumes itself"),
    # #627: an agent's NATS user (account AGENTS) is the owner's to add or remove; an agent never keys itself
    ("GET", "/v1/agents/{name}/nats-key"): Row(ONLY_OWNER, w.p_static("/v1/agents/agent:probe/nats-key"),
                                               "#627: only the owner reads an agent's NATS key"),
    ("PUT", "/v1/agents/{name}/nats-key"): Row(ONLY_OWNER, w.p_missing("/v1/agents/agent:probe/nats-key", json={
        "nkey": new_user_key()[1]}), "#627: an agent never registers its own NATS key"),
    ("DELETE", "/v1/agents/{name}/nats-key"): Row(ONLY_OWNER, w.p_missing("/v1/agents/agent:probe/nats-key"),
                                                  "#627: only the owner removes an agent's NATS key"),
    ("GET", "/v1/windows"): Row(READ_ANY, w.p_static("/v1/windows"), f"{_AUTOMATION}: any reader"),
    ("PUT", "/v1/windows/{window_id}"): Row(ONLY_OWNER, w.p_window_put, f"{_AUTOMATION}: only the owner edits windows"),
    # ---- update policy for apps (NMD-07, #132: core/onemind_core/routers/updatepolicy.py) -------------------
    ("GET", "/v1/update-policy"): Row(READ_ANY, w.p_static("/v1/update-policy"), "NMD-07: any reader sees the knobs"),
    ("PUT", "/v1/update-policy"): Row(ONLY_OWNER, w.p_missing("/v1/update-policy", json={}),
                                      "NMD-07: only the owner changes the update policy"),
    ("GET", "/v1/update-policy/dry-run"): Row(READ_ANY, w.p_static("/v1/update-policy/dry-run"),
                                              "NMD-07: any reader sees what would update; it files nothing"),
    ("POST", "/v1/update-policy/resume"): Row(ONLY_OWNER, w.p_missing("/v1/update-policy/resume", json={"app_id": "whoami"}),
                                              "NMD-07: only the owner lifts a back-off"),
    # ---- backups and restores (an agent may request, never approve; reads are household only) ---------------
    ("GET", "/v1/care/checkup"): Row(OWNER_ONLY, w.p_static("/v1/care/checkup"), "FD-08 owner-only box check-up"),
    ("GET", "/v1/status"): Row(HOUSEHOLD, w.p_static("/v1/status"),
                               "FD-01: needs-attention view; owner, adult, agent read; guest and child 403"),
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
    ("GET", "/v1/backups/content"): Row(OFF_HOUSEHOLD, w.p_static("/v1/backups/content"),
                                        f"{_BACKUPS}: household read of the content tier and its size (BAK-03)"),
    ("POST", "/v1/backups/content"): Row(OFF_OWNER_ONLY, w.p_missing("/v1/backups/content", json={"app_id": "whoami", "enabled": False}),
                                         f"{_BACKUPS}: only the owner switches the content tier (BAK-03)"),
    ("POST", "/v1/restores"): Row(OFF_OWNER_ONLY, w.p_missing("/v1/restores", json={"snapshot_id": "abcdef0123456789", "scope": {"app_id": "whoami"}}),
                                  f"{_BACKUPS}: only the owner asks for a restore"),
    ("GET", "/v1/restores"): Row(HOUSEHOLD, w.p_static("/v1/restores"), f"{_BACKUPS}: household read"),
    ("GET", "/v1/restores/{restore_id}"): Row(HOUSEHOLD_404, w.p_missing("/v1/restores/{restore}"), f"{_BACKUPS}: household read"),
    ("GET", "/v1/backups/kit"): Row(ONLY_OWNER, w.p_static("/v1/backups/kit"), f"{_BACKUPS}: the emergency kit is owner only"),
    ("POST", "/v1/backups/kit"): Row(OFF_OWNER_ONLY, w.p_static("/v1/backups/kit"), f"{_BACKUPS}: the emergency kit is owner only"),
    ("POST", "/v1/backups/kit/confirm"): Row(OWNER_ONLY_404, w.p_missing("/v1/backups/kit/confirm", json={"answers": {}}),
                                             f"{_BACKUPS}: the emergency kit is owner only"),
    # ---- first-run settings (contract 12.41) ----------------------------------------------------------------
    ("GET", "/v1/onboarding/state"): Row(ONLY_OWNER, w.p_static("/v1/onboarding/state"), "contract 12.41: owner only, read-only wizard state"),
    ("GET", "/v1/onboarding/settings"): Row(ONLY_OWNER, w.p_static("/v1/onboarding/settings"), "contract 12.41: owner only, audited"),
    ("PUT", "/v1/onboarding/settings"): Row(ONLY_OWNER, w.p_missing("/v1/onboarding/settings", json={
        "box_name": "home-hub", "time_zone": "UTC", "backup_choice": "later"}), "contract 12.41: owner only, audited"),
    ("POST", "/v1/onboarding/restore/candidates"): Row(OFF_OWNER_ONLY, w.p_missing("/v1/onboarding/restore/candidates", json={
        "destination_id": "dst_0123456789abcdef"}), "UMB-P08: first-run restore listing is owner only (503: backups off in the matrix)"),
    ("POST", "/v1/onboarding/restore/apps"): Row(OFF_OWNER_ONLY, w.p_missing("/v1/onboarding/restore/apps", json={
        "destination_id": "dst_0123456789abcdef", "box_id": "old-box", "recovery_key": "K" * 40, "run_id": "run_old",
        "app_id": "notes"}), "UMB-P08: restoring an app from another box's backup is owner only (503: backups off in the matrix)"),
    # ---- the person's own Home (UMB-P07, #144) --------------------------------------------------------------
    # Every person has one (child included); an agent has none. The write is probed without If-Match, so a
    # person who is let in gets 428: the route never reaches the store without a validator.
    ("GET", "/v1/me/home"): Row(grid(200, 200, 200, 200, 403), w.p_static("/v1/me/home"),
                                "desktop-ui.md 4.3: a person reads only their own Home; agents have none"),
    ("PUT", "/v1/me/home"): Row(grid(428, 428, 428, 428, 403), w.p_missing("/v1/me/home", json={}),
                                "desktop-ui.md 4.3: a person writes only their own Home; If-Match is required"),
    ("PATCH", "/v1/me"): Row(grid(403, 403, 403, 200, 403), w.p_missing("/v1/me", json={"display_name": "Probe"}),
                             "a person with a stored account (the household child here) sets only their own display name; the static token "
                             "probes have no account row to name (the signed-in 200 paths are in test_identity.py)", ID),
    # ---- My devices (#715): a person's own session only; the static-token probes and agents hold none --------
    ("GET", "/v1/me/devices"): Row(own_credentials(200), w.p_static("/v1/me/devices"),
                                   "#715 a signed-in person lists their own devices", ID),
    ("DELETE", "/v1/me/devices/{device_id}"): Row(own_credentials(200), w.p_static("/v1/me/devices/mdv_no_such_device"),
                                                  "#715 Lost this device: a person's own session; an id that is gone is a "
                                                  "no-op 200 (idempotent)", ID),
    # ---- apps, plans, databases -----------------------------------------------------------------------------
    ("GET", "/v1/databases"): Row(OWNER_ADULT, w.p_static("/v1/databases"), "owner and adult list databases; never a password"),
    ("GET", "/v1/apps/{app_id}/credentials"): Row(OWNER_ONLY_404, w.p_static(f"/v1/apps/{w.TARGET_APP}/credentials"),
                                                  "contract 12.40: the generated login is owner only"),
    # ---- app secrets and the F-7 override (docs/leap/core/SECRETS.md) ---------------------------------------
    ("GET", "/v1/secrets/public-key"): Row(grid(200, 200, 200, 403, 200), w.p_static("/v1/secrets/public-key"),
                                           "the public half of the box's sealing key: any reader; a child has no scope for it (403)"),
    ("GET", "/v1/apps/{app_id}/secrets"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/secrets"),
                                              "key names and set flags, never a value; follows per-app sharing (404)"),
    ("POST", "/v1/apps/{app_id}/secrets"): Row(grid(409, 403, 403, 403, 403), w.p_missing(f"/v1/apps/{w.TARGET_APP}/secrets", json={}),
                                               "owner only (409: this fixture app declares no secrets); nobody else"),
    ("GET", "/v1/apps/{app_id}/owner-override"): Row(grid(200, 403, 403, 403, 403), w.p_static(f"/v1/apps/{w.TARGET_APP}/owner-override"),
                                                     "F-7 approval-card info: owner only"),
    ("GET", "/v1/apps/{app_id}/plan"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/plan"),
                                           "a preview of an install: any reader; a child sees only shared apps (404)"),
    ("POST", "/v1/plans"): Row(grid(200, 403, 403, 403, 200), w.p_missing("/v1/plans", json={"type": "app.install", "params": {"app_id": w.TARGET_APP}}),
                               "an owner or agent may preview an action; a plan changes nothing"),
    # ---- app store depth (contract 12.22) ---------------------------------------------------------------------
    ("GET", "/v1/apps/{app_id}/settings"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/settings"),
                                               "12.22: any reader; values only for owner and adult"),
    ("GET", "/v1/apps/{app_id}/dependencies"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/dependencies"), "12.22: any reader"),
    ("GET", "/v1/apps/{app_id}/host-ports"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/host-ports"), "12.22: any reader"),
    ("GET", "/v1/apps/{app_id}/placement"): Row(CHILD_CANNOT, w.p_static(f"/v1/apps/{w.TARGET_APP}/placement"),
                                                "12.11 CORE-FABRIC-4: names the machines, so nodes:read like /v1/nodes"),
    ("GET", "/v1/apps/{app_id}/exposure"): Row(grid(200, 200, 200, 404, 200), w.p_static(f"/v1/apps/{w.TARGET_APP}/exposure"), "12.22: any reader"),
    ("GET", "/v1/system-apps"): Row(grid(200, 200, 200, 200, 200), w.p_static("/v1/system-apps"),
                                    "built-in apps list: any reader; a child or agent sees only the apps shared with them, as in /v1/apps"),
    ("GET", "/v1/settings/photos"): Row(grid(200, 200, 200, 404, 404), w.p_static("/v1/settings/photos"),
                                          "Photos visibility follows /v1/system-apps; only owners with approval scope see pending IDs"),
    ("PUT", "/v1/settings/photos"): Row(grid(202, 403, 403, 403, 403), w.p_missing("/v1/settings/photos", json={"enabled": False}),
                                          "only an owner may ask to switch Photos; it files app.disable/app.enable for approval"),
    ("GET", "/v1/builtins"): Row(grid(200, 200, 200, 200, 200), w.p_static("/v1/builtins"),
                                 "#603 built-in descriptors: any reader; a child or agent sees only the apps shared with them"),
    # ---- share (Send to, #612; core/tests/test_share.py) -------------------------------------------------------
    ("GET", "/v1/share/types"): Row(grid(200, 200, 200, 200, 200), w.p_static("/v1/share/types"), "#612 share type registry: any reader"),
    ("GET", "/v1/share/targets"): Row(grid(200, 200, 200, 200, 200), w.p_static("/v1/share/targets?type=file"),
                                      "#612 Send to list: any reader; each sees only the apps shared with them"),
    ("POST", "/v1/share"): Row(grid(201, 201, 403, 403, 403), w.p_missing(
        "/v1/share", json={"to": "files", "verb": "open", "object": {"type": "file", "ref": "shared:probe.txt"}}),
        "#612: an owner or adult hands an object to an app; an agent only drafts (AI never actuates)"),
    ("GET", "/v1/surfaces"): Row(grid(200, 200, 200, 200, 200), w.p_static("/v1/surfaces"),
                                 "#605 surface registry: any reader; a child or agent sees only the apps shared with them"),
    ("GET", "/v1/sources"): Row(READ_ANY, w.p_static("/v1/sources"), "12.22: any reader"),
    ("GET", "/v1/sources/{source_id}"): Row(READ_ANY_404, w.p_static("/v1/sources/src_00000000000000000000000000"), "12.22: any reader; missing is 404"),
    ("GET", "/v1/custom-apps"): Row(ONLY_OWNER, w.p_static("/v1/custom-apps"), "PLG-GIT-01: repository URLs and deploy history are the owner's"),
    ("GET", "/v1/custom-apps/{app_id}"): Row(OWNER_ONLY_404, w.p_static("/v1/custom-apps/no-such-app"), "PLG-GIT-01: owner only; missing is 404"),
    ("POST", "/v1/custom-apps/plan"): Row(grid(422, 403, 403, 403, 403), w.p_missing("/v1/custom-apps/plan", json={"url": "http://x.invalid/r", "ref": "main"}),
                                          "PLG-GIT-01: planning fetches a repository, so owner only; the probe's http URL is refused (422) before any fetch"),
    ("POST", "/v1/custom-apps/{app_id}/rollback"): Row(OWNER_ONLY_404, w.p_missing("/v1/custom-apps/no-such-app/rollback", json={}),
                                                       "PLG-GIT-01: owner only; a missing custom app is 404"),
    ("POST", "/v1/deploy/compose"): Row(grid(422, 403, 403, 403, 403), w.p_missing("/v1/deploy/compose", json={"app_id": "imp", "compose": "x"}),
                                        "12.22: Compose import is owner only; the probe's text is not Compose (422)"),
    # ---- files ----------------------------------------------------------------------------------------------
    ("GET", "/v1/files/roots"): Row(grid(200, 200, 200, 403, 200), w.p_static("/v1/files/roots"), f"{_FILES}: people list their spaces"),
    ("GET", "/v1/files/list"): Row(grid(200, 200, 200, 403, 403), w.p_static("/v1/files/list?root=shared&path=/"),
                                   f"{_FILES}: people browse; an agent needs a grant (none here)"),
    ("GET", "/v1/files/stat"): Row(grid(200, 200, 200, 403, 403), w.p_static("/v1/files/stat?root=shared&path=/"),
                                   f"{_FILES}: people browse; an agent needs a grant"),
    ("GET", "/v1/search"): Row(grid(200, 200, 200, 200, 200), w.p_static("/v1/search?q=report"),
                               "#611 global search: any signed-in caller; each hit is filtered by the caller's own grants"),
    ("GET", "/v1/sync/changes"): Row(grid(200, 200, 200, 403, 403), w.p_static("/v1/sync/changes?root=shared"),
                                     f"{_FILES}: the change feed (#698) follows read access to the whole root"),
    ("POST", "/v1/sync/chunks/missing"): Row(grid(200, 200, 403, 403, 403), w.p_missing(
        "/v1/sync/chunks/missing", json={"root": "shared", "hashes": ["0" * 64]}),
        f"{_FILES}: sending a file (#699) needs write access to the root; guests read Shared only"),
    ("PUT", "/v1/sync/chunks/{chunk_hash}"): Row(grid(200, 200, 403, 403, 403), w.p_missing(
        "/v1/sync/chunks/2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881?root=shared", content=b"x"),
        f"{_FILES}: a chunk (#699) needs write access to the root"),
    ("POST", "/v1/sync/commit"): Row(grid(404, 404, 403, 403, 403), w.p_missing("/v1/sync/commit", json={
        "root": "shared", "path": "/no-such-folder/probe", "size": 0,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "chunks": []}),
        f"{_FILES}: a commit (#699) needs write access to the entry; the probe's folder is missing (404)"),
    ("POST", "/v1/sync/locks"): Row(grid(404, 404, 403, 403, 403), w.p_missing("/v1/sync/locks", json={"root": "shared", "path": "/no-such-file"}),
                                   f"{_FILES}: an advisory lock (#699) is a write intent; the probe's file is missing (404)"),
    ("GET", "/v1/sync/locks"): Row(grid(200, 200, 200, 403, 403), w.p_static("/v1/sync/locks?root=shared"),
                                  f"{_FILES}: locks (#699) follow read access to the path"),
    ("POST", "/v1/sync/locks/{lock_id}/refresh"): Row(grid(404, 404, 404, 403, 404), w.p_missing(
        "/v1/sync/locks/lck_00000000000000000000000000/refresh", json={}), f"{_FILES}: only the holder refreshes (none here)"),
    ("DELETE", "/v1/sync/locks/{lock_id}"): Row(grid(404, 404, 404, 403, 404), w.p_missing(
        "/v1/sync/locks/lck_00000000000000000000000000"), f"{_FILES}: the holder or an owner releases (none here)"),
    ("GET", "/v1/sync/versions"): Row(grid(404, 404, 404, 403, 403), w.p_static("/v1/sync/versions?root=shared&path=/a"),
                                      f"{_FILES}: versions (#699) follow read access; the probe's file is missing"),
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
    # #693 browser downloads in quarantine: people see their own (owners all); only an owner asks to release one.
    ("GET", "/v1/files/downloads"): Row(grid(200, 200, 200, 403, 403), w.p_static("/v1/files/downloads"),
                                        f"{_FILES}: each person their own held downloads, an owner all; agents refused"),
    ("POST", "/v1/files/downloads/{download_id}/release"): Row(OWNER_ONLY_404, w.p_missing("/v1/files/downloads/{download}/release"),
                                                              f"{_FILES}: only an owner asks; an owner approves the action"),
    ("DELETE", "/v1/files/downloads/{download_id}"): Row(grid(404, 404, 404, 403, 403), w.p_missing("/v1/files/downloads/{download}"),
                                                         f"{_FILES}: the person who downloaded it or an owner; others see 404"),
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
    # ---- WOPI host (#675): like every /v1/files/* route the token route needs the "*" scope, so the child (a household
    # session) is refused by scope; only a signed-in person's session mints a file token, so the static tokens file,
    # API tokens and agents are 403 too. The WOPI operations take only that file token (access_token), never a bearer
    # token, so every column is 401.
    ("POST", "/v1/files/wopi/tokens"): Row(grid(403, 403, 403, 403, 403), w.p_missing(
        "/v1/files/wopi/tokens", json={"root": "shared", "path": "/probe.docx"}), f"{_WOPI}: the owner's own signed-in editor only"),
    ("GET", "/v1/files/wopi/files/{file_id}"): Row(cells(401), w.p_static(_WOPI_FILE), f"{_WOPI}: CheckFileInfo takes the file token"),
    ("GET", "/v1/files/wopi/files/{file_id}/contents"): Row(cells(401), w.p_static(f"{_WOPI_FILE}/contents"), f"{_WOPI}: GetFile takes the file token"),
    ("POST", "/v1/files/wopi/files/{file_id}"): Row(cells(401), w.p_missing(_WOPI_FILE, headers={"X-WOPI-Override": "LOCK", "X-WOPI-Lock": "probe"}),
                                                    f"{_WOPI}: Lock and Unlock take the file token"),
    ("POST", "/v1/files/wopi/files/{file_id}/contents"): Row(cells(401), w.p_missing(
        f"{_WOPI_FILE}/contents", content=b"x", headers={"X-WOPI-Override": "PUT", "X-WOPI-Lock": "probe"}), f"{_WOPI}: PutFile takes the file token"),
    # ---- photos (a person's phone backup; PHOTOS.md section 2) -----------------------------------------------
    # The service's own gate (PhotosService.person) runs before any lookup: only a person with role owner or adult has a
    # photo library, so guests, children and agents are 403 and the two library owners reach the (missing) object: 404.
    ("POST", "/v1/photos/sources"): Row(grid(201, 201, 403, 403, 403), w.p_missing(
        "/v1/photos/sources", json={"client_id": "probe-phone", "name": "Probe", "platform": "other"}), f"{_PHOTOS}: owner and adult register a phone"),
    ("POST", "/v1/photos/sources/{source_id}/check"): Row(PHOTOS_404, w.p_missing(
        "/v1/photos/sources/{source}/check", json={"items": []}), f"{_PHOTOS}: your own phone only"),
    ("GET", "/v1/photos/sources/{source_id}/coverage"): Row(PHOTOS_404, w.p_missing("/v1/photos/sources/{source}/coverage"), f"{_PHOTOS}: your own phone only"),
    ("GET", "/v1/photos/sources/{source_id}/receipts"): Row(PHOTOS_404, w.p_missing("/v1/photos/sources/{source}/receipts"), f"{_PHOTOS}: your own phone only"),
    ("GET", "/v1/photos/library"): Row(grid(200, 200, 403, 403, 403), w.p_static("/v1/photos/library"), f"{_PHOTOS}: your own photos only"),
    ("GET", "/v1/photos/assets/{asset_id}/content"): Row(PHOTOS_404, w.p_missing("/v1/photos/assets/{asset}/content"), f"{_PHOTOS}: your own photo only"),
    ("POST", "/v1/photos/uploads"): Row(PHOTOS_404, w.p_missing("/v1/photos/uploads", headers={
        "Upload-Length": "1", "Upload-Complete": "?0", "OneMind-Source-Id": w.MISSING["source"],
        "OneMind-Client-Key": "a" * 64, "OneMind-Content-Hash": "sha256:" + "b" * 64}), f"{_PHOTOS}: upload for your own phone only"),
    ("HEAD", "/v1/photos/uploads/{upload_id}"): Row(PHOTOS_404, w.p_missing("/v1/photos/uploads/{upload}"), f"{_PHOTOS}: your own upload"),
    ("PATCH", "/v1/photos/uploads/{upload_id}"): Row(PHOTOS_404, w.p_missing(
        "/v1/photos/uploads/{upload}", content=b"x",
        headers={"Content-Type": "application/partial-upload", "Upload-Offset": "0", "Upload-Complete": "?1"}), f"{_PHOTOS}: your own upload"),
    # ---- tips (#669: the image tips pack, shown by role; each person's own dismiss state) ---------------------
    # Every person reads the tips for their role (a child and a teen too); an agent has none. The matrix gateway has
    # no pack, so a tip id is missing (404) for every person.
    ("GET", "/v1/tips"): Row(grid(200, 200, 200, 200, 403), w.p_static("/v1/tips"), f"{_TIPS}: every person, filtered by role"),
    ("GET", "/v1/tips/collections"): Row(grid(200, 200, 200, 200, 403), w.p_static("/v1/tips/collections"), f"{_TIPS}: every person"),
    ("GET", "/v1/tips/whats-new"): Row(grid(200, 200, 200, 200, 403), w.p_static("/v1/tips/whats-new"), f"{_TIPS}: every person"),
    ("GET", "/v1/tips/{tip_id}"): Row(grid(404, 404, 404, 404, 403), w.p_static("/v1/tips/no-such-tip"), f"{_TIPS}: a tip for your role"),
    ("POST", "/v1/tips/{tip_id}/state"): Row(grid(404, 404, 404, 404, 403), w.p_missing(
        "/v1/tips/no-such-tip/state", json={"state": "dismissed"}), f"{_TIPS}: your own state for a tip you may see"),
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


# ---- storage (STORAGE-ACT-1; docs/leap/core/STORAGE-ACTIONS.md) ---------------------------------------------
# The matrix gateway runs with storage switched off (ONEMIND_STORAGE_ENABLED unset), so a caller that is allowed
# in is told 409 "off on this box"; the role gate that runs first still answers 403. Approving a destructive
# storage action needs the owner's passkey: core/tests/test_storage_security.py.
_STORAGE = "docs/leap/core/STORAGE-ACTIONS.md; core/tests/test_storage_security.py"
_STORAGE_PLAN = {"type": "storage.mirror.create", "params": {"device": "/dev/vdc"}}
POLICY |= {
    ("GET", "/v1/storage"): Row(READ_ANY, w.p_static("/v1/storage"), f"{_STORAGE}: any reader; no disk identities"),
    ("GET", "/v1/storage/devices"): Row(grid(409, 403, 403, 403, 403), w.p_static("/v1/storage/devices"),
                                        f"{_STORAGE}: full disk serials are owner only"),
    ("POST", "/v1/storage/plans"): Row(grid(409, 403, 403, 403, 409), w.p_missing("/v1/storage/plans", json=_STORAGE_PLAN),
                                       f"{_STORAGE}: requesters preview a plan; nothing changes"),
    ("POST", "/v1/storage/actions"): Row(grid(409, 403, 403, 403, 409), w.p_missing("/v1/storage/actions", json=_STORAGE_PLAN),
                                         f"{_STORAGE}: requesters file; only an owner approves, with a passkey"),
    ("GET", "/v1/storage/operations/{action_id}"): Row(grid(404, 403, 403, 403, 404), w.p_missing("/v1/storage/operations/x"),
                                                       f"{_STORAGE}: requesters read the stored plan"),
    ("POST", "/v1/storage/recovery-key"): Row(grid(404, 403, 403, 403, 403), w.p_missing("/v1/storage/recovery-key"),
                                              f"{_STORAGE}: owner only, and off until F-61/F-62"),
}

# ---- networking: feat/net-part2 (CORE-NET-12; contract §12.7 box CA, §12.11 fabric joins, §12.1 rate limits) ------
# Join tickets are an owner's: a ticket is what lets a machine ask to join the box (agents and guests never mint
# or list them; every refusal is audited, FabricService._deny). A joining node has no session: the one-time join
# code in the body (or in the poll's headers) is its only credential, so a bearer token is neither needed nor
# looked at, and a code the hub never issued is 401 for every caller. The box CA is public data.
_NET = "contract §12.11, core/onemind_core/routers/net.py"
_JOIN_CODE = f"{_NET}: no session, the one-time join code authenticates (rate limited per source, §12.1)"
POLICY |= {
    ("POST", "/v1/fabric/join-tickets"): Row(grid(201, 403, 403, 403, 403), w.p_missing("/v1/fabric/join-tickets", json={}),
                                             f"{_NET}: only the owner lets a machine join (an agent never mints a ticket)"),
    ("GET", "/v1/fabric/join-tickets"): Row(ONLY_OWNER, w.p_static("/v1/fabric/join-tickets"), f"{_NET}: owner only"),
    ("DELETE", "/v1/fabric/join-tickets/{ticket_id}"): Row(OWNER_ONLY_404, w.p_missing("/v1/fabric/join-tickets/tkt_0123456789abcdef"),
                                                           f"{_NET}: owner only; the gate runs before the lookup"),
    ("POST", "/v1/fabric/join-requests"): Row(cells(401), w.p_join_request, _JOIN_CODE, challenge="bearer"),
    ("GET", "/v1/fabric/join-requests/{request_id}"): Row(cells(404), w.p_missing("/v1/fabric/join-requests/jrq_0123456789abcdef"),
                                                          f"{_JOIN_CODE}; an unknown request id is 404 before any code is checked"),
    ("GET", "/v1/fabric"): Row(CHILD_CANNOT, w.p_static("/v1/fabric"),
                               f"{_NET}: the fabric summary (nodes, pending joins) like /v1/nodes: a child has no nodes:read (§12.6)"),
    ("GET", "/v1/mesh"): Row(CHILD_CANNOT, w.p_static("/v1/mesh"),
                             f"{_NET}: the mesh view (nodes, devices, app URLs); a child has no nodes:read; mesh addresses are owner only (?addresses)"),
    ("PUT", "/v1/mesh/settings"): Row(ONLY_OWNER, w.p_missing("/v1/mesh/settings", json={}),
                                      f"{_NET}: CORE-NET-8, only the owner turns the mesh on or off or picks its provider (refusals audited)"),
    ("GET", "/v1/tls"): Row(CHILD_CANNOT, w.p_static("/v1/tls"),
                            "contract §12.7: CA fingerprint and names to any signed-in caller; a child's role defaults do not cover it"),
    ("GET", "/v1/tls/ca.crt"): Row(cells(200), w.p_static("/v1/tls/ca.crt"),
                                   "contract §12.7: the box CA is public data; a phone or node needs it before it can sign in"),
    ("GET", "/v1/tls/onemind.mobileconfig"): Row(cells(200), w.p_static("/v1/tls/onemind.mobileconfig"),
                                                 "contract §12.7: the same public CA as ca.crt, wrapped as an Apple profile; carries no secret"),
    ("GET", "/v1/auth/forward"): Row(cells(404), w.p_static("/v1/auth/forward"),
                                     "NETWORKING §9.3: forward-auth for the app proxy, loopback only (the test client is not loopback: 404)"),
    ("POST", "/v1/auth/app-session"): Row(
        cells(403, **GONE, owner=204, adult=204, guest=204, child=204, **PENDING_DENY), w.p_static("/v1/auth/app-session"),
        "NETWORKING §9: a person's own bearer becomes the app-host cookie; agents are not people (refusal audited)"),
    ("DELETE", "/v1/auth/app-session"): Row(cells(204), w.p_static("/v1/auth/app-session"),
                                            "NETWORKING §9: only clears the caller's own cookie; no data, so no credential"),
}

# ---- virtual machines (MACH-1, #281: core/onemind_core/routers/machines.py) ---------------------------------
_MACH = "core/onemind_core/routers/machines.py"
POLICY |= {
    ("GET", "/v1/machines/capabilities"): Row(CHILD_CANNOT, w.p_static("/v1/machines/capabilities"),
                                              f"{_MACH}: shows what /v1/nodes shows, so the same nodes:read gate (a child has none)"),
    # The owner reaches the preflight, which refuses with 409 (no eligible node, or no extension yet); everybody else is stopped at 403.
    ("POST", "/v1/machines/enable"): Row(cells(403, **GONE, owner=409, plugin=DENIED, automation=DENIED, node=DENIED),
                                         w.p_static("/v1/machines/enable"),
                                         f"{_MACH}: only the owner turns machines on; an agent can never approve its own power-up"),
    ("POST", "/v1/machines/disable"): Row(cells(403, **GONE, owner=409, plugin=DENIED, automation=DENIED, node=DENIED),
                                          w.p_static("/v1/machines/disable"),
                                          f"{_MACH}: only the owner turns machines off; in this world they are already off (409)"),
    # Part 3 (machine actions). The list shows the same nodes:read facts; a machine that does not exist is a 404.
    ("GET", "/v1/machines"): Row(CHILD_CANNOT, w.p_static("/v1/machines"), f"{_MACH}: the machines on this box; a child has no nodes:read"),
    ("GET", "/v1/machines/{name}"): Row(cells(404, **GONE, child=403, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                        w.p_static("/v1/machines/ghost"), f"{_MACH}: one machine; none exists in this world"),
    ("GET", "/v1/machines/{name}/snapshots"): Row(cells(404, **GONE, child=403, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                                  w.p_static("/v1/machines/ghost/snapshots"),
                                                  f"{_MACH}: a machine's snapshots; none exists in this world"),
    ("GET", "/v1/machines/{name}/devices"): Row(cells(404, **GONE, child=403, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                                w.p_static("/v1/machines/ghost/devices"),
                                                f"{_MACH}: the devices a machine could be given (#690); none exists in this world"),
    ("POST", "/v1/machines/{name}/console"): Row(cells(403, **GONE, owner=404, plugin=DENIED, automation=DENIED, node=DENIED),
                                                 w.p_static("/v1/machines/ghost/console"),
                                                 f"{_MACH}: only the owner gets a console ticket; an agent never gets a screen"),
    ("POST", "/v1/machines/{name}/upload"): Row(cells(403, **GONE, owner=404, plugin=DENIED, automation=DENIED, node=DENIED),
                                                w.p_static("/v1/machines/ghost/upload"),
                                                f"{_MACH}: only the owner can transfer media to an approved machine"),
}

# ---- system controls (UMB-P09, #146: core/onemind_core/routers/system.py) -----------------------------------
_SYS = "core/onemind_core/routers/system.py"
POLICY |= {
    ("GET", "/v1/system/controls"): Row(OWNER_ONLY, w.p_static("/v1/system/controls"),
                                        f"{_SYS}: restart, shutdown, reset and their pending requests; owner only"),
    ("GET", "/v1/system/diagnostics"): Row(OWNER_ONLY, w.p_static("/v1/system/diagnostics"),
                                           f"{_SYS}: the redacted diagnostic bundle; owner only, audited"),
    # The owner and agents pass authorization; the gateway has no host path yet (NoHostPath), so the
    # request answers 409 host_unavailable instead of filing it. With a host, it is filed (202) and waits
    # for the owner's approval (tests/test_system_controls.py). Everyone else is refused first (403).
    ("POST", "/v1/system/actions"): Row(cells(403, **GONE, owner=409, agent=409, app_agent=409, plugin=DENIED,
                                              automation=DENIED, node=DENIED),
                                        lambda _w: w.Req("/v1/system/actions", json={"type": "system.restart"}),
                                        f"{_SYS}: owner or agent requests a restart; only an owner approves it"),
}

# ---- share links (FILES-02, #237: core/onemind_core/routers/shares.py) ------------------------------------
# Only an owner or adult publishes files outside the household (files:share); guests, children and agents are
# refused before any lookup. The /v1/share routes take no principal: the link secret in the path is the only
# credential, so a secret the box never issued is 404 for every caller, with or without a bearer token.
_SHARE = "core/onemind_core/files/shares.py"
POLICY |= {
    ("POST", "/v1/files/shares"): Row(grid(404, 404, 403, 403, 403), w.p_share_create,
                                      f"{_SHARE}: owner and adult share what they can read; agents never publish files"),
    ("GET", "/v1/files/shares"): Row(READ_ANY, w.p_static("/v1/files/shares"),
                                     f"{_SHARE}: each person their own links, an owner everyone's; others see none"),
    ("DELETE", "/v1/files/shares/{share_id}"): Row(READ_ANY_404, w.p_static(f"/v1/files/shares/{w.SHARE_ID}"),
                                                   f"{_SHARE}: the creator or an owner revokes; nobody else sees it"),
    ("GET", "/v1/share/{token}"): Row(cells(404), w.p_static(f"/v1/share/{w.SHARE_TOKEN}"),
                                      f"{_SHARE}: anonymous; the link secret is the credential"),
    ("GET", "/v1/share/{token}/items/{index}"): Row(cells(404), w.p_static(f"/v1/share/{w.SHARE_TOKEN}/items/0"),
                                                    f"{_SHARE}: anonymous; the link secret is the credential"),
}

# ---- fleet-staged OS updates (CORE-UPDATE-9, #156: core/onemind_core/routers/rollouts.py) ------------------
_ROLL = "core/onemind_core/routers/rollouts.py"
POLICY |= {
    # updates:read (contract §12.6): owner, adult and agents read versions and rollouts; guests and children do not.
    ("GET", "/v1/os/fleet"): Row(HOUSEHOLD, w.p_static("/v1/os/fleet"), f"{_ROLL}: every machine's OS version, updates:read"),
    ("GET", "/v1/os/rollouts"): Row(HOUSEHOLD, w.p_static("/v1/os/rollouts"), f"{_ROLL}: the rollouts, updates:read"),
    ("GET", "/v1/os/rollouts/{rollout_id}"): Row(HOUSEHOLD_404, w.p_static("/v1/os/rollouts/rol_ghost"),
                                                 f"{_ROLL}: one rollout; none exists in this world"),
    # Starting and resuming go through POST /v1/actions (owner approval); cancelling is the owner's alone.
    ("POST", "/v1/os/rollouts/{rollout_id}/cancel"): Row(OWNER_ONLY_404, w.p_static("/v1/os/rollouts/rol_ghost/cancel"),
                                                         f"{_ROLL}: only the owner cancels a rollout"),
}

# ---- family controls (FAM-01, #204) -------------------------------------------------------
# The owner passes authorization and gets 404 for these deliberately missing targets.
# Other people and service identities are refused before target lookup.
POLICY |= {
    ("GET", "/v1/family/profiles/{user_id}"): Row(
        OWNER_ONLY_404, w.p_static("/v1/family/profiles/missing"), "FAM-01: private profiles are owner only"),
    ("PUT", "/v1/family/profiles/{user_id}"): Row(
        OWNER_ONLY_404, w.p_missing("/v1/family/profiles/missing", json={}), "FAM-01: owner manages profiles"),
    ("GET", "/v1/family/apps/{app_id}"): Row(
        OWNER_ONLY_404, w.p_static("/v1/family/apps/missing"), "FAM-01: classifications are owner only"),
    ("PUT", "/v1/family/apps/{app_id}"): Row(
        OWNER_ONLY_404, w.p_missing("/v1/family/apps/missing", json={}), "FAM-01: owner manages classifications"),
}

# ---- agent kill switch (CORE-SEC-6, #159: core/onemind_core/routers/agents.py) ---------------------------------
# The matrix world runs with the switch off; test_agent_kill_switch.py covers every kind with it on.
_STOP = "core/onemind_core/routers/agents.py"
POLICY |= {
    ("GET", "/v1/agents/kill-switch"): Row(ANY_PRINCIPAL, w.p_static("/v1/agents/kill-switch"),
                                           f"{_STOP}: any signed-in caller may see whether agents are stopped (instance:read)"),
    ("PUT", "/v1/agents/kill-switch"): Row(ONLY_OWNER, w.p_missing("/v1/agents/kill-switch", json={"on": False}),
                                           f"{_STOP}: only the owner stops or resumes agents; an agent can never turn it off"),
}

# ---- SMB shares (FILES-SHARE-01, #235: core/onemind_core/routers/shares.py) ---------------------------------
_SHR = "core/onemind_core/routers/shares.py"
POLICY |= {
    ("GET", "/v1/shares/smb"): Row(grid(200, 200, 403, 403, 403), w.p_static("/v1/shares/smb"),
                                   f"{_SHR}: owner sees all shares, an adult their own; a guest has no home, a child has no scope, an agent never"),
    ("POST", "/v1/shares/smb/password"): Row(grid(409, 409, 403, 403, 403), w.p_missing("/v1/shares/smb/password"),
                                             f"{_SHR}: a person with files gets their own SMB password (409: none has a share in this world); guest, child and agent never"),
    ("POST", "/v1/shares/smb/{share_id}/stop"): Row(grid(404, 403, 403, 403, 403), w.p_missing("/v1/shares/smb/shr_0123456789abcdef/stop"),
                                                 f"{_SHR}: only an owner stops a share; the one probed does not exist"),
}

# ---- WebDAV app passwords (files-webdav, #722: core/onemind_core/routers/webdav.py) --------------------------
# The /dav tree is a middleware outside the router (files/webdav.py): it takes only app passwords, so every
# bearer token gets 401 there; core/tests/test_files_webdav.py covers it, including each token kind.
_DAV = "core/onemind_core/routers/webdav.py"
POLICY |= {
    ("GET", "/v1/files/app-passwords"): Row(grid(200, 200, 403, 403, 403), w.p_static("/v1/files/app-passwords"),
                                            f"{_DAV}: owner sees all, an adult their own; guest, child and agent hold none"),
    ("POST", "/v1/files/app-passwords"): Row(grid(201, 201, 403, 403, 403), w.p_missing(
        "/v1/files/app-passwords", json={"label": "probe", "scopes": ["shared:r"]}),
        f"{_DAV}: the owner or an adult makes one for themself (tokens:self); guest, child and agent never"),
    ("POST", "/v1/files/app-passwords/{password_id}/revoke"): Row(grid(404, 404, 403, 403, 403), w.p_missing(
        "/v1/files/app-passwords/apw_missing/revoke"), f"{_DAV}: revoking your own (an owner anyone's); the one probed does not exist"),
}

# ---- OS updates (UMB-P05, #142: core/onemind_core/routers/osupdates.py) --------------------------------------
_OSUP = "core/onemind_core/routers/osupdates.py"
POLICY |= {
    ("GET", "/v1/os/updates"): Row(CHILD_CANNOT, w.p_static("/v1/os/updates"),
                                   f"{_OSUP}: versions and A/B slots, the facts /v1/nodes shows; a child has no nodes:read"),
    ("GET", "/v1/os/updates/history"): Row(CHILD_CANNOT, w.p_static("/v1/os/updates/history"),
                                           f"{_OSUP}: commits, rollbacks and install requests; same nodes:read gate"),
    # About this box (UMB-P14, #432: core/onemind_core/routers/about.py)
    ("GET", "/v1/os/about"): Row(CHILD_CANNOT, w.p_static("/v1/os/about"),
                                 "core/onemind_core/routers/about.py: device facts the nodes report, as /v1/nodes shows; a child has no nodes:read"),
}

# ---- service cards (#623: core/onemind_core/routers/services.py) ------------------------------------------------
POLICY |= {
    # Owner only, read only (scope system:admin, like /v1/system/controls). In this world there is no host
    # socket, so the owner gets 200 with available=false; everyone else is refused first.
    ("GET", "/v1/system/services"): Row(OWNER_ONLY, w.p_static("/v1/system/services"),
                                        "core/onemind_core/routers/services.py: every systemd unit on the box and its state; owner only"),
    # #636: logs are owner only; with no host socket in this world the owner gets 409 host_unavailable.
    ("GET", "/v1/system/services/{unit}/logs"): Row(
        cells(403, **GONE, owner=409, plugin=DENIED, automation=DENIED, node=DENIED),
        w.p_static("/v1/system/services/onemind-gateway.service/logs"),
        "core/onemind_core/routers/services.py: a unit's redacted journal; owner only, audited"),
    # #636: the owner and agents pass authorization and get 409 (no host socket: nothing is filed); with a host
    # the request is filed and waits for the owner's passkey approval (tests/test_service_actions.py).
    ("POST", "/v1/system/services/{unit}/restart"): Row(
        cells(403, **GONE, owner=409, agent=409, app_agent=409, plugin=DENIED, automation=DENIED, node=DENIED),
        lambda _w: w.Req("/v1/system/services/onemind-gateway.service/restart", json={}),
        "core/onemind_core/routers/services.py: owner or agent asks for a service restart; only an owner approves it"),
    # The UPS battery (IMG-06, #244: core/onemind_core/routers/ups.py). Read only; no upsd in this world, so a
    # reader gets 200 with present=false. Device health like /v1/os/about: a child has no nodes:read.
    ("GET", "/v1/system/ups"): Row(CHILD_CANNOT, w.p_static("/v1/system/ups"),
                                   "core/onemind_core/routers/ups.py: the UPS on this box, read from upsd on loopback; never a command"),
}

# ---- Network screen (NET-UI-01, #239: core/onemind_core/routers/network.py) ---------------------------------
POLICY |= {
    ("GET", "/v1/network"): Row(grid(200, 403, 403, 403, 403), w.p_static("/v1/network"),
                                "core/onemind_core/routers/network.py: every address, MAC and open port of the box; owner only"),
}

# ---- bring your own domain (NET-DOM-01, #238: core/onemind_core/routers/domains.py) -----------------------------
_DOM = "core/onemind_core/routers/domains.py"
_OFF = grid(503, 403, 403, 403, 403)  # owner reaches the service, which is off in this world (domains_disabled)
POLICY |= {
    ("GET", "/v1/domains"): Row(ONLY_OWNER, w.p_static("/v1/domains"), f"{_DOM}: owner only, no-store"),
    ("POST", "/v1/domains"): Row(_OFF, w.p_missing("/v1/domains", json={"domain": "example.org"}),
                                 f"{_DOM}: owner only; refused while the feature is off"),
    ("DELETE", "/v1/domains/{domain}"): Row(_OFF, w.p_missing("/v1/domains/example.org"), f"{_DOM}: owner only"),
    ("POST", "/v1/domains/{domain}/check"): Row(_OFF, w.p_missing("/v1/domains/example.org/check"),
                                                f"{_DOM}: owner only; the DNS check never runs while off"),
    ("POST", "/v1/domains/{domain}/hosts"): Row(_OFF, w.p_missing("/v1/domains/example.org/hosts", json={"app_id": "whoami"}),
                                                f"{_DOM}: owner only"),
    ("POST", "/v1/domains/hosts/{hostname}/approve"): Row(
        _OFF, w.p_missing("/v1/domains/hosts/whoami.example.org/approve", json={"confirm": "whoami.example.org"}),
        f"{_DOM}: only the owner approves a public name; an agent never does"),
    ("DELETE", "/v1/domains/hosts/{hostname}"): Row(_OFF, w.p_missing("/v1/domains/hosts/whoami.example.org"), f"{_DOM}: owner only"),
}


# DEV-PLG-3: real installed plugin summaries follow Market sharing.
POLICY.update({
    ("GET", "/v1/plugins/{plugin_id}/settings"): Row(cells(404, **GONE, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                          w.p_static("/v1/plugins/not-installed/settings"), "#178 installed settings require sharing"),
    ("POST", "/v1/plugins/{plugin_id}/settings"): Row(cells(403, **GONE, owner=404, plugin=DECIDE, automation=DECIDE, node=DECIDE),
                                          lambda x: w.Req("/v1/plugins/not-installed/settings", json={"settings": {}, "bundle_sha256": "sha256:" + "a" * 64, "idempotency_key": x.key(), "expires_at": x.action_body()["expires_at"]}), "#178 owner-approved plugin.configure"),
    ("GET", "/v1/plugins"): Row(ANY_PRINCIPAL, w.p_static("/v1/plugins"), "#178 apps:read; shared installed plugin summaries"),
    ("GET", "/v1/plugins/{plugin_id}"): Row(cells(404, **GONE, plugin=DECIDE, automation=DECIDE, node=DECIDE),
        w.p_static("/v1/plugins/not-installed"), "#178 unavailable or unshared plugin is 404"),
})

# #178 REST plugin tools never allow plugin backend tokens or ownerless mutation.
POLICY.update({
    ("GET", "/v1/plugins/{plugin_id}/tools"): Row(cells(404, **GONE, plugin=DECIDE, automation=DECIDE, node=DECIDE),
        w.p_static("/v1/plugins/not-installed/tools"), "#178 shared installed tool declarations"),
    ("POST", "/v1/plugins/{plugin_id}/tools/{tool_name}"): Row(cells(404, **GONE, plugin=DECIDE, automation=DECIDE, node=DECIDE),
        lambda world: w.Req("/v1/plugins/not-installed/tools/missing", json={"arguments": {}}),
        "#178 read tools or pending owner-approved invocation"),
})


def _plugin_key_proposal(world):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return w.Req("/v1/plugin-trust/keys/requests", json={"name": "Test signing key", "public_key": public,
        "idempotency_key": world.key(), "expires_at": world.action_body()["expires_at"]})


POLICY.update({
    ("GET", "/v1/plugin-trust/keys"): Row(OWNER_ONLY, w.p_static("/v1/plugin-trust/keys"),
        "#180 only an owner reads private signing trust"),
    ("POST", "/v1/plugin-trust/keys/requests"): Row({**OWNER_ONLY, "owner": 202}, _plugin_key_proposal,
        "#180 owner proposal stays pending until approval"),
    ("POST", "/v1/plugin-trust/keys/{key_id}/revoke"): Row({**OWNER_ONLY, "owner": 404},
        lambda x: w.Req("/v1/plugin-trust/keys/sha256:" + "0" * 64 + "/revoke", json={
            "idempotency_key": x.key(), "expires_at": x.action_body()["expires_at"]}),
        "#180 owner approval required to revoke enrolled signing trust"),
})

# ---- host grants, the E2 capability broker (#186: core/onemind_core/routers/host_grants.py) ----------------
# An owner or an agent files a request (pending until an owner approves it on POST /v1/actions/{id}/approve);
# only an owner reads the grants or revokes one. The revoke probe names no grant: the owner learns 404.
def _host_grant_request(world):
    return w.Req("/v1/host-grants/requests", json={
        "app_id": "uptime-kuma", "kind": "device", "device_class": "usb-serial", "path": "/dev/ttyUSB0",
        "reason": "Zigbee stick", "idempotency_key": world.key(), "expires_at": world.action_body()["expires_at"]})


POLICY.update({
    ("GET", "/v1/host-grants"): Row(OWNER_ONLY, w.p_static("/v1/host-grants"),
        "#186 only an owner reads which apps hold host grants"),
    ("POST", "/v1/host-grants/requests"): Row(
        cells(403, **GONE, owner=202, agent=202, app_agent=202, plugin=DENIED, automation=DENIED, node=DENIED),
        _host_grant_request, "#186 an owner or agent files a host grant; it stays pending until an owner approves"),
    ("POST", "/v1/host-grants/{grant_id}/revoke"): Row({**OWNER_ONLY, "owner": 404},
        lambda x: w.Req("/v1/host-grants/hg_unknown/revoke"), "#186 only an owner revokes a host grant"),
})

# ---- browser windows, one profile per person (#692: core/onemind_core/routers/browsers.py) ----------------
# The probe names an app that is not a browser: a person learns only "no such browser app" (404). Only a
# signed-in person may ask at all, so every agent, plugin, automation and node is refused (403, audited).
_BROWSER = "core/onemind_core/routers/browsers.py"
BROWSER_PERSON = cells(404, **GONE, agent=403, app_agent=403, plugin=403, automation=403, node=403)
POLICY |= {
    ("POST", "/v1/browsers/{app_id}/session"): Row(BROWSER_PERSON, w.p_static("/v1/browsers/whoami/session"),
                                                   f"{_BROWSER}: a person opens their own browser; no token opens a person's"),
    ("POST", "/v1/browsers/{app_id}/session/close"): Row(BROWSER_PERSON, w.p_static("/v1/browsers/whoami/session/close"),
                                                         f"{_BROWSER}: a person stops their own browser"),
    ("POST", "/v1/browsers/{app_id}/profile/reset"): Row(BROWSER_PERSON, w.p_static("/v1/browsers/whoami/profile/reset"),
                                                         f"{_BROWSER}: files browser.profile.reset; only an owner's approval erases"),
}

# ---- the NATS subject tree (#600: core/onemind_core/routers/subjects.py) ------------------------------------
_SUBJ = "core/onemind_core/routers/subjects.py"
POLICY |= {
    ("GET", "/v1/subjects"): Row(CHILD_CANNOT, w.p_static("/v1/subjects"),
                                 f"{_SUBJ}: the public subject registry (§12.9), same events:read gate as /v1/events"),
    ("GET", "/v1/subjects/check"): Row(CHILD_CANNOT, w.p_static("/v1/subjects/check?subject=onemind.audit"),
                                       f"{_SUBJ}: read-only what-if check with a reason; never publishes"),
}

# ---- the box's own screen (UX-07, #242: core/onemind_core/routers/kiosk.py) ---------------------------------
_KIOSK = "core/onemind_core/routers/kiosk.py"
POLICY |= {
    ("GET", "/v1/instance/kiosk"): Row(ONLY_OWNER, w.p_static("/v1/instance/kiosk"),
                                       f"{_KIOSK}: owner only, reading too (the switch is the box's own screen); refusals audited"),
    # enabled=false only removes a flag file that is not there on a test box, so the probe changes nothing.
    ("PUT", "/v1/instance/kiosk"): Row(ONLY_OWNER, w.p_kiosk_put,
                                       f"{_KIOSK}: only the owner changes the screen; an agent can never switch it"),
}

# ---- bridge intake (#610: core/onemind_core/routers/bridges.py) --------------------------------------------
# Only the bridge's own installation token posts events (plugins/auth.allows_bridge_intake); every person and
# agent is refused. Owners and adults read status; the probe names a bridge that is not installed (404).
_BRIDGE = "core/onemind_core/routers/bridges.py"
BRIDGE_READ = cells(403, **GONE, owner=404, adult=404, plugin=DENIED, automation=DENIED, node=DENIED)
POLICY |= {
    ("POST", "/v1/bridges/{bridge_id}/events"): Row(
        cells(403, **GONE, plugin=DENIED, automation=DENIED, node=DENIED),
        lambda _: w.Req("/v1/bridges/whoami/events", json={"events": [{"id": "probe"}]}),
        f"{_BRIDGE}: a bridge posts only under its own app id; people and agents never post events"),
    ("GET", "/v1/bridges"): Row(cells(403, **GONE, owner=200, adult=200, plugin=DENIED, automation=DENIED, node=DENIED),
                                w.p_static("/v1/bridges"), f"{_BRIDGE}: owners and adults read bridge status"),
    ("GET", "/v1/bridges/{bridge_id}"): Row(BRIDGE_READ, w.p_static("/v1/bridges/not-a-bridge"),
                                            f"{_BRIDGE}: owners and adults read bridge status"),
    ("GET", "/v1/bridges/{bridge_id}/latest"): Row(BRIDGE_READ, w.p_static("/v1/bridges/not-a-bridge/latest"),
                                                   f"{_BRIDGE}: values need owner or adult, then the bridge's data class"),
    ("POST", "/v1/bridges/{bridge_id}/resume"): Row(
        cells(403, **GONE, owner=404, plugin=DENIED, automation=DENIED, node=DENIED),
        w.p_static("/v1/bridges/not-a-bridge/resume"), f"{_BRIDGE}: only an owner lets a paused bridge in again"),
}

# ---- radio-found cards (#732) ---------------------------------------------------------------------------------------
_RADIO = "core/onemind_core/routers/radios.py (#732)"
POLICY |= {
    ("GET", "/v1/radios"): Row(CHILD_CANNOT, w.p_static("/v1/radios"),
                               f"{_RADIO}: the USB serial lines of the hardware profile /v1/nodes shows; a child has no nodes:read"),
    # A radio that is not there: the owner reaches the (missing) card, everybody else is refused first.
    ("POST", "/v1/radios/{radio_id}/confirm"): Row(OWNER_ONLY_404, w.p_missing("/v1/radios/nosuchnode.lora0/confirm", json={
        "profile": "meshcore-companion-usb"}),
        f"{_RADIO}: only the owner says what a radio is; an agent never confirms one, and nothing is probed or sent"),
}

# ---- motion lockout (#723: core/onemind_core/routers/physical.py) ----------------------------------------------
# Owner only for reading too (MotionLockout.owner_only audits every refusal). The probe turns the lockout on,
# which never needs a passkey; turning it off needs a fresh passkey once passkeys are active
# (test_physical_actions.py covers that step-up).
_PHYS = "core/onemind_core/routers/physical.py"
POLICY |= {
    ("GET", "/v1/physical/lockout"): Row(ONLY_OWNER, w.p_static("/v1/physical/lockout"),
                                         f"{_PHYS}: whether every physical action is refused; owner only, refusals audited"),
    ("PUT", "/v1/physical/lockout"): Row(ONLY_OWNER, lambda _w: w.Req("/v1/physical/lockout", json={"locked": True, "reason": "matrix probe"}),
                                         f"{_PHYS}: only the owner locks or lifts motion; an agent can never lift it"),
}

# ---- the data commons (#615: core/onemind_core/routers/datagrants.py) -----------------------------------------
# No token scope opens these doors: everybody signed in reaches them and sees what their data grant allows
# (nothing, so an empty list or a stream that ends at once). Writing needs a write grant, revoking an owner.
_DATA = "core/onemind_core/routers/datagrants.py"
DATA_READ = cells(200, **GONE, plugin=200, automation=frozenset({200, 403}), node=frozenset({200, 403}))
DATA_OWNER = cells(403, **GONE, owner=201, automation=frozenset({403}), node=DENIED)
POLICY |= {
    ("GET", "/v1/data/classes"): Row(DATA_READ, w.p_static("/v1/data/classes"),
                                     f"{_DATA}: the five classes and the caller's own access"),
    ("GET", "/v1/data/classes/{data_class}"): Row(DATA_READ, w.p_static("/v1/data/classes/location"),
                                                  f"{_DATA}: count only with read or aggregate, else null"),
    ("GET", "/v1/data/classes/{data_class}/records"): Row(DATA_READ, w.p_static("/v1/data/classes/location/records"),
                                                          f"{_DATA}: empty without a read grant, never an error"),
    ("POST", "/v1/data/classes/{data_class}/records"): Row(
        DATA_OWNER, lambda world: w.Req("/v1/data/classes/location/records", json={"kind": "probe", "value": 1}),
        f"{_DATA}: a write grant (only an owner holds one by default); refusals audited"),
    ("GET", "/v1/data/classes/{data_class}/stream"): Row(
        DATA_READ, lambda world: w.Req("/v1/data/classes/location/stream", stream=True),
        f"{_DATA}: SSE; without read it sends end(no_grant) and closes"),
    ("GET", "/v1/data/grants"): Row(DATA_READ, w.p_static("/v1/data/grants"),
                                    f"{_DATA}: the owner sees every grant (the Privacy screen), others their own"),
    ("DELETE", "/v1/data/grants/{grant_id}"): Row(OWNER_ONLY_404, w.p_missing("/v1/data/grants/dgr_0123456789abcdef"),
                                                  f"{_DATA}: only an owner revokes; no approval, it only takes access away"),
}

# Asset locations use the node-inventory read scope. Only a human owner can edit map records.
POLICY |= {
    ("GET", "/v1/sites"): Row(CHILD_CANNOT, w.p_static("/v1/sites"), "Site inventory, nodes:read"),
    ("POST", "/v1/sites"): Row({**OWNER_ONLY, "owner": 422}, w.p_missing("/v1/sites", json={}),
                               "Only an owner may create a site; probe has no anchors"),
}

# ---- the agent browser (#694: core/onemind_core/routers/agentbrowser.py) --------------------------------------
# Only the owner and AI agents use it; every other person is refused (403, audited). The matrix gateway runs with
# the agent browser switched off, so starting a session is 409 agent_browser_off; test_agentbrowser.py has it on.
_AB = "core/onemind_core/routers/agentbrowser.py"
AB_USERS = grid(200, 403, 403, 403, 200)
POLICY |= {
    ("GET", "/v1/agent-browser/sites"): Row(AB_USERS, w.p_static("/v1/agent-browser/sites"),
                                            f"{_AB}: owner sees every agent's allowlist, an agent its own"),
    ("POST", "/v1/agent-browser/sites"): Row({**grid(201, 403, 403, 403, 201), "app-agent": 403},
                                             w.p_missing("/v1/agent-browser/sites", json={"entry": "example.org", "agent": "hermes"}),
                                             f"{_AB}: owner or agent files agentbrowser.site.allow (an app's agent may not ask for hermes); only an owner's approval adds it"),
    ("DELETE", "/v1/agent-browser/sites/{site_id}"): Row(OWNER_ONLY_404, w.p_missing("/v1/agent-browser/sites/abs_missing"),
                                                         f"{_AB}: only the owner takes a site away; the one probed does not exist"),
    ("GET", "/v1/agent-browser/sessions"): Row(AB_USERS, w.p_static("/v1/agent-browser/sessions"),
                                               f"{_AB}: owner sees all sessions, an agent its own"),
    ("POST", "/v1/agent-browser/sessions"): Row(grid(409, 403, 403, 403, 409), w.p_missing("/v1/agent-browser/sessions", json={}),
                                                f"{_AB}: owner or agent; switched off in the matrix world (409 agent_browser_off)"),
    ("DELETE", "/v1/agent-browser/sessions/{session_id}"): Row(grid(404, 403, 403, 403, 404),
                                                               w.p_missing("/v1/agent-browser/sessions/abs_missing"),
                                                               f"{_AB}: owner ends any session, an agent its own; none exists"),
    ("POST", "/v1/agent-browser/sessions/{session_id}/visit"): Row(
        grid(404, 403, 403, 403, 404),
        w.p_missing("/v1/agent-browser/sessions/abs_missing/visit", json={"url": "https://example.org/"}),
        f"{_AB}: owner or agent opens a page in its own session; none exists"),
}
