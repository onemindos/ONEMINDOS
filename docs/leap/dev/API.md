<!-- SPDX-License-Identifier: Apache-2.0 -->
# Gateway REST API v1 (completed)

**Status:** proposal for the Phase B build (2026-11-12). Each change to `sdk/contracts/poc-v0.md` that this file needs goes in its own contract PR (that file is a serialized hotspot).
**Epic ids:** `DEV-API-1` to `DEV-API-14` (§14).
**Serves:** brief 30 D-B9.2 to D-B9.8, D-B9.11, B4.2 (`/v1/os/*`), REC-W11-02 and REC-W11-17 (research 12), REC-W5-R13 (research 06), 29 §7, §8.3 and E6/E9, plus the security backlog items H-09, H-10, H-13, H-14, H-16, H-20, H-21, H-22 and H-23 (`docs/security/HARDENING-BACKLOG.md`, on the `secdoc` branch).
**Sister specs:** the CLI, SDK, MCP and plugin SDK specs in `docs/leap/dev/`, and the Phase B feature specs (fabric, backups, notifications, automation, updates). **The feature spec owns the behaviour. This file owns the HTTP shape:** paths, bodies, errors, scopes and versioning. If the two disagree on a field name, this file wins and the feature spec is corrected.

> **Explain it like I am the founder**
> The API is the one door into your box. The dashboard, the phone apps, the `onemind` CLI, the SDKs, MCP and every plugin all go through it. Nothing has a back door.
> Today the door has 10 rooms (nodes, apps, actions). This spec adds the rooms you need to run your own cluster on OneMind: nodes joining, backups and restores, alerts, automations, updates, the audit record, and users and tokens. It also adds a live event feed.
> One rule holds in every room. An AI agent or a plugin can only **ask** for a change. You approve it. The OS does the work. The audit record keeps every step.
> The API is written once, as OpenAPI. The TypeScript, Python and Go SDKs and the CLI are generated from it, so they never drift apart. v1 only ever grows; anything that would break your scripts waits for v2.

---

## 1. Goals and non-goals

**Goals**
1. List every route the gateway serves today, and every route the in-flight branches add, in one table (§3).
2. Define the Phase B core endpoints, so the founder can move his own services onto a OneMind box and run it from the dashboard, the CLI and the phone (§5).
3. Write one rulebook that every endpoint follows: errors, pagination, idempotency, scopes, rate limits, events (§6 to §10).
4. Make **OpenAPI the single source**. The SDKs, the CLI client, the MCP tool schemas and the docs site are generated from it (§11).
5. Promise third-party developers a stable API: v1 is additive only, and breaking changes wait for v2 with a published deprecation window (§12).

**Non-goals (this spec)**
- Identity itself: Kanidm, passkeys and OIDC flows (D-B9.1, D-B9.2). This file defines how the API *uses* a session or a token, not how a person signs in.
- The MCP protocol surface. MCP tools are generated from the same operations (§11.4), and the MCP spec owns the protocol.
- Robotics, drones, TAK and physical actuation endpoints. They come later, and they will reuse the action model unchanged.
- GraphQL, gRPC or a WebSocket API. SSE covers the event feed in v1 (§10). A WebSocket channel can be added later, as an addition.
- Direct NATS access for clients. Clients never connect to NATS; the gateway relays filtered events (research 12 §4).
- The node agent's local API (`onemindd` on `:7480`) is listed in §3.3 for completeness but is not part of the public v1 surface.

---

## 2. Principles every endpoint follows

| # | Principle | What it means in practice |
|---|---|---|
| P1 | **Ask, approve, execute, audit** | Any change made by an agent, plugin or automation is created as an **action** in `awaiting_approval`. Only a person with role `owner` can approve it. The executor runs only approved actions. Every decision goes into the hash-chained audit log. |
| P2 | **Typed requests, not raw writes** | A change is never "PATCH this object to anything". It is a named action type (`backup.restore`, `node.join`) with a validated parameter schema. The approval card shows exactly those parameters. |
| P3 | **Owners may write their own settings directly** | A person `owner` may change low-risk settings without an action: their notification preferences, their own tokens, rule drafts. These writes are still audited. Agents and plugins never get a direct write. |
| P4 | **Read scope is explicit** | Every route names its scope (§8). A token carries scopes. Effective access = role ∩ token scopes ∩ the fixed rules for that principal kind. |
| P5 | **One error envelope** | `{"error": <code>, "message": <text>}` on every failure, plus optional additive fields (§6). |
| P6 | **One spec** | Routes exist in the OpenAPI document or they do not exist. The SPA fallback never answers an API path (`is_api_path` in `core/onemind_core/app.py`). |
| P7 | **Nothing secret in a response** | Secrets are write-only. Tokens are shown once at creation. Notification channel credentials, backup keys and join tokens are never returned by `GET`. |

### 2.1 Two kinds of write

| Kind | Who may call | What happens | HTTP result | Example |
|---|---|---|---|---|
| **Request** (governed change) | person `owner`, `agent`, `plugin`, `automation`, according to scope | An action is created in `awaiting_approval` and returned | `202 Accepted` with the action and a `Location: /v1/actions/{id}` header (`201` for `POST /v1/actions` itself, unchanged) | `POST /v1/backups/{id}/restore` |
| **Direct owner write** | person `owner` only (some also `adult` for their own records) | Applied at once and audited | `200` or `201` with the resource | `PUT /v1/notifications/preferences` |

**Owner shortcut.** On any request endpoint a person `owner` may send `"approve": true`. The gateway creates the action and approves it in one transaction, and audits both steps (`action.requested` then `action.approved`, same approver). Rules:
- An agent, plugin or automation that sends `"approve": true` gets `403 permission_denied` and an `authz.denied` audit line. The action is **not** created.
- If the action type is `destructive` (§5.12), the shortcut also needs a fresh step-up proof (§8.4). Without it: `401 unauthenticated` with `"reason": "step_up_required"`.

---

## 3. What exists today (inventory)

### 3.1 Gateway routes on `main`

Source: `core/onemind_core/app.py` (FastAPI). Port `:8080`. OpenAPI at `/openapi.json`. Contract: `sdk/contracts/poc-v0.md` §3.

| # | Method and path | Auth | Who | Returns | Errors |
|---|---|---|---|---|---|
| 1 | `GET /healthz` | open | anyone | `{"ok": true}` | — |
| 2 | `GET /openapi.json` | open | anyone | the OpenAPI document | — |
| 3 | `GET /v1/instance` | bearer | any principal | `{"name", "version", "hub_node_id"}` | 401 |
| 4 | `GET /v1/nodes` | bearer | any principal | list of heartbeats, each plus `status` (`online` / `stale` / `offline`) and `last_seen` | 401 |
| 5 | `GET /v1/nodes/{node_id}` | bearer | any principal | one node | 401, 404, 422 |
| 6 | `GET /v1/apps` | bearer | any principal | catalog entries with `installed` and `status` | 401 |
| 7 | `POST /v1/actions` | bearer | owner or agent | the action in `awaiting_approval` (201); a replay with the same `idempotency_key` returns the same action (200) | 401, 403, 404, 409, 422 |
| 8 | `GET /v1/actions` | bearer | any principal | all actions | 401 |
| 9 | `GET /v1/actions/{action_id}` | bearer | any principal | one action | 401, 404, 422 |
| 10 | `POST /v1/actions/{action_id}/approve` | bearer | **owner only** | the action after dispatch | 401, 403, 404, 409, 422 |
| 11 | `POST /v1/actions/{action_id}/deny` | bearer | owner only | the action, now `cancelled` | 401, 403, 404, 409, 422 |
| — | `GET /{path}` | open | anyone | dashboard static files with SPA fallback; never answers `v1/*`, `healthz` or `openapi.json` | 404 |

Action types on `main`: `app.install`, `app.remove` (`core/onemind_core/actions.py`). Action ids are UUID v4 (`ledger.py`).

### 3.2 Added by in-flight branches (align with, do not duplicate)

| Branch (worktree) | Adds | Status |
|---|---|---|
| `gwmcp` | `POST /mcp` (MCP Streamable HTTP, protocol 2025-06-18, agents only; tools `list_nodes`, `list_apps`, `request_action`; no approve tool). `GET`/`DELETE /mcp` answer 405. `GET /v1/apps` gains `links`, `tier`, `scan` (typed `CatalogApp` model in `core/onemind_core/models.py`). Approve of `app.install` returns 409 `stale_precondition` without a passing scan newer than 7 days (`scan.py`). Apps with `spec.agent` get a database-stored agent principal (`agent:<app-id>`) at install, revoked at removal. | committed on branch, not merged |
| `updater` | `onemindd update` service and `onemind update status\|check\|apply` (console only). Heartbeat gains an optional `update` object. The README states that "the `/v1/os/*` gateway API ... come[s] later": this spec defines it (§5.6). | **merged** as PR #15 (after this spec was written) |
| `pipeline` | `apps/<id>/scan.json` (contract §11.1), which the catalog reads | committed |
| `deploy-v0` | `deploy/install.sh` join flow with a hub URL and token. This spec replaces the static join token with an owner-approved join (§5.1, H-23). | committed |

