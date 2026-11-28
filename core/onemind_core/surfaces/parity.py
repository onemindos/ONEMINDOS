# SPDX-License-Identifier: Apache-2.0
"""Route parity (#605): every route the gateway serves has a tool or a named reason it has none.

Three lists, and CI (tests/test_surfaces.py) fails on any route that is in none of them:
- a tool: the `route` of a ToolSurface in surfaces/core.py (the MCP catalogue is generated from it);
- HUMAN_ONLY: routes no agent tool may stand for, each with its reason (REASONS);
- AWAITING_TOOL: read routes that are to get a generated read tool (the area issues; #632 landed the first). It is a
  ratchet: a new route never goes here, and an entry leaves it when its tool lands.

A route is one "METHOD /path" with the path as FastAPI declares it. HEAD follows GET and OPTIONS is the
CORS preflight, so neither is listed. An entry for a route the gateway no longer serves also fails, so
the lists never hold dead lines.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI
from starlette.routing import Route, WebSocketRoute

OVERSIGHT = "oversight"
CREDENTIAL = "credential"
PERSON = "person"
SITE_MAP = "site-map"
BYTES = "bytes"
DOOR = "door"
WRITE = "write"
FLEET = "fleet"
CONSOLE = "console"

REASONS: dict[str, str] = {
    OVERSIGHT: "Approving, denying, approval policies, the motion lockout, confirming what a found radio is and "
               "the controls over agents are a person's alone; no agent tool exists for them.",
    CREDENTIAL: "Sign-in, sessions, tokens, passkeys, keys, secrets, join tickets and device trust never pass "
                "through an agent.",
    PERSON: "The signed-in person's own record (profile, Home, inbox, windows); an agent has no such record.",
    SITE_MAP: "Shared site map configuration and surveyed anchors have no agent tool.",
    BYTES: "File bytes, uploads, event streams, consoles, Prometheus text or the restic repository protocol, "
           "not a JSON tool result.",
    DOOR: "A door of its own (the MCP endpoint, installed-app tool calls, sign-in page, health probe, OpenAPI "
          "document, surface registry, sync feed and file transfer, the Send to menu, dashboard files, the data commons, the agent browser, an outsider's "
          "share link); a tool over it adds nothing.",
    WRITE: "Changes the box directly. An agent never writes: it files a request (request_action or a "
           "request_<type> tool) that a person approves.",
    FLEET: "Fleet OS versions and staged rollouts (#156): a rollout starts only as an owner-approved action "
           "(os.rollout.start), which an agent follows through get_action; this is the owner's update console.",
    CONSOLE: "The owner's system console: host service logs (which can hold secrets until a redacted read tool "
             "exists), the message-bus monitor (#619), bridge status (#610) and the UPS battery (#244). Agents read the world through the "
             "data commons doors and request changes as actions.",
}

SKIP_METHODS = frozenset({"HEAD", "OPTIONS"})


def route_keys(app: FastAPI) -> set[str]:
    """Every "METHOD /path" the app serves (websockets as "WS /path")."""
    keys: set[str] = set()
    for r in app.routes:
        if isinstance(r, WebSocketRoute):  # FastAPI's APIWebSocketRoute too
            keys.add(f"WS {r.path}")
        elif isinstance(r, Route):  # FastAPI's APIRoute too
            keys.update(f"{m} {r.path}" for m in (r.methods or {"GET"}) - SKIP_METHODS)
    return keys


def problems(keys: Iterable[str], tool_routes: dict[str, str]) -> list[str]:
    """Why the lists and the served routes disagree; empty when every route is accounted for.

    tool_routes maps "METHOD /path" to the tool (or tools) that project it."""
    keys = set(keys)
    out: list[str] = []
    for key in sorted(keys):
        listed = [n for n, hit in (("a tool", key in tool_routes), ("HUMAN_ONLY", key in HUMAN_ONLY),
                                   ("AWAITING_TOOL", key in AWAITING_TOOL)) if hit]
        if not listed:
            out.append(f"{key} has no tool and no human-only entry: declare a ToolSurface in surfaces/core.py "
                       "or add it to HUMAN_ONLY in surfaces/parity.py with its reason")
        elif len(listed) > 1:
            out.append(f"{key} is in {' and '.join(listed)}; it belongs in one")
    for key in sorted((HUMAN_ONLY.keys() | AWAITING_TOOL) - keys):
        out.append(f"{key} is listed in surfaces/parity.py but the gateway does not serve it: delete the line")
    for key, tool in sorted(tool_routes.items()):
        if key not in keys:
            out.append(f"tool {tool} projects {key}, which the gateway does not serve")
    for key, reason in sorted(HUMAN_ONLY.items()):
        if reason not in REASONS:
            out.append(f"{key} has reason {reason!r}, which is not in REASONS")
    return out


HUMAN_ONLY: dict[str, str] = {
    "POST /v1/work/projects": WRITE,
    "POST /v1/work/capture": WRITE,
    "POST /v1/work/quick-add": WRITE,
    "PATCH /v1/work/projects/{project_id}/tasks/{task_id}": WRITE,
    "DELETE /v1/work/projects/{project_id}/tasks/{task_id}": WRITE,
    # ---- oversight: deciding requests and controlling agents
    "POST /v1/actions/{action_id}/approve": OVERSIGHT,
    "POST /v1/actions/{action_id}/approve-options": OVERSIGHT,
    "POST /v1/actions/{action_id}/deny": OVERSIGHT,
    "GET /v1/agents/kill-switch": OVERSIGHT,
    "PUT /v1/agents/kill-switch": OVERSIGHT,
    "PUT /v1/agents/{name}/budget": OVERSIGHT,
    "POST /v1/agents/{name}/cancel": OVERSIGHT,
    "POST /v1/agents/{name}/resume": OVERSIGHT,
    # an agent never gets a tool that issues, reads or revokes its own NATS key
    "GET /v1/agents/{name}/nats-key": CREDENTIAL,
    "PUT /v1/agents/{name}/nats-key": CREDENTIAL,
    "DELETE /v1/agents/{name}/nats-key": CREDENTIAL,
    "GET /v1/approval-policies": OVERSIGHT,
    "POST /v1/approval-policies": OVERSIGHT,
    "DELETE /v1/approval-policies/{policy_id}": OVERSIGHT,
    # FD-08 is an owner-only report for assessing the box before deciding on maintenance.
    "GET /v1/care/checkup": OVERSIGHT,
    "POST /v1/domains/hosts/{hostname}/approve": OVERSIGHT,
    "POST /v1/files/requests/{request_id}/approve": OVERSIGHT,
    "POST /v1/files/requests/{request_id}/deny": OVERSIGHT,
    # #690: the USB devices and GPUs an owner may grant a machine, and why one is refused; the owner
    # decides a grant from it (an agent only files machine.attach_device, which the owner approves)
    "GET /v1/machines/{name}/devices": OVERSIGHT,
    # host grants (#186 E2): the owner alone decides what reaches the host; an agent may file the request
    # over REST (it stays pending until the owner approves), but no agent tool stands for it
    "GET /v1/host-grants": OVERSIGHT,
    "POST /v1/host-grants/requests": OVERSIGHT,
    "POST /v1/host-grants/{grant_id}/revoke": OVERSIGHT,
    "PUT /v1/physical/lockout": OVERSIGHT,
    "POST /v1/radios/{radio_id}/confirm": OVERSIGHT,
    # ---- credential: sign-in, tokens, keys, secrets, pairing
    "GET /v1/apps/{app_id}/credentials": CREDENTIAL,
    "GET /v1/apps/{app_id}/secrets": CREDENTIAL,
    "POST /v1/apps/{app_id}/secrets": CREDENTIAL,
    "DELETE /v1/auth/app-session": CREDENTIAL,
    "POST /v1/auth/app-session": CREDENTIAL,
    "POST /v1/auth/enrol": CREDENTIAL,
    "GET /v1/auth/forward": CREDENTIAL,
    "POST /v1/auth/login": CREDENTIAL,
    "POST /v1/auth/login/options": CREDENTIAL,
    "POST /v1/auth/logout": CREDENTIAL,
    "GET /v1/auth/methods": CREDENTIAL,
    "GET /v1/auth/passkeys": CREDENTIAL,
    "POST /v1/auth/passkeys/register": CREDENTIAL,
    "POST /v1/auth/passkeys/register/options": CREDENTIAL,
    "DELETE /v1/auth/passkeys/{credential_id}": CREDENTIAL,
    "POST /v1/auth/password": CREDENTIAL,
    "POST /v1/auth/refresh": CREDENTIAL,
    "POST /v1/auth/rescue/options": CREDENTIAL,
    "POST /v1/auth/rescue/verify": CREDENTIAL,
    "GET /v1/auth/sessions": CREDENTIAL,
    "DELETE /v1/auth/sessions/{session_id}": CREDENTIAL,
    "POST /v1/auth/setup": CREDENTIAL,
    "POST /v1/auth/totp/confirm": CREDENTIAL,
    "POST /v1/auth/totp/disable": CREDENTIAL,
    "POST /v1/auth/totp/setup": CREDENTIAL,
    "GET /v1/backups/kit": CREDENTIAL,
    "POST /v1/backups/kit": CREDENTIAL,
    "POST /v1/backups/kit/confirm": CREDENTIAL,
    "POST /v1/fabric/join-requests": CREDENTIAL,
    "GET /v1/fabric/join-requests/{request_id}": CREDENTIAL,
    "GET /v1/fabric/join-tickets": CREDENTIAL,
    "POST /v1/fabric/join-tickets": CREDENTIAL,
    "DELETE /v1/fabric/join-tickets/{ticket_id}": CREDENTIAL,
    "GET /v1/files/app-passwords": CREDENTIAL,
    "POST /v1/files/app-passwords": CREDENTIAL,
    "POST /v1/files/app-passwords/{password_id}/revoke": CREDENTIAL,
    "POST /v1/files/wopi/tokens": CREDENTIAL,
    "GET /v1/plugin-trust/keys": CREDENTIAL,
    "POST /v1/plugin-trust/keys/requests": CREDENTIAL,
    "POST /v1/plugin-trust/keys/{key_id}/revoke": CREDENTIAL,
    "GET /v1/push/registrations": CREDENTIAL,
    "POST /v1/push/registrations": CREDENTIAL,
    "DELETE /v1/push/registrations/{device_id}": CREDENTIAL,
    "GET /v1/push/vapid-public-key": CREDENTIAL,
    "GET /v1/secrets/public-key": CREDENTIAL,
    "POST /v1/shares/smb/password": CREDENTIAL,
    "POST /v1/storage/recovery-key": CREDENTIAL,
    "GET /v1/tls/ca.crt": CREDENTIAL,
    "GET /v1/tls/onemind.mobileconfig": CREDENTIAL,
    "GET /v1/tokens": CREDENTIAL,
    # share links (#237): each link secret is a bearer credential handed to someone outside the household
    "GET /v1/files/shares": CREDENTIAL,
    "POST /v1/files/shares": CREDENTIAL,
    "DELETE /v1/files/shares/{share_id}": CREDENTIAL,
    "POST /v1/tokens": CREDENTIAL,
    "DELETE /v1/tokens/{token_id}": CREDENTIAL,
    "POST /v1/tokens/{token_id}/rotate": CREDENTIAL,
    # ---- person: the signed-in person's own record
    # #693: the signed-in person's own quarantined browser downloads (an owner sees everyone's).
    "GET /v1/files/downloads": PERSON,
    "GET /v1/me": PERSON,
    "PATCH /v1/me": PERSON,
    "GET /v1/me/dashboard-card": PERSON,
    "PUT /v1/me/dashboard-card": PERSON,
    "GET /v1/me/dashboard-card/events": BYTES,
    "GET /v1/me/home": PERSON,
    "PUT /v1/me/home": PERSON,
    "GET /v1/notifications": PERSON,
    "GET /v1/notifications/summary": PERSON,
    "GET /v1/notifications/preferences": PERSON,
    "PUT /v1/notifications/preferences": PERSON,
    "POST /v1/notifications/read-all": PERSON,
    "GET /v1/notifications/{notification_id}": PERSON,
    "POST /v1/notifications/{notification_id}/read": PERSON,
    "GET /v1/windows": PERSON,
    "PUT /v1/windows/{window_id}": PERSON,
    # tips (#669): how-to text for a person at a screen, filtered by role, with that person's seen state;
    # routers/tips.py answers 403 to any caller that is not a person
    "GET /v1/tips": PERSON,
    "GET /v1/tips/collections": PERSON,
    "GET /v1/tips/whats-new": PERSON,
    "GET /v1/tips/{tip_id}": PERSON,
    "POST /v1/tips/{tip_id}/state": PERSON,
    # ---- shared map configuration
    "GET /v1/sites": SITE_MAP,
    # ---- bytes: files, uploads, streams and repository protocols
    "GET /v1/backups/snapshots/{snapshot_id}/file": BYTES,
    "GET /v1/events": BYTES,
    "GET /v1/files/download": BYTES,
    "GET /v1/files/preview": BYTES,
    "GET /v1/share/{token}/items/{index}": BYTES,
    "POST /v1/files/uploads": BYTES,
    "DELETE /v1/files/uploads/{upload_id}": BYTES,
    "GET /v1/files/uploads/{upload_id}": BYTES,
    "PATCH /v1/files/uploads/{upload_id}": BYTES,
    # WOPI (#675): the office engine's file protocol, reached only with a person's om_wopi_ token
    "GET /v1/files/wopi/files/{file_id}": BYTES,
    "POST /v1/files/wopi/files/{file_id}": BYTES,
    "GET /v1/files/wopi/files/{file_id}/contents": BYTES,
    "POST /v1/files/wopi/files/{file_id}/contents": BYTES,
    "POST /v1/machines/{name}/console": BYTES,
    "POST /v1/machines/{name}/upload": BYTES,
    "GET /v1/metrics": BYTES,
    "POST /v1/migrate/repo/{plan_id}": BYTES,
    "POST /v1/migrate/repo/{plan_id}/": BYTES,
    "GET /v1/migrate/repo/{plan_id}/config": BYTES,
    "POST /v1/migrate/repo/{plan_id}/config": BYTES,
    "GET /v1/migrate/repo/{plan_id}/{typ}/": BYTES,
    "DELETE /v1/migrate/repo/{plan_id}/{typ}/{name}": BYTES,
    "GET /v1/migrate/repo/{plan_id}/{typ}/{name}": BYTES,
    "POST /v1/migrate/repo/{plan_id}/{typ}/{name}": BYTES,
    "GET /v1/photos/assets/{asset_id}/content": BYTES,
    "POST /v1/photos/uploads": BYTES,
    "PATCH /v1/photos/uploads/{upload_id}": BYTES,
    "PUT /v1/sync/chunks/{chunk_hash}": BYTES,
    # ---- door: routes that are doors of their own
    "GET /healthz": DOOR,
    "DELETE /mcp": DOOR,
    "GET /mcp": DOOR,
    "POST /mcp": DOOR,
    "GET /openapi.json": DOOR,
    "GET /signin": DOOR,
    "POST /v1/plugins/{plugin_id}/tools/{tool_name}": DOOR,
    "GET /v1/protocol": DOOR,
    "GET /v1/share/{token}": DOOR,
    "GET /v1/share/targets": DOOR,
    "GET /v1/share/types": DOOR,
    "GET /v1/surfaces": DOOR,
    "GET /v1/sync/changes": DOOR,
    "POST /v1/sync/chunks/missing": DOOR,
    "POST /v1/sync/commit": DOOR,
    "GET /v1/sync/versions": DOOR,
    "GET /{full_path:path}": DOOR,
    # ---- write: direct changes; agents file requests instead
    "POST /v1/alerts/{alert_id}/ack": WRITE,
    "POST /v1/alerts/{alert_id}/fix": WRITE,
    "POST /v1/alerts/{alert_id}/resolve": WRITE,
    "PUT /v1/apps/{app_id}/access": WRITE,
    "POST /v1/automation/pause": WRITE,
    "POST /v1/automation/resume": WRITE,
    "POST /v1/automation/rules": WRITE,
    "DELETE /v1/automation/rules/{rule_id}": WRITE,
    "PATCH /v1/automation/rules/{rule_id}": WRITE,
    "POST /v1/automation/rules/{rule_id}/disable": WRITE,
    "POST /v1/automation/rules/{rule_id}/dry-run": WRITE,
    "POST /v1/automation/rules/{rule_id}/enable": WRITE,
    "POST /v1/backups/content": WRITE,
    "POST /v1/backups/destinations": WRITE,
    "DELETE /v1/backups/destinations/{dest_id}": WRITE,
    "POST /v1/backups/runs": WRITE,
    "POST /v1/backups/verify": WRITE,
    "POST /v1/browsers/{app_id}/profile/reset": WRITE,
    "POST /v1/browsers/{app_id}/session": WRITE,
    "POST /v1/browsers/{app_id}/session/close": WRITE,
    "POST /v1/deploy/compose": WRITE,
    "GET /v1/custom-apps": OVERSIGHT,  # repository URLs and deploy history are the owner's; an agent requests app.install
    "GET /v1/custom-apps/{app_id}": OVERSIGHT,
    "POST /v1/custom-apps/plan": OVERSIGHT,  # fetches a repository: an owner act, an agent only requests the install
    "POST /v1/custom-apps/{app_id}/rollback": OVERSIGHT,
    "POST /v1/domains": WRITE,
    "DELETE /v1/domains/hosts/{hostname}": WRITE,
    "DELETE /v1/domains/{domain}": WRITE,
    "POST /v1/domains/{domain}/check": WRITE,
    "POST /v1/domains/{domain}/hosts": WRITE,
    "PUT /v1/family/apps/{app_id}": WRITE,
    "PUT /v1/family/profiles/{user_id}": WRITE,
    "POST /v1/files/grants": WRITE,
    "DELETE /v1/files/grants/{grant_id}": WRITE,
    "POST /v1/files/ops": WRITE,
    "POST /v1/os/rollouts/{rollout_id}/cancel": WRITE,
    "PUT /v1/files/quotas/{person_id}": WRITE,
    "POST /v1/files/requests/{request_id}/cancel": WRITE,
    "POST /v1/files/trash/empty": WRITE,
    "POST /v1/files/downloads/{download_id}/release": WRITE,
    "DELETE /v1/files/downloads/{download_id}": WRITE,
    "PUT /v1/instance/kiosk": WRITE,
    "POST /v1/machines/disable": WRITE,
    "POST /v1/machines/enable": WRITE,
    "POST /v1/migrate/plans": WRITE,
    "POST /v1/migrate/plans/{plan_id}/copy": WRITE,
    "POST /v1/migrate/plans/{plan_id}/cutover": WRITE,
    "POST /v1/migrate/plans/{plan_id}/import": WRITE,
    "POST /v1/migrate/plans/{plan_id}/revert": WRITE,
    "POST /v1/notifications/channels": WRITE,
    "DELETE /v1/notifications/channels/{channel_id}": WRITE,
    "PATCH /v1/notifications/channels/{channel_id}": WRITE,
    "POST /v1/notifications/channels/{channel_id}/test": WRITE,
    "PUT /v1/notifications/sources/{source_id}": WRITE,
    "POST /v1/onboarding/restore/apps": WRITE,
    "POST /v1/onboarding/restore/candidates": WRITE,
    "PUT /v1/onboarding/settings": WRITE,
    "POST /v1/photos/sources": WRITE,
    "POST /v1/photos/sources/{source_id}/check": WRITE,
    "POST /v1/plugins/{plugin_id}/settings": WRITE,
    "POST /v1/restores": WRITE,
    "POST /v1/share": WRITE,
    "POST /v1/shares/smb/{share_id}/stop": WRITE,
    "POST /v1/sites": WRITE,
    "POST /v1/storage/actions": WRITE,
    "POST /v1/storage/plans": WRITE,
    "POST /v1/system/actions": WRITE,
    "PUT /v1/os/settings": WRITE,
    "PUT /v1/update-policy": WRITE,
    "POST /v1/update-policy/resume": WRITE,
    "POST /v1/users": WRITE,
    "PATCH /v1/users/{user_id}": WRITE,
    "POST /v1/users/{user_id}/disable": WRITE,
    # ---- fleet: OS versions and staged rollouts
    "GET /v1/os/fleet": FLEET,
    "GET /v1/os/rollouts": FLEET,
    "GET /v1/os/rollouts/{rollout_id}": FLEET,
    # ---- classified 2026-11-23 (hand-off gate): routes that landed without an entry
    "GET /v1/auth/approver-keys": CREDENTIAL,
    "POST /v1/auth/approver-keys": CREDENTIAL,
    "DELETE /v1/auth/approver-keys/{key_id}": CREDENTIAL,
    "GET /v1/me/devices": PERSON,
    "DELETE /v1/me/devices/{device_id}": PERSON,
    "GET /v1/sync/locks": DOOR,
    "POST /v1/sync/locks": DOOR,
    "POST /v1/sync/locks/{lock_id}/refresh": DOOR,
    "DELETE /v1/sync/locks/{lock_id}": DOOR,
    "POST /v1/bridges/{bridge_id}/events": DOOR,
    "GET /v1/bridges": CONSOLE,
    "GET /v1/bridges/{bridge_id}": CONSOLE,
    "GET /v1/bridges/{bridge_id}/latest": CONSOLE,
    "GET /v1/engine": CONSOLE,
    "GET /v1/system/services/{unit}/logs": CONSOLE,
    "GET /v1/system/ups": CONSOLE,
    "POST /v1/bridges/{bridge_id}/resume": WRITE,
    "POST /v1/system/services/{unit}/restart": WRITE,
    "PUT /v1/mesh/settings": WRITE,
    # ---- data commons (#615): the commons is itself the grant-checked door; grants are the owner's oversight
    "GET /v1/data/classes": DOOR,
    "GET /v1/data/classes/{data_class}": DOOR,
    "GET /v1/data/classes/{data_class}/records": DOOR,
    "POST /v1/data/classes/{data_class}/records": DOOR,
    "GET /v1/data/classes/{data_class}/stream": DOOR,
    "GET /v1/data/grants": OVERSIGHT,
    "DELETE /v1/data/grants/{grant_id}": OVERSIGHT,
    # ---- agent browser (#694): its own door with a per-site and per-step owner approval; removing a site is oversight
    "GET /v1/agent-browser/sites": DOOR,
    "POST /v1/agent-browser/sites": DOOR,
    "DELETE /v1/agent-browser/sites/{site_id}": OVERSIGHT,
    "GET /v1/agent-browser/sessions": DOOR,
    "POST /v1/agent-browser/sessions": DOOR,
    "DELETE /v1/agent-browser/sessions/{session_id}": DOOR,
    "POST /v1/agent-browser/sessions/{session_id}/visit": DOOR,
}

# Routes that are to get a generated tool (#632 and the area issues). A ratchet: it may only shrink, and
# tests/test_surfaces.py holds the frozen snapshot it must stay inside.
AWAITING_TOOL: frozenset[str] = frozenset({
    "GET /v1/agents",
    "GET /v1/agents/{name}",
    "GET /v1/apps/{app_id}",
    "GET /v1/apps/{app_id}/access",
    "GET /v1/apps/{app_id}/dependencies",
    "GET /v1/apps/{app_id}/exposure",
    "GET /v1/apps/{app_id}/host-ports",
    "GET /v1/apps/{app_id}/metrics",
    "GET /v1/apps/{app_id}/owner-override",
    "GET /v1/apps/{app_id}/placement",
    "GET /v1/apps/{app_id}/plan",
    "GET /v1/apps/{app_id}/settings",
    "GET /v1/audit/events/{seq}",
    "GET /v1/audit/verify",
    "GET /v1/automation/rules",
    "GET /v1/automation/rules/{rule_id}",
    "GET /v1/automation/runs",
    "GET /v1/automation/schedules",
    "GET /v1/automation/state",
    "GET /v1/backups/content",
    "GET /v1/backups/destinations",
    "GET /v1/backups/runs/{run_id}",
    "GET /v1/backups/snapshots/{snapshot_id}",
    "GET /v1/backups/snapshots/{snapshot_id}/tree",
    "GET /v1/backups/verifications",
    "GET /v1/builtins",
    "GET /v1/databases",
    "GET /v1/domains",
    "GET /v1/fabric",
    "GET /v1/family/apps/{app_id}",
    "GET /v1/family/profiles/{user_id}",
    "GET /v1/files/grants",
    "GET /v1/files/list",
    "GET /v1/files/quotas",
    "GET /v1/files/requests",
    "GET /v1/files/requests/{request_id}",
    "GET /v1/files/roots",
    "GET /v1/files/trash",
    "GET /v1/instance/kiosk",
    "GET /v1/instance/name",
    "GET /v1/machines/capabilities",
    "GET /v1/machines/{name}/snapshots",
    "GET /v1/mesh",
    "GET /v1/migrate/plans",
    "GET /v1/migrate/plans/{plan_id}",
    "GET /v1/migrate/plans/{plan_id}/helper",
    "GET /v1/monitoring/summary",
    "GET /v1/network",
    "GET /v1/nodes/{node_id}/metrics",
    "GET /v1/nodes/{node_id}/wake",
    "GET /v1/notifications/channels",
    "POST /v1/notifications/send",
    "GET /v1/notifications/sources",
    "GET /v1/onboarding/settings",
    "GET /v1/onboarding/state",
    "GET /v1/os/about",
    "GET /v1/photos/library",
    "GET /v1/photos/sources/{source_id}/coverage",
    "GET /v1/photos/sources/{source_id}/receipts",
    "GET /v1/physical/lockout",
    "POST /v1/plans",
    "GET /v1/plugins",
    "GET /v1/plugins/{plugin_id}",
    "GET /v1/plugins/{plugin_id}/settings",
    "GET /v1/plugins/{plugin_id}/tools",
    "GET /v1/radios",
    "GET /v1/restores",
    "GET /v1/restores/{restore_id}",
    "GET /v1/search",
    "GET /v1/series",
    "GET /v1/shares/smb",
    "GET /v1/sources",
    "GET /v1/sources/{source_id}",
    "GET /v1/status",
    "GET /v1/storage/devices",
    "GET /v1/storage/operations/{action_id}",
    "GET /v1/subjects",
    "GET /v1/subjects/check",
    "GET /v1/system-apps",
    "GET /v1/system/controls",
    "GET /v1/system/diagnostics",
    "GET /v1/system/services",
    "GET /v1/tls",
    "GET /v1/update-policy/dry-run",
    "GET /v1/usage",
    "GET /v1/users",
})

# The read areas #632 names, each with the routes that read it. tests/test_mcp_read_tools.py fails when an area
# has no tool, or when one of its routes is neither a tool nor listed above with its reason.
READ_AREAS: dict[str, tuple[str, ...]] = {
    "backups": ("GET /v1/backups/status", "GET /v1/backups/runs", "GET /v1/backups/runs/{run_id}",
                "GET /v1/backups/snapshots", "GET /v1/backups/snapshots/{snapshot_id}",
                "GET /v1/backups/snapshots/{snapshot_id}/tree", "GET /v1/backups/verifications",
                "GET /v1/backups/destinations", "GET /v1/backups/content"),
    "os_updates": ("GET /v1/os/updates", "GET /v1/os/updates/history", "GET /v1/os/about"),
    "files_metadata": ("GET /v1/files/stat", "GET /v1/files/list", "GET /v1/files/roots"),
    "machines": ("GET /v1/machines", "GET /v1/machines/{name}", "GET /v1/machines/{name}/snapshots",
                 "GET /v1/machines/capabilities"),
    "storage": ("GET /v1/storage", "GET /v1/storage/devices", "GET /v1/storage/operations/{action_id}"),
    "alerts": ("GET /v1/alerts", "GET /v1/alerts/{alert_id}"),
    "settings": ("GET /v1/update-policy", "GET /v1/update-policy/dry-run", "GET /v1/onboarding/settings"),
    "logs": ("GET /v1/apps/{app_id}/logs", "GET /v1/system/diagnostics"),
}