### 3.3 Node agent local API (not public)

Source: `internal/agent/agent.go`. Port `:7480`. No auth today; the hardening backlog binds it to loopback (H-24).

| Method and path | Returns |
|---|---|
| `GET /api/v1/node` | the node heartbeat (contract §2) |
| `GET /healthz` | liveness |

Clients must never call `:7480` from off the box. The gateway reads node state from NATS heartbeats, and reaches a node through the fabric command channel (fabric spec). Future local endpoints (`/api/v1/os/*` on a Unix socket, B4.2) stay local and are reached from outside only through the gateway routes in §5.6.

### 3.4 Gaps this spec closes

| Gap on `main` | Where it is closed |
|---|---|
| Lists have no pagination or filters | §7 |
| Only one idempotency mechanism (a body field on `POST /v1/actions`) | §7.3 |
| Roles exist (`owner`, `adult`, `guest`, `agent`) but there are no scopes; any principal reads everything | §8 (H-21, H-22) |
| Static tokens file only; no create, list, rotate, revoke or expiry | §5.9 (H-09) |
| Audit is a file plus a NATS publish; no read or verify API | §5.7 (H-10) |
| No event feed; the dashboard polls | §10 |
| 422 validation errors reuse the code `conflict`; 405 reuses `not_found` | §6.2 |
| No limits on body size, rate or pending actions per agent | §9 (H-14, H-20) |

---

## 4. Resource map (v1 complete)

`R` = read, `Q` = request (creates an action), `W` = direct owner write. New in Phase B unless marked "exists".

| Area | Path prefix | R | Q | W | Section |
|---|---|---|---|---|---|
| Meta | `/healthz`, `/openapi.json`, `/v1/instance` | exists | — | — | §3.1 |
| Fabric (nodes and join) | `/v1/nodes`, `/v1/fabric/*` | yes (nodes exist) | join, drain, remove, relabel | — | §5.1 |
| Apps | `/v1/apps` | exists | via actions (exists) | — | §3.1 |
| Actions | `/v1/actions` | exists, plus filters | exists | approve, deny (exist) | §5.11 |
| Backups | `/v1/backups/*` | yes | run, verify, destination changes, delete | — | §5.2 |
| Restores | `/v1/restores/*` | yes | restore app, restore box | — | §5.3 |
| Notifications | `/v1/notifications/*` | yes | plugin `send` (rate-limited, no approval: it changes no state) | channels, preferences, test, read marks | §5.4 |
| Automation | `/v1/automation/*` | yes | create, enable, change rule (agents); runs file actions | owner create, disable, delete | §5.5 |
| Updates | `/v1/os/*` | status, history, releases | check, apply, postpone, channel, window | — | §5.6 |
| Audit | `/v1/audit/*` | events, verify, checkpoints | — | checkpoint (owner) | §5.7 |
| Users | `/v1/users/*`, `/v1/me` | yes | — | owner | §5.8 |
| Tokens | `/v1/tokens/*` | yes | plugin tokens via app install | create, rotate, revoke | §5.9 |
| Events | `/v1/events` (SSE) | yes | — | — | §10 |
| MCP | `/mcp` | — | `request_action` | — | §11.4, MCP spec |

---

## 5. Phase B endpoints

All bodies are JSON (`Content-Type: application/json`). Times are RFC 3339 UTC. Ids are opaque strings; clients must not parse them. Every request endpoint accepts the common request fields:

```json
{
  "reason": "optional text shown on the approval card, at most 500 characters",
  "expires_at": "optional RFC 3339; default now + 24 h, at most now + 7 d",
  "approve": false
}
```

and the `Idempotency-Key` header (§7.3). Every request endpoint returns `202` with the action:

```json
{
  "id": "6f1c9e0a-2b7d-4c1e-9a55-0d3f8f9b1c42",
  "type": "backup.restore",
  "params": {"snapshot_id": "snap_01JC8Q", "scope": {"app_id": "vaultwarden"}, "mode": "portable"},
  "state": "awaiting_approval",
  "risk": "destructive",
  "requested_by": {"id": "agent:hermes-agent", "kind": "agent"},
  "reason": "Vault data looks corrupted since 02:00",
  "expires_at": "2026-11-13T09:00:00Z",
  "plan_sha256": "sha256:4b1d…",
  "created_at": "2026-11-12T09:00:00Z",
  "updated_at": "2026-11-12T09:00:00Z",
  "result": null
}
```

`risk` and `plan_sha256` are new, additive fields (§5.11).

### 5.1 Fabric: nodes and join

Today a node joins with a long-lived token passed to `deploy/install.sh`, and starts publishing heartbeats. Phase B makes a join an action the owner approves (H-23).

| Method and path | Kind | Scope | Who | Body or query | Returns |
|---|---|---|---|---|---|
| `GET /v1/nodes` | R | `nodes:read` | any | `?status=online,stale,offline&role=hub,node&limit&cursor` | nodes (exists; gains filters and pagination) |
| `GET /v1/nodes/{node_id}` | R | `nodes:read` | any | — | one node (exists) |
| `POST /v1/fabric/join-tickets` | W | `fabric:admin` | owner | `{"role": "node", "expires_in_s": 900, "labels": {"room": "garage"}}` | `201 {"ticket_id", "join_code", "qr_payload", "hub_ca_sha256", "expires_at"}`. The `join_code` is shown **once** |
| `GET /v1/fabric/join-tickets` | R | `fabric:read` | owner | — | tickets without codes: `{ticket_id, role, expires_at, used_by_node_id}` |
| `DELETE /v1/fabric/join-tickets/{ticket_id}` | W | `fabric:admin` | owner | — | `204` |
| `POST /v1/fabric/join-requests` | Q | none (the join code is the credential) | a node | `{"join_code", "node": <heartbeat subset: node_id, hostname, board, arch, os>, "csr_pem"}` | `202` with the `node.join` action, plus `{"poll": "/v1/fabric/join-requests/{id}"}` |
| `GET /v1/fabric/join-requests/{id}` | R | join code | the joining node | header `OneMind-Join-Code` | `{"state", "credentials": null \| {...}}`. Credentials are returned once, after approval |
| `POST /v1/nodes/{node_id}/drain` | Q | `fabric:request` | owner, agent | `{"reason"}` | `202` with `node.drain` |
| `POST /v1/nodes/{node_id}/remove` | Q | `fabric:request` | owner, agent | `{"wipe": false}` | `202` with `node.remove` (destructive) |
| `POST /v1/nodes/{node_id}/labels` | Q | `fabric:request` | owner, agent | `{"set": {"gpu": "true"}, "unset": ["room"]}` | `202` with `node.label` |

Rules:
- A join code is single-use, expires in at most 1 hour, and is bound to the hub's CA fingerprint so the node can pin it. A wrong or used code gets `401 unauthenticated` (rate-limited per source, §9).
- The joining node never becomes a principal until the owner approves. After approval it gets a principal of kind `node` with scopes `nodes:report` only.
- The approval card shows the node's board, arch, OS, hostname and the ticket's labels. It never shows serial numbers, MAC or IP addresses (contract §2).

Example: the owner adds a Pi 5.

```console
$ onemind fabric qr --role node --label room=garage
Join code (valid 15 min, shown once): 7KQ4-M2XP-9D
QR saved to: ./join-garage.png
On the new node run:  onemind fabric join 7KQ4-M2XP-9D --hub https://box.local
```

```http
POST /v1/fabric/join-requests HTTP/1.1
Content-Type: application/json

{"join_code": "7KQ4-M2XP-9D",
 "node": {"node_id": "a41c09e2b7f3", "hostname": "pi-garage", "board": "rpi5", "arch": "arm64",
          "os": {"id": "debian", "version_id": "13"}},
 "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n…"}

HTTP/1.1 202 Accepted
Location: /v1/actions/0b7e…
{"id": "0b7e…", "type": "node.join", "state": "awaiting_approval", "risk": "sensitive", …,
 "poll": "/v1/fabric/join-requests/0b7e…"}
```

### 5.2 Backups

Engine: restic (W5-R1). Agents may **request** a backup run and read status. A restore, a destination change, a key change and a delete always need the owner (W5-R13).

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `GET /v1/backups/status` | R | `backups:read` | any | `{"last_success_at", "last_verified_restore_at", "next_run_at", "health": "ok\|stale\|failing\|not_configured", "destinations": [...]}` |
| `GET /v1/backups/snapshots` | R | `backups:read` | any | snapshots: `{id, taken_at, scope, size_bytes, destination_id, tags, verified_at}`. Filters `?app_id&destination_id&since` |
| `GET /v1/backups/snapshots/{id}` | R | `backups:read` | any | one snapshot, plus its contents summary (apps and volumes, no file listing) |
| `GET /v1/backups/destinations` | R | `backups:read` | owner, adult | destinations without credentials: `{id, kind: "usb\|box\|s3\|rest", label, append_only, last_seen_at}` |
| `POST /v1/backups/runs` | Q | `backups:request` | owner, agent, automation | `{"scope": "box" \| {"app_id"}, "destination_id"}` → `202` with `backup.run` (risk `write`) |
| `GET /v1/backups/runs/{id}` | R | `backups:read` | any | run progress: `{state, started_at, bytes_done, bytes_total, snapshot_id}` |
| `POST /v1/backups/verify` | Q | `backups:request` | owner, agent, automation | `{"snapshot_id" \| "latest": true, "mode": "check\|scratch_restore"}` → `202` with `backup.verify` (risk `write`; it uses disk and CPU) |
| `GET /v1/backups/verifications` | R | `backups:read` | any | verify results: `{id, snapshot_id, mode, result: "pass\|fail", probes, finished_at}` |
| `POST /v1/backups/destinations` | Q | `backups:admin` | owner | `{"kind": "s3", "label", "config": {...}, "credentials": {...}}` → `202` with `backup.destination.add` (risk `sensitive`). Credentials are write-only |
| `DELETE /v1/backups/destinations/{id}` | Q | `backups:admin` | owner | `202` with `backup.destination.remove` (destructive) |
| `DELETE /v1/backups/snapshots/{id}` | Q | `backups:admin` | owner | `202` with `backup.snapshot.delete` (destructive) |

Note: `backup.run` and `backup.verify` start as approval-required like every other action. The owner may later allow them without a tap through an **approval policy** (§5.5.3), which the owner sets. That policy is recorded as the approver (`approved_by: "policy:<id>"`, created by the owner). This is a founder decision (§15, Q1).

### 5.3 Restores

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `POST /v1/restores` | Q | `backups:request` | owner, agent | `{"snapshot_id", "scope": "box" \| {"app_id"}, "mode": "portable\|exact", "target": "in_place\|new_namespace"}` → `202` with `backup.restore` (destructive when `in_place`) |
| `GET /v1/restores` | R | `backups:read` | any | restore records with `?state&app_id` |
| `GET /v1/restores/{id}` | R | `backups:read` | any | `{state, action_id, snapshot_id, scope, started_at, finished_at, health_gate: {verdict, probes}}` |

A restore succeeds only when the restore health gate passes on **fresh** signals (W5-R8). A restore whose gate fails ends in `failed` with the gate verdict, never in `succeeded`.

Example (Python SDK, an agent asks for a restore):

```python
from onemind_sdk import Client

om = Client.from_env()  # reads ONEMIND_GATEWAY_URL and ONEMIND_AGENT_TOKEN
action = om.restores.create(
    snapshot_id="snap_01JC8Q",
    scope={"app_id": "vaultwarden"},
    mode="portable",
    target="in_place",
    reason="Vault data looks corrupted since 02:00",
    idempotency_key="hermes-restore-vaultwarden-2026-11-12",
)
print(action.state)       # "awaiting_approval"
print(action.risk)        # "destructive"
# om.actions.approve(action.id)  -> raises PermissionDenied: agents can never approve
```

### 5.4 Notifications

The alert centre: in-app, Web Push, ntfy/UnifiedPush, email, webhook, Telegram, Matrix (core-alignment NOT-P1 to NOT-P3). iOS follows D-005: the push carries only an opaque "new alert" signal and the app fetches the content from the box.

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `GET /v1/notifications` | R | `notifications:read` | any person (their own inbox) | `{id, severity: "info\|warning\|critical", topic, title, body, source, created_at, read_at, links, action_id}` with `?unread&severity&topic&since` |
| `POST /v1/notifications/{id}/read` | W | `notifications:read` | the recipient | `200` |
| `POST /v1/notifications/read-all` | W | `notifications:read` | the recipient | `{"marked": 12}` |
| `GET /v1/notifications/channels` | R | `notifications:read` | owner, adult | channels without secrets: `{id, kind, label, verified, created_at, owner_user_id}` |
| `POST /v1/notifications/channels` | W | `notifications:write` | owner, adult (own channels) | `{"kind": "ntfy", "label", "config": {"topic_url"}, "secret": {...}}` → `201`. Secret is write-only |
| `PATCH /v1/notifications/channels/{id}` | W | `notifications:write` | the channel's owner | partial update (merge patch) |
| `DELETE /v1/notifications/channels/{id}` | W | `notifications:write` | the channel's owner | `204` |
| `POST /v1/notifications/channels/{id}/test` | W | `notifications:write` | the channel's owner | `{"delivered": true, "latency_ms": 840}` |
| `GET /v1/notifications/preferences` | R | `notifications:read` | any person | the caller's routing table |
| `PUT /v1/notifications/preferences` | W | `notifications:write` | any person (their own) | full replace of the caller's routing table |
| `POST /v1/notifications/send` | send | `notifications:send` | plugin, automation, agent | `{"severity", "topic", "title", "body", "dedupe_key"}` → `202`. Delivered to the owner's channels by preference. No approval (it changes no state), but rate-limited (§9) and audited |
| `POST /v1/push/registrations` | W | `notifications:write` | a person's device | `{"platform": "webpush\|unifiedpush\|apns", "endpoint", "keys"}` → `201` |

Preferences example:

```json
{
  "quiet_hours": {"from": "23:00", "to": "07:00", "except_severity": ["critical"]},
  "routes": [
    {"match": {"topic": "approvals.*"}, "channels": ["ch_phone_push"]},
    {"match": {"severity": "critical"}, "channels": ["ch_phone_push", "ch_email"]},
    {"match": {"topic": "backups.*", "severity": "warning"}, "channels": ["in_app"]}
  ]
}
```

Rules: a plugin cannot choose the channel or the recipient; it sends to the owner by topic and the owner's preferences decide. Bodies are plain text (no HTML), at most 4 KiB. Topics belong to a fixed tree (`approvals`, `backups`, `updates`, `nodes`, `apps`, `security`, `automation`, `plugin.<app-id>`); a plugin may send only under `plugin.<its-app-id>`.

### 5.5 Automation: rules and schedules

An automation is a rule that, when its trigger fires, **requests** actions. It never executes them by itself (core-alignment AUT-P1, AUT-B1).

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `GET /v1/automation/rules` | R | `automation:read` | any | rules: `{id, name, enabled, trigger, conditions, actions, created_by, approval_policy_id, last_fired_at}` |
| `GET /v1/automation/rules/{id}` | R | `automation:read` | any | one rule |
| `POST /v1/automation/rules` | W for owner, Q for others | `automation:write` (owner) or `automation:request` | owner directly; agent or plugin as a request | owner: `201` (created **disabled**). Others: `202` with `automation.rule.create` |
| `PATCH /v1/automation/rules/{id}` | W / Q | as above | as above | owner: `200`; others: `202` with `automation.rule.update` |
| `POST /v1/automation/rules/{id}/enable` | W | `automation:write` | owner | `200`. Agents may request it (`automation.rule.enable`) |
| `POST /v1/automation/rules/{id}/disable` | W | `automation:write` or `automation:request` | owner directly; **anyone with request scope may disable at once** (turning a rule off is always safe) | `200` |
| `DELETE /v1/automation/rules/{id}` | W | `automation:write` | owner | `204` |
| `POST /v1/automation/rules/{id}/dry-run` | R | `automation:read` | any | `{"would_request": [<action previews>], "policy_outcome": "needs_approval\|auto_approved_by_policy"}` |
| `GET /v1/automation/runs` | R | `automation:read` | any | firings: `{id, rule_id, fired_at, trigger_event_id, action_ids, outcome}` |
| `GET /v1/automation/schedules` | R | `automation:read` | any | the next fire time of every schedule trigger |

Rule example:

```json
{
  "name": "Nightly app backup",
  "trigger": {"schedule": {"cron": "0 3 * * *", "timezone": "local"}},
  "conditions": [{"node_status": {"role": "hub", "is": "online"}}],
  "actions": [{"type": "backup.run", "params": {"scope": "box", "destination_id": "dst_usb1"}}],
  "approval_policy_id": "pol_backups_unattended"
}
```

Triggers in v1: `schedule` (cron, 5 fields, at most once per minute), `event` (one SSE event type and a filter on its fields, §10), `manual`. Action types a rule may request are the same as everywhere else; a rule that names a `destructive` type is rejected with `422` unless the founder decision Q2 (§15) allows it.

#### 5.5.3 Approval policies (owner-only)

An approval policy is the owner's standing "yes" for a narrow set of requests, so routine work runs without a tap.

| Method and path | Scope | Who |
|---|---|---|
| `GET /v1/approval-policies` | `actions:read` | any |
| `POST /v1/approval-policies` | `actions:approve` | owner + step-up |
| `DELETE /v1/approval-policies/{id}` | `actions:approve` | owner |

```json
{"id": "pol_backups_unattended",
 "allow": {"types": ["backup.run", "backup.verify"], "requested_by": ["automation:*"]},
 "limits": {"per_day": 4},
 "expires_at": "2027-02-14T00:00:00Z"}
```

Hard limits: a policy can never cover a `sensitive`, `destructive` or `actuate` action type, never covers a request from `kind: agent` unless the owner names that agent exactly, and always has an expiry (at most 90 days). The audit line for an auto-approved action records `approved_by: "policy:pol_backups_unattended"` and the owner who created the policy.

### 5.6 OS updates

Closes the open item in `internal/update/README.md` (`updater` branch): "Gateway approval (REC-DEC-13) is not wired". The gateway reads `status.json` through the node agent and sends approved commands through the fabric channel. Fields come from that README's state machine (`idle`, `downloading`, `installing`, `pending_reboot`, `trial`, `committed`, `rolled_back`, `error`).

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `GET /v1/os/status` | R | `updates:read` | any | per node: `{node_id, booted: {version, slot}, channel, policy, window, state, available: {version, security, notes_url} \| null, last_result, postponed_until}` with `?node_id` |
| `GET /v1/os/history` | R | `updates:read` | any | `{node_id, from_version, to_version, started_at, state, verdict: "committed\|image-bad\|environment-bad\|interrupted", snapshot}` |
| `POST /v1/os/check` | Q | `updates:request` | owner, agent, automation | `{"node_id" \| "all": true}` → `202` with `os.update.check` (risk `read`; the default policy auto-approves it, §5.11) |
| `POST /v1/os/apply` | Q | `updates:request` | owner, agent, automation | `{"node_id", "version", "reboot": "window\|now\|no"}` → `202` with `os.update.apply` (risk `write`; `reboot: now` makes it `destructive`) |
| `POST /v1/os/postpone` | Q | `updates:request` | owner, agent | `{"node_id", "until"}` → `202` with `os.update.postpone` |
| `PUT /v1/os/settings` | Q | `updates:admin` | owner | `{"channel": "security\|stable", "policy": "auto\|notify\|off", "window": "02:00-05:00"}` → `202` with `os.update.settings` (risk `sensitive`; changes only policy keys, H-26) |

The security channel's on-box auto-install (BD-09) stays as decided: it is an owner-set policy, and each install it performs is audited as `approved_by: "policy:os-security-auto"`. `onemind update apply` at the console keeps working and is audited as an owner approval made at the console.

### 5.7 Audit: read, verify and checkpoint

The audit log is hash-chained JSONL (`core/onemind_core/audit.py`): `hash = sha256(prev_hash + canonical_json(line))`. Phase B exposes it read-only and adds signed checkpoints (H-10).

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `GET /v1/audit/events` | R | `audit:read` | owner, adult | records `{seq, ts, event, principal, action_id, data, prev_hash, hash}`. Filters `?after_seq&before_seq&event=action.*&principal_id&action_id&since&until&limit`. Ordered by `seq` |
| `GET /v1/audit/events/{seq}` | R | `audit:read` | owner, adult | one record |
| `GET /v1/audit/verify` | R | `audit:read` | owner, adult | `{"ok": true, "records": 18342, "head": {"seq", "hash"}, "first_bad_seq": null, "checked_at", "last_checkpoint": {...}}`. `?from_seq` checks a range; a full check is cached for 60 s |
| `GET /v1/audit/checkpoints` | R | `audit:read` | owner, adult | `{id, seq, hash, signed_at, key_id, signature, anchors: [{kind, ref, at}]}` |
| `POST /v1/audit/checkpoints` | W | `audit:admin` | owner | `201` with a new checkpoint over the current head. Automatic checkpoints run hourly; this forces one |
| `GET /v1/audit/checkpoints/{id}/proof` | R | `audit:read` | owner, adult | everything an off-box tool needs to check the checkpoint: the signed statement and the public key id |

A checkpoint is a signed statement `{instance_id, seq, hash, signed_at}` made with a box key. Anchors copy it **off the box**: to the owner's phone app, to a backup destination, or to a second box. Then a rewritten log on a compromised box no longer matches a copy the attacker cannot reach. The anchor kinds are defined in the security spec; the API only lists them.

Example:

```console
$ onemind audit verify
Audit chain OK: 18,342 records, head seq 18342 (hash 9c1f…e07a)
Last checkpoint: seq 18300, signed 2026-11-12 08:00, anchored to phone, backup:usb1
```

Audit is never writable through the API. No endpoint deletes or edits a record. Rotation (H-20) seals a segment with a checkpoint first.

### 5.8 Users

Until Kanidm lands (D-B9.1), users are the person principals in the token store. The API shape is fixed now so the dashboard and SDKs do not change when identity moves to Kanidm.

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `GET /v1/me` | R | any valid token | any | `{"principal": {id, kind, role}, "token": {id, scopes, expires_at}, "capabilities": ["can_approve", ...]}` |
| `GET /v1/users` | R | `users:read` | owner | `{id, display_name, role, created_at, last_seen_at, disabled}` |
| `POST /v1/users` | W | `users:admin` | owner + step-up | `{"display_name", "role": "adult\|guest\|owner"}` → `201` with an enrolment link valid 24 h (shown once) |
| `PATCH /v1/users/{id}` | W | `users:admin` | owner + step-up | role or display-name change |
| `POST /v1/users/{id}/disable` | W | `users:admin` | owner | `200`; also revokes the user's tokens and sessions |

Rules: the last active owner cannot be demoted or disabled (`409 conflict`). Roles in v1: `owner`, `adult`, `guest`. The research roles `child` and `operator` (D-B9.1) are added later as new enum values, which v1 allows (§12).

### 5.9 Tokens and scoped tokens (including per-plugin tokens)

Replaces the static tokens file over time (H-09). The file keeps working in v1 and is listed read-only.

| Method and path | Kind | Scope | Who | Returns |
|---|---|---|---|---|
| `GET /v1/tokens` | R | `tokens:read` | owner: all; others: their own | `{id, prefix, name, principal_id, kind, scopes, created_at, expires_at, last_used_at, source: "api\|file\|app-install"}` (never the secret) |
| `POST /v1/tokens` | W | `tokens:admin` (owner) or `tokens:self` (own personal token) | owner; adult for themselves | `{"name", "principal": "self" \| {"kind": "agent", "id": "agent:my-script"}, "scopes": [...], "expires_in_days": 90}` → `201 {"id", "token", ...}`. The `token` value is shown **once** |
| `POST /v1/tokens/{id}/rotate` | W | same as create | same | `201` with the new token; the old one stays valid for `grace_s` (default 0, at most 3600) |
| `DELETE /v1/tokens/{id}` | W | same as create | same | `204` |

**Token format.** `om_<kind>_<random>`: `om_pat_` (person), `om_agt_` (agent), `om_plg_` (plugin), `om_nod_` (node), `om_aut_` (automation). The prefix lets secret scanners (gitleaks) find leaked tokens. Only the sha256 is stored, as today (`auth.py`).

**Per-plugin tokens.** Contract §11.2 already creates an agent principal for an app that declares `spec.agent`. Phase B generalises it:
- A manifest declares `spec.plugin: {principal: true, secret: <name>}` and the scopes it needs in `spec.permissions` ([PLUGIN-SDK.md](PLUGIN-SDK.md) §4.2, manifest v1). The permission names are mapped onto the scopes in §8.2 by the contract PR (C12-A, [DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md) §2).
- At install the approval card lists those scopes, so the owner approves them together with the install.
- The gateway mints a `kind: plugin` principal `plugin:<app-id>` with exactly those scopes, stores it hashed, and writes the token to the Secret in `app-<id>`.
- `app.remove` revokes it. An app update that **adds** scopes is a new approval; removing scopes needs none.
- The owner can see and revoke a plugin's token like any other (`source: "app-install"`). A revoked plugin token is not re-minted until the app is reinstalled or the owner re-grants it.

**Scopes a token can never carry** when its kind is `agent`, `plugin`, `automation` or `node`: `actions:approve`, `users:admin`, `tokens:admin`, `audit:admin`, `backups:admin`, `updates:admin`, `fabric:admin`. The gateway refuses to mint such a token (`403 permission_denied`) and refuses such a scope in a manifest (`422`).

Example (TypeScript SDK, the owner makes a read-only token for a home dashboard script):

```ts
import { OneMind } from "@onemind/sdk";

const om = new OneMind({ baseUrl: "https://box.local", auth: OneMind.staticToken(process.env.ONEMIND_TOKEN!) });
const created = await om.tokens.create({
  name: "wall-tablet",
  principal: { kind: "agent", id: "agent:wall-tablet" },
  scopes: ["nodes:read", "apps:read", "backups:read"],
  expiresInDays: 365,
});
console.log(created.token); // printed once; store it in the tablet's config
```

### 5.10 Instance and capabilities

| Method and path | Kind | Scope | Returns |
|---|---|---|---|
| `GET /v1/instance` | R | `instance:read` | exists; gains `api: {version: "1.4.0", min_client: "1.0.0"}`, `features: ["fabric", "backups", ...]` (additive) |
| `GET /v1/action-types` | R | `actions:read` | every action type the box accepts: `{type, risk, params_schema, since}`. Clients build forms and approval cards from it |

### 5.11 Actions (extended)

Existing routes stay. Additions:

| Change | Detail |
|---|---|
| Filters on `GET /v1/actions` | `?state=awaiting_approval,dispatched&type=backup.*&requested_by=agent:hermes-agent&since&limit&cursor` |
| New fields | `risk` (`read`, `write`, `sensitive`, `destructive`, `actuate`), `reason`, `plan_sha256`, `approved_by`, `approved_via` (`dashboard`, `phone`, `cli`, `policy`, `console`) |
| Approval body (optional) | `POST /v1/actions/{id}/approve` accepts `{"plan_sha256": "…", "webauthn": {...}}` (challenge from `POST /v1/actions/{id}/approve-options`, [SECURITY.md](../core/SECURITY.md) §3.2). If `plan_sha256` does not match the plan the gateway stored for this action ([SANDBOX.md](../core/SANDBOX.md) §3.2): `409 stale_precondition`. This binds the approval to exactly what the owner saw (D-B9.6, H-13) |
| Deny body (optional) | `{"reason": "…"}`, recorded in audit and shown to the requester |
| `POST /v1/actions/{id}/cancel` | The requester withdraws its own pending request (`awaiting_approval` → `cancelled`). Agents may do this; it is not an approval |
| Preview | `GET /v1/actions/{id}/preview` returns "what will change" (objects to create or delete, volumes touched, nodes affected) for the approval card (H-13) |
| Preview before a request | `POST /v1/plans` with `{type, params}` returns the same plan and its `plan_sha256` without filing an action (MCP `preview_action`, SDK `actions.preview`). Name proposed by the §12 draft; settled in C12-A ([DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md) §2) |

Risk levels decide the approval rule:

| Risk | Meaning | Approval |
|---|---|---|
| `read` | No lasting change (`os.update.check`) | Auto-approved by the built-in policy `policy:read-only`. The owner can turn that policy off |
| `write` | A reversible change that adds no power (`backup.run`, `node.label`, `node.drain`) | Owner tap, or an owner-set approval policy |
| `sensitive` | Changes credentials, destinations, update policy or grants, or widens what runs (`app.install`, `node.join`, token create). [AUTOMATION.md](../core/AUTOMATION.md) calls this class "grant-widening" | Owner tap; never covered by a policy |
| `destructive` | Data loss or downtime possible (`app.remove` with data, `backup.restore` in place, `node.remove`, `backup.snapshot.delete`) | Owner tap **plus step-up** (§8.4); never covered by a policy |
| `actuate` | Moves or switches a physical device | Owner tap plus step-up; never covered by a policy; lab-only until LT-VM-18 passes (plan G4) |

### 5.12 Action type catalogue (v1)

| Type | Risk | Params (summary) | Requested by |
|---|---|---|---|
| `app.install` (exists) | sensitive | `{app_id}`; later `{app_id, version, node_selector}` | owner, agent, automation |
| `app.remove` (exists) | write; destructive with `delete_data: true` | `{app_id, delete_data?}` | owner, agent, automation |
| `node.join` | sensitive | `{node_id, hostname, board, arch, role, labels}` | the joining node |
| `node.drain` | write | `{node_id}` | owner, agent, automation |
| `node.remove` | destructive | `{node_id, wipe}` | owner, agent |
| `node.label` | write | `{node_id, set, unset}` | owner, agent, automation |
| `backup.run` | write | `{scope, destination_id}` | owner, agent, automation |
| `backup.verify` | write | `{snapshot_id \| latest, mode}` | owner, agent, automation |
| `backup.restore` | destructive in place; write to a new namespace | `{snapshot_id, scope, mode, target}` | owner, agent |
| `backup.destination.add` / `.remove` | sensitive / destructive | destination config (secrets held aside, never in `params`) | owner |
| `backup.snapshot.delete` | destructive | `{snapshot_id}` | owner |
| `automation.rule.create` / `.update` / `.enable` | write | the rule body | agent, plugin |
| `os.update.check` | read | `{node_id \| all}` | owner, agent, automation |
| `os.update.apply` | write; destructive with `reboot: now` | `{node_id, version, reboot}` | owner, agent, automation |
| `os.update.postpone` | write | `{node_id, until}` | owner, agent |
| `os.update.settings` | sensitive | `{channel, policy, window}` | owner |
| `os.rollback` | destructive | `{node_id}` | owner ([UPDATES.md](../core/UPDATES.md) §3.2) |

Secrets never sit in `params` (they would be in the audit log). An action that carries a secret stores it in a sealed side table keyed by the action id, deletes it after dispatch or expiry, and the audit records only `"credentials": "provided"`.

---

## 6. Error model

### 6.1 Envelope

Unchanged from contract §3, plus optional additive fields:

```json
{
  "error": "stale_precondition",
  "message": "app uptime-kuma has no passing scan newer than 7 days",
  "request_id": "req_01JC8R4T2Z",
  "details": [{"field": "params.app_id", "problem": "scan stale"}],
  "retry_after_s": null,
  "docs": "https://docs.onemind…/errors/stale_precondition"
}
```

- `error` and `message` are always present. Clients branch on `error`, never on `message`.
- Every response (success or failure) carries a `OneMind-Request-Id` header; the gateway writes it to its log, and to the audit line when there is one.
- `401` responses carry `WWW-Authenticate: Bearer` (exists).

### 6.2 Codes

| Code | HTTP | When | Status |
|---|---|---|---|
| `unauthenticated` | 401 | Missing, unknown, expired or revoked token; step-up missing (`details[0].problem = "step_up_required"`) | exists |
| `permission_denied` | 403 | Valid principal, not allowed (scope, role, kind) | exists |
| `not_found` | 404 | No such resource, or the caller may not know it exists | exists |
| `conflict` | 409 | State does not allow it (e.g. demote the last owner, approve a finished action) | exists |
| `stale_precondition` | 409 | A precondition the caller relied on changed (scan stale, `plan_sha256` mismatch, `If-Match` mismatch) | exists |
| `expired` | 409 | The action or ticket passed its `expires_at` | exists |
| `outcome_unknown` | 502 | The executor did not report; the action is `outcome_unknown` and will not be redispatched | exists |
| `invalid_request` | 422 | The body or query fails the schema | **new** (v1 keeps sending `conflict` on 422 until v2; see below) |
| `method_not_allowed` | 405 | Wrong method on an existing path | **new** (replaces `not_found` on 405) |
| `payload_too_large` | 413 | Body over the limit (§9) | **new** |
| `rate_limited` | 429 | A limit in §9 was hit; `Retry-After` header and `retry_after_s` field | **new** |
| `offline_not_supported` | 409 | The request needs a node or destination that is offline | **new** (D-B9.8) |
| `unavailable` | 503 | The gateway is starting, or a dependency (database) is down | **new** |

**Compatibility for 422 and 405.** On `main`, a validation failure is `422 conflict` and a wrong method is `405 not_found` (`errors.py`). Changing the code string would break a v0 client that matched it. So in v1:
- The HTTP status is the contract (422 and 405 already).
- v1 keeps `"error": "conflict"` on 422 and adds `"details"` with the bad fields. A client that sends `OneMind-Errors: 2` gets `"error": "invalid_request"` and `"method_not_allowed"` now.
- v2 makes the new codes the default.

**Rule for clients:** treat an unknown `error` value by its HTTP status class. New codes are allowed in v1 (§12).

---

## 7. Lists, pagination, filtering and idempotency

### 7.1 Pagination

Every list endpoint returns a **JSON array**, as `GET /v1/nodes`, `/v1/apps` and `/v1/actions` do today, so v0 clients keep working. Pagination is in headers:

| Request | Meaning |
|---|---|
| `?limit=50` | Page size. Default 100, maximum 500. Today's list endpoints keep returning everything when `limit` is absent, up to 1,000 items, and add the `Link` header if there are more |
| `?cursor=<opaque>` | Continue from a previous page |

| Response header | Meaning |
|---|---|
| `Link: </v1/actions?cursor=eyJ…&limit=50>; rel="next"` | RFC 8288; absent on the last page |
| `OneMind-Total-Estimate: 1840` | Optional; may be absent on large tables |

Cursors are opaque, stable under inserts, and valid for 24 hours. The SDKs expose them as async iterators (`for await (const a of om.actions.list({state: "awaiting_approval"}))`).

### 7.2 Filtering and sorting

- Filters are query parameters named after fields. A comma means OR within one field; different fields are ANDed.
- Glob filters end in `.*` (`type=backup.*`, `event=action.*`).
- Time windows use `since` and `until` (RFC 3339).
- Sort is fixed per resource and documented (newest first, except audit by `seq` ascending). There is no general `sort` parameter in v1.

### 7.3 Idempotency

| Endpoint | Mechanism |
|---|---|
| `POST /v1/actions` | Body field `idempotency_key` (exists, required). Kept for ever in the ledger |
| Every other `POST` that creates something | `Idempotency-Key` header (optional, at most 200 characters). Kept for 24 hours per principal |

Behaviour, both mechanisms:
- Same key, same principal, same body → the first response is replayed with status `200` (or the original status for non-create calls) and header `OneMind-Idempotent-Replay: true`.
- Same key, different body → `409 conflict` ("idempotency key reused with different parameters").
- Same key from another principal → treated as a different key.
- SDKs generate a key for every request call by default, so a network retry never creates two actions.

### 7.4 Concurrency on direct writes

Direct owner writes on mutable resources (`/v1/automation/rules/{id}`, `/v1/notifications/channels/{id}`, `/v1/notifications/preferences`, `/v1/users/{id}`) return an `ETag`. A `PATCH` or `PUT` with `If-Match` that no longer matches gets `409 stale_precondition`. `If-Match` is optional in v1 and the SDKs always send it.

---

## 8. Authentication and scopes

### 8.1 Credentials

| Client | Credential | Status |
|---|---|---|
| CLI, SDK, scripts | `Authorization: Bearer om_…` | exists (static file); Phase B adds API-issued tokens (§5.9) |
| Dashboard and phone web view | Same-origin session cookie (`HttpOnly`, `Secure`, `SameSite=Strict`) **plus** CSRF token header `OneMind-CSRF` on every non-GET | Phase B with identity (H-16: never cookies without CSRF) |
| Phone app (native shell) | OIDC auth code + PKCE → short-lived bearer access token + refresh token | with Kanidm (D-B9.2) |
| Plugin in its pod | `om_plg_` token from the Secret written at install | Phase B (§5.9) |
| Node | `om_nod_` token or mTLS client certificate from the join flow | Phase B (§5.1) |
| MCP client | Bearer today; OAuth via the authorization-server façade (RFC 9728, RFC 8707) later | MCP spec |

HTTPS is required for every non-loopback call (H-05). Plain HTTP is accepted only on loopback, and the gateway binds to localhost by default.

### 8.2 Scope list (v1)

| Scope | Grants | Allowed for kinds |
|---|---|---|
| `instance:read` | `/v1/instance`, `/v1/me` | all |
| `nodes:read` | nodes | all |
| `nodes:report` | publish its own heartbeat | node |
| `apps:read` | catalog | all |
| `actions:read` | actions, action types, approval policies | all |
| `actions:request` | `POST /v1/actions` and request endpoints that create app actions | person, agent, plugin, automation |
| `actions:approve` | approve, deny, approval policies | **person owner only** |
| `fabric:read` / `fabric:request` / `fabric:admin` | fabric | read: all; request: person, agent, automation; admin: owner |
| `backups:read` / `backups:request` / `backups:admin` | backups, restores | read: all; request: person, agent, automation; admin: owner |
| `notifications:read` / `notifications:write` | own inbox, own channels and preferences | person |
| `notifications:send` | `POST /v1/notifications/send` | plugin, agent, automation |
| `automation:read` / `automation:request` / `automation:write` | rules | read: all; request: agent, plugin; write: owner |
| `updates:read` / `updates:request` / `updates:admin` | `/v1/os/*` | read: all; request: person, agent, automation; admin: owner |
| `audit:read` / `audit:admin` | audit | read: owner, adult; admin: owner |
| `users:read` / `users:admin` | users | owner |
| `tokens:self` / `tokens:read` / `tokens:admin` | tokens | self: person; read: person; admin: owner |
| `events:read` | `/v1/events`, filtered by the caller's other read scopes | all |

**Role defaults** (what a person's session gets):

| Role | Scopes |
|---|---|
| `owner` | all |
| `adult` | every `:read` except `users:read`, plus `notifications:write`, `tokens:self`, `actions:request` |
| `guest` | `instance:read`, `nodes:read`, `apps:read`, `notifications:read` |

Today every principal reads everything. Turning on role defaults for `adult` and `guest` (H-21) is a behaviour change for those roles only; it ships behind the instance setting `api.enforce_role_scopes` (default on for new boxes, off for boxes upgraded from v0 until the owner turns it on), so no existing script breaks silently.

**Effective access** = role defaults (for persons) or the token's scopes (for everyone else) ∩ the "allowed for kinds" column ∩ resource ownership (own inbox, own tokens). A static-file token with no `scopes` key gets its role defaults, which keeps v0 token files working.

### 8.3 Agent tool scopes

An agent token can also narrow which action types it may request: `actions:request:backup.run`, `actions:request:app.install`. Without a suffix, `actions:request` allows every type the kind may request. This is the per-tool scope of H-22; the MCP endpoint applies the same check to `request_action`.

### 8.4 Step-up

A `destructive` approval, user or token administration and approval-policy creation need a fresh proof of presence:
- Web and phone: a WebAuthn assertion made in the last 5 minutes, sent as `"webauthn": {...}` in the approve body, signed over the challenge from `POST /v1/actions/{id}/approve-options`, which binds the action id and `plan_sha256` ([SECURITY.md](../core/SECURITY.md) §3.2). Founder decision F-2 (proposed default, [DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md)): once passkeys exist, every owner approval uses one; the `destructive` rule here is the minimum.
- CLI: `onemind actions approve <id>` opens the browser for the passkey prompt, or uses a device-bound token that the owner enrolled with a passkey.
- Missing or stale → `401 unauthenticated`, `details[0].problem = "step_up_required"`.
Until passkeys land (D-B9.1), step-up is a re-entry of the owner token in the dashboard, and this limitation is shown on the approval card.

---

## 9. Rate limits and size limits

Token bucket per principal (per source address for unauthenticated routes). Defaults below; the owner can raise them in instance settings.

| Class | Applies to | Default |
|---|---|---|
| `read` | every `GET` | 20 requests per second, burst 60 |
| `request` | request endpoints, `POST /v1/actions` | 2 per second, burst 10, **and at most 10 actions in `awaiting_approval` per requester** (H-14; the same cap as [MCP.md](MCP.md) §5.4 and [SECURITY.md](../core/SECURITY.md) §3.8) |
| `send` | `POST /v1/notifications/send` | 10 per minute per plugin; same `dedupe_key` within 10 minutes is merged |
| `auth` | wrong tokens and join codes per source | 10 per minute, then 15-minute back-off (the existing audit throttle of one `auth.rejected` line per minute stays) |
| `events` | open SSE streams | 5 per principal |
| `mcp` | `POST /mcp` | same as `read` and `request`, by the tool called |

Responses carry `RateLimit-Policy` and `RateLimit` headers (IETF HTTPAPI draft) on limited classes. Over the limit: `429 rate_limited` with `Retry-After` in seconds.

Size limits (H-20): request bodies at most 256 KiB (the MCP endpoint's existing limit); `reason` fields at most 500 characters; `limit` at most 500; filters at most 20 values each. Over → `413 payload_too_large` or `422`.

---

## 10. Events stream (SSE)

`GET /v1/events` with `Accept: text/event-stream`. One-way, from box to client. Chosen over WebSocket for v1 because it works through every proxy, resumes with a standard header, and the browser reconnects by itself. Research 12 REC-W11-02 proposed a WebSocket or NATS-relay stream; SSE meets the same need, and a WebSocket channel can be added later without a breaking change.

**Query:** `?types=action.*,node.status,backup.*&since_id=<id>`. Without `types`: everything the caller may read.

**Wire format:**

```text
id: 18342
event: action.state_changed
data: {"schema":"onemind.event/v1","id":"18342","type":"action.state_changed","ts":"2026-11-12T09:01:12Z","subject":{"action_id":"6f1c9e0a-…"},"data":{"from":"awaiting_approval","to":"accepted","by":"person:owner"}}

: keepalive

```

- `id` is a monotonic event id. Audit-derived events use the audit `seq`; others share the same sequence space.
- Resume with the `Last-Event-ID` header (the browser sends it) or `since_id`. The gateway replays from a buffer of the last 24 hours or 10,000 events. If the id is older, the first event is `stream.reset` and the client must re-read state through the REST endpoints.
- A comment line `: keepalive` every 15 seconds.
- Events are **filtered by scope** before sending: a guest never sees audit events, and a plugin sees only events for its own app plus `node.status`.
- Events carry ids and states, not secrets or full bodies. The client fetches details through REST.

**Event types (v1):**

| Type | When |
|---|---|
| `action.requested`, `action.state_changed` | Action lifecycle |
| `node.status` | A node's status changes (`online`, `stale`, `offline`), not every heartbeat |
| `node.join_requested`, `node.joined`, `node.removed` | Fabric |
| `app.status` | An app's install status changes |
| `backup.run.finished`, `backup.verify.finished`, `backup.health` | Backups |
| `restore.state_changed` | Restores |
| `os.update.state` | Update state machine transitions (§5.6) |
| `notification.created` | A new item in the caller's inbox |
| `automation.fired` | A rule fired |
| `audit.appended` | Every audit line (scope `audit:read` only) |
| `audit.checkpoint` | A checkpoint was signed |
| `stream.reset` | The resume id is outside the buffer |

New event types are additive in v1. Clients must ignore types they do not know.

Example (Go SDK):

```go
stream, err := om.Events.Subscribe(ctx, onemind.EventFilter{Types: []string{"action.*"}})
if err != nil { return err }
for ev := range stream.C {
    if ev.Type == "action.requested" {
        a, _ := om.Actions.Get(ctx, ev.Subject.ActionID)
        fmt.Printf("%s wants %s %v\n", a.RequestedBy.ID, a.Type, a.Params)
    }
}
```

---

## 11. OpenAPI as the single source

### 11.1 Where the spec lives

| Artifact | Path | Who writes it |
|---|---|---|
| Live spec | `GET /openapi.json` (FastAPI generates it from the route and Pydantic models) | the gateway code |
| Committed snapshot | `sdk/openapi/onemind-v1.json` (OpenAPI 3.1) | generated by `make openapi`, never edited by hand |
| Breaking-change gate | CI job `api-compat`: diffs the PR's generated spec against `main`'s snapshot with `oasdiff` (`breaking` mode) and fails on any breaking change under `/v1` | DEV-API-2 |
| Error, event and action-type schemas | `sdk/schema/onemind.event.schema.json`, `sdk/schema/onemind.action-types.json` (JSON Schema 2020-12), referenced from the OpenAPI document | generated from the same Pydantic models |

Every operation has a stable `operationId` (`listNodes`, `createRestore`, `approveAction`), one tag per resource, and the extensions:
- `x-onemind-scope: "backups:request"`
- `x-onemind-kind: "request" | "read" | "write"`
- `x-onemind-since: "1.3"` (the API minor that added it)
- `x-onemind-mcp: {"tool": "request_restore"}` when the operation is exposed as an MCP tool

The CI gate also checks that every operation has a scope, an error list and an example.

### 11.2 Generated SDKs

Generators, package layout, publishing and the SSE client are owned by [SDK.md](SDK.md); this table is the summary and follows it.

| Language | Package | Generator (pinned in `os/versions.lock.yaml`) | Hand-written layer |
|---|---|---|---|
| TypeScript | `@onemind/sdk` (also used by the dashboard, replacing `dashboard/src/api`) | `openapi-typescript` types + a thin fetch client | auth, pagination iterators, SSE, idempotency keys, retries |
| Python | `onemind-sdk` (import `onemind_sdk`) | `datamodel-code-generator` (pydantic v2 models) | the same helpers; `Client.from_env()` |
| Go | `github.com/onemindos/onemindos/sdk/go` (package `onemind`; also used by `cmd/onemind`) | `oapi-codegen` v2, models only | the same helpers |

Rules:
- The generated code is committed and rebuilt in CI. A PR that changes the spec without regenerating fails.
- Hand-written layers never re-declare request or response types.
- SDK major version = API major version. The SDK minor follows the API minor it was generated from.
- The SDK sends `User-Agent: onemind-sdk-<lang>/<version>` and `OneMind-API-Version: 1`.

### 11.3 The CLI

`cmd/onemind` uses the Go SDK for every gateway call (today `onemind nodes` makes its own HTTP call). Commands map one-to-one to operations (`onemind backups runs create` = `createBackupRun`), and friendly aliases sit on top (`onemind backup now`). The CLI spec owns the command tree.

### 11.4 MCP

MCP tool definitions for agents are generated from operations tagged `x-onemind-mcp`. Only read operations and request operations may be tagged. CI fails if an operation with scope `actions:approve` or any `:admin` scope carries the tag. That makes "no approve tool" a build rule, not a convention. The existing three tools (`list_nodes`, `list_apps`, `request_action`) keep their names.

---

## 12. Versioning, compatibility and deprecation

### 12.1 v1 is additive only

| Allowed in v1 (minor bump, e.g. 1.3 → 1.4) | Not allowed in v1 (needs v2) |
|---|---|
| New endpoints | Removing or renaming an endpoint, field or query parameter |
| New optional request fields and query parameters | Making an optional field required |
| New response fields | Changing a field's type or format, or its meaning |
| New enum values (action types, states, roles, event types, error codes) | Changing a status code for an existing case |
| New headers | Tightening validation so a request that was valid is now rejected (except security fixes, §12.4) |
| Raising a limit | Lowering a documented limit below what clients were promised |

**Client obligations**, written in every SDK's README and the docs site: ignore unknown fields, treat unknown enum values as "other", treat unknown error codes by HTTP status, follow `Link` headers, and never parse ids.

### 12.2 Version signals

- Path: `/v1/...`. A future `/v2/...` is served next to `/v1` by the same gateway.
- `GET /v1/instance` returns `api.version` (semver of the OpenAPI document) and `features`.
- Responses carry `OneMind-API-Version: 1.4.0`.
- The SDK checks `api.version` at first call and warns if the box is older than the SDK expects for a call (the server returns `404 not_found` for an unknown route, and the SDK turns that into "this box's API is 1.2; this needs 1.3").

### 12.3 Deprecation and v2 rules

1. A field or route is marked `deprecated: true` in OpenAPI, and responses that use it carry `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) headers plus a `Link: <docs>; rel="deprecation"`.
2. A deprecated v1 element keeps working until v1 itself is retired. Nothing is removed from v1.
3. v2 is cut only when the list of breaking changes justifies it. The list will live in `docs/leap/dev/API-V2-QUEUE.md`, created by DEV-API-2 (the first entries: the 422/405 error codes from §6.2, envelope-style lists if wanted, required `plan_sha256` on approve).
4. When v2 ships, v1 stays served for **at least 12 months** and across at least two OS feature releases, whichever is longer. The owner sees v1 usage per token on the security page before it is turned off.
5. The plugin API level (29 §10, `compat.onemind` in the manifest) names the API major it needs. A box refuses a plugin that needs an API major the box does not serve.

### 12.4 Security exception

A security fix may tighten v1 behaviour (for example refuse a scope combination) without waiting for v2. It ships with a security advisory, a changelog entry and, where possible, an instance setting to restore the old behaviour for 30 days.

---

## 13. Security model (summary)

| Threat | Control in this API |
|---|---|
| An agent approves its own request (OpenClaw class) | `actions:approve` cannot be minted for non-persons; the approve route checks kind `person` and role `owner` (exists, `auth.py` `is_owner`); MCP has no approve tool, enforced by CI (§11.4) |
| Approval of something other than what the owner saw | `plan_sha256` binding and the preview (§5.11) |
| A prompt-injected agent floods the owner | Pending-action cap per requester, request rate limit (§9) |
| A plugin escalates through the API | Per-plugin token with only the scopes the owner approved at install; new scopes need a new approval (§5.9) |
| Token theft | Prefixes for leak scanning, hash-only storage, expiry, rotation, revocation, last-used shown to the owner (§5.9) |
| CSRF on the dashboard | Cookie sessions only with a CSRF header (§8.1, H-16) |
| Secrets leaking through audit or responses | Secrets write-only, never in `params`, never in events (§5.12, §10) |
| A rewritten audit log | Hash chain plus signed, off-box anchored checkpoints (§5.7) |
| A rogue node joining | Single-use, short-lived, CA-bound join codes; owner approval before any credential (§5.1) |
| Enumeration | `404 not_found` for resources the caller may not see; join and token errors rate-limited (§9) |
| Plaintext on the LAN | HTTPS everywhere except loopback (§8.1, H-05) |

---

## 14. Test plan and acceptance criteria

| # | Test | Accepts when | Where |
|---|---|---|---|
| T1 | Route inventory | Every route in `/openapi.json` appears in §3/§5 of this file, and every v1 route here exists in the spec at the epic's end (script compares the two) | `core/tests/test_openapi_inventory.py` |
| T2 | Compatibility gate | `oasdiff breaking` against `main`'s snapshot reports nothing under `/v1`; a deliberate breaking change in a test branch fails CI | CI `api-compat` |
| T3 | No self-approval | For every action type: an agent, plugin, automation and node token get 403 on approve, on `"approve": true`, and on creating a policy; each leaves an `authz.denied` audit line | `core/tests/test_authz_matrix.py` |
| T4 | Scope matrix | Generated from the scope table: every route × every kind × every role returns the documented status | same |
| T5 | Unmintable scopes | Creating a non-person token with any scope from the forbidden list returns 403; a manifest with one returns 422 | `test_tokens.py` |
| T6 | Idempotency | Same key + same body → one action, replay header; same key + different body → 409; concurrent duplicates (20 threads) → one action | `test_idempotency.py` |
| T7 | Pagination | 2,500 actions: following `Link` returns each exactly once with inserts during the walk; v0 call without `limit` still returns an array | `test_pagination.py` |
| T8 | Digest binding | Approve with a stale `plan_sha256` → 409 `stale_precondition`, action stays `awaiting_approval` | `test_actions.py` |
| T9 | SSE | Resume with `Last-Event-ID` gets no gap and no duplicate; a guest receives no `audit.*`; `stream.reset` after the buffer | `test_events.py` |
| T10 | Audit verify | Tampering one line makes `GET /v1/audit/verify` return `ok: false` and the right `first_bad_seq`; a checkpoint verifies with only the public key | `test_audit_api.py` |
| T11 | Rate limits | The 11th pending action from one agent → 429 with `Retry-After`; reads under the limit are unaffected | `test_limits.py` |
| T12 | Secrets | A grep of every response body, audit line and event in the test run finds no channel secret, token value (after creation) or backup credential | `test_no_secrets.py` |
| T13 | SDK parity | The same scenario script (list nodes, request restore, try to approve as agent, approve as owner, stream events) passes in TypeScript, Python and Go against a compose hub | `sdk/conformance/` |
| T14 | End to end | On the compose hub (`noop` executor): node joins through a ticket and approval; backup run and verify through a policy; agent-requested restore approved by the owner; the audit verify is green; every step has one audit line with requester and approver | `deploy/verify/verify.sh` extension |

**Definition of done for "API v1 complete":** T1 to T14 green in CI; the OpenAPI snapshot published on the docs site; the three SDKs published at `1.x`; `cmd/onemind` and the dashboard use the generated clients.

---

## 15. Build plan

### 15.1 Epics

| Id | Title | Size | Depends on | Owns (files) |
|---|---|---|---|---|
| DEV-API-1 | Inventory, conventions and route registration seam | S | — | `core/onemind_core/routes.py` (new: one `register(app, deps)` per feature module, so feature PRs do not all edit `app.py`), one serialized edit of `app.py` |
| DEV-API-2 | OpenAPI snapshot, `api-compat` CI gate, extensions linter | S | 1, DEV-SDK-1 (produces `sdk/openapi/onemind-v1.json`) | `sdk/openapi/compat/` (baseline for oasdiff), `.github/workflows/api-compat.yml`, `Makefile` target |
| DEV-API-3 | Errors v1, request ids, size limits | S | 1, contract C12-A (new codes) | `core/onemind_core/errors.py`, `core/onemind_core/limits.py` (new) |
| DEV-API-4 | Pagination, filters, ETags, idempotency header | M | 1 | `core/onemind_core/listing.py`, `core/onemind_core/idempotency.py` (new) |
| DEV-API-5 | Scopes, role defaults, `/v1/me`, step-up hook | M | 1, 3 | `core/onemind_core/scopes.py` (new), `auth.py` |
| DEV-API-6 | Tokens API and per-plugin tokens | M | 5, gwmcp merged, CORE-SEC-3 (token lifecycle, same file, lands first) | `core/onemind_core/tokens.py` (new), `ledger.py` (token table) |
| DEV-API-7 | Actions v1: risk, digest, preview, cancel, action-type registry, approval policies, pending cap | M | 5 | `actions.py`, `core/onemind_core/action_types.py` (new). Approval policies live in `policies.py`, owned by CORE-AUTO-3 |
| DEV-API-8 | Events SSE | M | 5, 7 | `core/onemind_core/events.py` (new) |
| DEV-API-9 | Audit read, verify, checkpoints | M | 5 | `core/onemind_core/audit_api.py` (new), `audit.py` (checkpoint signing) |
| DEV-API-10 | Fabric routes (route shapes; built inside CORE-FABRIC-1, which owns the file) | M | 7, fabric spec, deploy-v0 merged | `core/onemind_core/fabric.py` (new) |
| DEV-API-11 | Backups and restores routes (route shapes; built inside CORE-BACKUP-8, which owns the file) | M | 7, backups spec (backup agent) | `core/onemind_core/backups.py` (new) |
| DEV-API-12 | Notifications routes (route shapes; built inside CORE-NOTIFY-1, which owns the files) | M | 5, notifications spec | `core/onemind_core/notify/` package and `alerts.py` |
| DEV-API-13 | Automation routes and OS update routes (route shapes; built inside CORE-AUTO-2 and CORE-UPDATE-2, which own the files) | M | 7, 8, automation spec, updater merged | `core/onemind_core/automation.py`, `core/onemind_core/os_updates.py` (new) |
| DEV-API-14 | **Superseded** by DEV-SDK-1…10 ([SDK.md](SDK.md)); the id stays so old links resolve | – | 2, 4, 8 | `sdk/ts/`, `sdk/python/`, `sdk/go/`, `sdk/conformance/`; CLI and dashboard switch-over PRs owned by their streams |

### 15.2 Order and phases

| Phase | Epics | Result |
|---|---|---|
| B0 (week 1) | 1, 2, 3 | Every later PR is checked for breaking changes and has the error model |
| B1 (weeks 1-3) | 4, 5, 7 | The rulebook works on the existing routes; approval binding and pending cap on |
| B2 (weeks 2-4) | 6, 8, 9 | Tokens, live events, audit screen and `onemind audit verify` possible |
| B3 (weeks 3-8, follows the feature specs) | 10, 11, 12, 13 | Phase B core endpoints |
| B4 (from week 3, rolling) | DEV-SDK-2…9 (was 14) | SDKs regenerate on every merge; conformance runs in CI |

### 15.3 Collision rules

- One module per feature in `core/onemind_core/`, registered through `routes.py` (DEV-API-1). After that epic, a feature PR adds one line to `routes.py`; `app.py` is not edited again.
- Serialized hotspots: `core/onemind_core/app.py` (DEV-API-1 only), `sdk/contracts/poc-v0.md` (one contract PR per phase: §3 errors and scopes in B1, new action types in B3), `os/versions.lock.yaml` (generator pins in DEV-SDK-2), `cmd/onemindd/main.go` (not touched by this spec).
- `ledger.py` migrations: one migration file per epic, numbered when merged.
- `sdk/openapi/onemind-v1.json` is regenerated, never merged by hand. On a conflict, rebase and run `make openapi`.
- Branch names: `feat/api-<epic-number>-<slug>`, e.g. `feat/api-7-actions-v1`.

---

## 16. Open questions for the founder

| # | Question | Proposed answer |
|---|---|---|
| Q1 | May routine actions (`backup.run`, `backup.verify`, `os.update.check`) run through an owner-set approval policy, without a tap each time? | Yes, for `read` and `write` risk only, with expiry and daily limits; never for `sensitive` or `destructive` (§5.5.3) |
| Q2 | May an automation rule request a `destructive` action at all? | No in v1; it may notify instead |
| Q3 | Should `adult` and `guest` lose read access to things they read today when an upgraded box turns on role scopes? | Off by default on upgraded boxes, on for new boxes (§8.2) |
| Q4 | Approval step-up before passkeys exist | Token re-entry, shown as a limitation on the card (§8.4) |

## 17. Follow-ups found while writing (not fixed here)

- `errors.py` maps HTTP 405 to `not_found` and 422 to `conflict`; §6.2 handles both without breaking v0 clients.
- Contract §3 says the gateway publishes audit lines on NATS `onemind.audit`; the event stream (§10) should read from the same append path so the two never disagree.
- `cmd/onemind nodes` makes its own HTTP call; it should move to the Go SDK in DEV-SDK-5.
- `internal/update/README.md` (updater branch) notes TUF expiry values that differ from brief 30 B4.3; not an API matter, flagged to the updates spec.
