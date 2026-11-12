<!-- SPDX-License-Identifier: Apache-2.0 -->
# Contract §12 (draft): phase-B interfaces

**Status:** DRAFT, not binding (2026-11-12). It proposes §12 of [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md). It follows the contract's rule: "a change to it is a separate PR that all streams adopt". Each sub-section below is meant to be merged **on its own**, when the build step that needs it starts (§12.15). Until then, streams build against §1–§11.
**Design rationale:** [FABRIC.md](FABRIC.md), [BACKUPS.md](BACKUPS.md), [DEPLOYMENTS.md](DEPLOYMENTS.md), [AUTOMATION.md](AUTOMATION.md), [NOTIFICATIONS.md](NOTIFICATIONS.md).
**Compatibility:** everything here is **additive**. No §3 path, field, state or error changes meaning. Clients written for §3 and §11 keep working. Two changes alter behaviour and are listed for an explicit decision at the end: the `reconcile_interrupted` amendment (§12.2 `hold`) and `acknowledge_unscanned` (open item 4).

## 12.1 Conventions

**Principals.** §3's `{id, kind, role}` gains kinds:
- `automation` (id `automation:<id>`, role `automation`): may request, never approve.
- `node` (id `node:<node_id>`, role `node`): may request only `node.join`, and only with a join ticket.
- `person` and `agent` stay as §3 defines them.

A **decider** (`decided_by`) is a person with role owner, or `{"id": "policy:<id>@<rev>", "kind": "policy"}`.

**Errors.** The §3 envelope gains an optional machine-readable `reason`:
```json
{"error": "stale_precondition", "message": "the plan changed since the request", "reason": "plan_changed"}
```
New error codes (each a contract change; nothing else is added):

| Code | HTTP | Use |
|---|---|---|
| `rate_limited` | 429 | Join, webhook and login endpoints; per-person notification caps do not use it (they summarise instead). Sets `Retry-After` |
| `unavailable` | 503 | A dependency the request needs is down: NATS for a job, a node that is `offline`, a backup target that is unreachable. D-B9.8's `offline_not_supported` is folded into this with `reason: node_offline` |

Reasons used in this draft: `plan_changed`, `assertion_required`, `assertion_invalid`, `ticket_used`, `ticket_unknown`, `duplicate_node_id`, `dry_run_required`, `policy_never_allowed`, `limit_reached`, `not_drained`, `version_mismatch`, `node_offline`, `target_unreachable`, `too_many_pending` (H-14), `unscanned_not_acknowledged`, `scan_stale` (§11.1). New reasons may be added without a contract change; codes may not.

**Lists.** New list endpoints take `?limit=` (default 50, max 500) and `?cursor=` and return `{"items": […], "next_cursor": "…" | null}`. The §3 lists keep their bare-array shape.

**Live stream.** `GET /v1/stream` (any principal) is server-sent events. Each message is `event: <type>` with `data:` holding an `onemind.event.v1` envelope (§12.3), filtered to what the principal may see. Clients reconnect with `Last-Event-ID`. The dashboard and the phone use it instead of polling.

**One-time outputs.** A response may carry `"one_time": {…}`: secrets shown once (join ticket, recovery key, webhook secret). They are never stored in clear, logged, put in the audit log, or returned again.

**Sealed input.** A request may carry `"sealed": {"alg": "X25519-AES256GCM", "epk": "…", "ct": "…"}`, encrypted in the client to the gateway's secret-store public key (`GET /v1/secrets/public-key`). The gateway decrypts it only into the secret store. Plans and the audit log hold only `sha256` of each value.

**Times** are RFC 3339 UTC. **Ids** are prefixed ULIDs (`job_`, `snap_`, `run_`, `tgt_`, `alrt_`, `ntf_`, `chn_`, `dev_`, `auto_`, `pol_`, `win_`, `hook_`, `tkt_`, `join_`, `rev_` + number for revisions).

## 12.2 Actions: model additions and the type registry

### Action object additions
```json
{"id": "…", "type": "app.update", "params": {"app_id": "uptime-kuma", "to_version": "2.0.3"},
 "state": "accepted",
 "requested_by": {"id": "automation:auto_01J…", "kind": "automation"},
 "decided_by": {"id": "policy:pol_01J…@3", "kind": "policy"},
 "risk": "medium",
 "target": {"kind": "app", "id": "uptime-kuma", "node_id": "3f9c2a1b7d4e"},
 "plan": {"summary": "…", "objects": […], "images": […], "warnings": […]},
 "plan_sha256": "…",
 "hold": {"window_id": "win_nightly", "until": "2026-11-13T02:00:00Z"},
 "result": {"outcome": "…", "message": "…", "reverted": "code"},
 "assertion": {"credential_id": "…", "sign_count": 12}}
```
- `risk`: `low | medium | high | critical`, fixed per type (table below).
- `plan`/`plan_sha256` (H-13): what will change, rendered at request time. `plan_sha256` is the sha256 of the canonical JSON of `plan.objects` + `params` + `target`.
- `hold`: an accepted action waiting for its window. It stays in state `accepted` (no new state). A gateway restart leaves held actions `accepted`; only accepted actions without a hold, or with a dispatch record, become `outcome_unknown` (amends `reconcile_interrupted`).

### Endpoints added to §3
| Method and path | Who | Returns |
|---|---|---|
| `POST /v1/plans` | owner, agent | body as `POST /v1/actions` without `idempotency_key`/`expires_at` → `{plan, plan_sha256, risk, policy_verdict}`; no side effects |
| `POST /v1/actions` | as §3, plus `automation`; `node` for `node.join` only (via §12.4) | §3, plus optional body fields `plan_sha256` (refuse if the fresh plan differs) and `approve: true` (**owner only**: create and approve in one step; the audit shows `owner_initiated: true`) |
| `POST /v1/actions/{id}/approval-challenge` | owner | `{challenge, plan_sha256, expires_at}` (60 s) |
| `POST /v1/actions/{id}/approve` | owner only (§3) | body optional `{plan_sha256, assertion}`. `assertion` = WebAuthn `{credential_id, client_data_json, authenticator_data, signature}` over the challenge. **Required** when `risk` is `high` or `critical` once SEC-P1 passkeys exist (`403 permission_denied`, `assertion_required`). Plan mismatch → `409 stale_precondition` (`plan_changed`) |
| `GET /v1/action-types` | any principal | the registry below, as JSON, with each type's params schema |

### Type registry
O = owner, A = agent, Au = automation, N = node. **Policy** = may an approval policy approve it ("never" is enforced in code, AUTOMATION.md §3.2). **Runs on:** G = gateway (Kubernetes / DB), J = job to a node (§12.4), G+J = both.

| Type | Params | Risk | May request | Policy | Runs on |
|---|---|---|---|---|---|
| `app.install` | `{app_id, version?, node_id?, bundle_sha256?, acknowledge_unscanned?, sealed?}` | medium (high if unscanned) | O, A | yes for catalog apps with a fresh passing scan; never for bundles | G |
| `app.remove` | `{app_id}` (keeps data) | medium | O, A | yes | G |
| `app.update` | `{app_id, to_version?, bundle_sha256?}` | medium | O, A, Au | yes | G+J (snapshot) |
| `app.rollback` | `{app_id, to_revision}` | medium | O, A, Au | yes | G |
| `app.restart` | `{app_id, component?}` | low | O, A, Au | yes | G |
| `app.configure` | `{app_id, values, sealed?}` | medium | O, A (no `sealed`) | no | G |
| `app.reconcile` | `{app_id}` | low | O, Au | yes | G |
| `app.move` | `{app_id, to_node_id}` | high | O | no | G+J |
| `app.data.delete` | `{app_id}` | critical | O | **never** | G+J |
| `backup.run` | `{units?: [..], target_id?}` | low | O, A, Au | yes | G+J |
| `backup.verify` | `{kind: check|restore, unit?}` | low | O, A, Au | yes | G+J |
| `backup.restore` | `{scope: path|app|box, app_id?, path?, snapshot_id, mode?: portable|exact}` | critical | O | **never** | G+J |
| `backup.target.add` / `.remove` | `{kind, name, location, sealed?}` / `{target_id}` | high | O | **never** | G+J |
| `backup.key.rotate` | `{which: device|owner|escrow}` | critical | O | **never** | G+J |
| `backup.prune` | `{target_id, sealed (owner key)?}` | high | O, Au (non-append-only targets only) | only for non-append-only targets | J |
| `backup.kit.issue` | `{}` → `one_time` kit | high | O | **never** | G |
| `node.join` | `{join_id}` (created by §12.4) | high | N | **never** | G (custodian) |
| `node.drain` / `node.uncordon` | `{node_id}` | medium / low | O, Au | yes / yes | G |
| `node.remove` | `{node_id, wipe: bool}` | critical | O | **never** | G+J |
| `node.set_role` | `{node_id, role: worker|leaf}` | high | O | no | G+J |
| `node.renew` | `{node_id}` | low | O, Au | yes | J |
| `os.update.apply` | `{node_id, version}` | high | O, A, Au | yes, security channel in a window only | J |
| `os.update.postpone` | `{node_id, until}` | low | O | yes | J |
| `os.update.policy` | `{node_id, channel?, policy?, window?}` | medium | O | no | J |
| `automation.create` / `.update` | `{automation}` | medium | O, A (propose) | no | G |
| `automation.enable` / `.disable` / `.delete` | `{automation_id, dry_run_id?}` | medium / low / low | O | no | G |
| `policy.create` / `.update` / `.delete` | `{policy}` / `{policy_id, …}` | critical | O | **never** | G |
| `notify.channel.add` / `.update` / `.remove` | `{kind, name, config, content_level, sealed?}` | high | O | **never** | G |
| `system.check` | `{checks?: [..]}` | low (read-only) | O, A, Au | yes | G+J |
| `system.restart_unit` | `{node_id, unit}` (allowlist: `onemind-nats`, `onemindd`, `k3s`, `k3s-agent`) | medium | O, Au | yes | J |
| `catalog.refresh` | `{}` | low | O, Au | yes | G |
| `exposure.*` (reserved for backlog item 22) | — | critical | O | **never** | G |

`ActionType` in `core/onemind_core/actions.py` becomes this registry. `APP_CLAIMS` is extended per type that claims an app or node, so two conflicting actions cannot both be accepted.

## 12.3 Events and NATS

### Envelope `onemind.event.v1` (from context/02 §8)
```json
{"schema": "onemind.event.v1", "id": "evt_01J…", "type": "node.offline",
 "instance_id": "…", "site_id": null, "source_id": "node:3f9c2a1b7d4e", "actor_id": null,
 "occurred_at": "…", "observed_at": "…",
 "correlation_id": "…", "causation_id": "…",
 "resource": {"kind": "node", "id": "3f9c2a1b7d4e", "version": null},
 "severity": "error", "dedupe_key": "node:3f9c2a1b7d4e:offline",
 "data": {"last_seen": "…", "apps": ["uptime-kuma"]}}
```
`data` carries ids and small facts only, never secrets or file contents (by reference only, context/02 §8). The `type` values are the event catalogue (NOTIFICATIONS.md §3).

### Subjects (the OS owns `onemind.>`; apps may not publish there, brief 30 E7)
| Subject | Publisher | Payload | Stream |
|---|---|---|---|
| `onemind.node.<node_id>.status` | that node | §2 heartbeat + §12.11 | none (core) |
| `onemind.audit` | gateway | §3 audit line | `ONEMIND_AUDIT` (file, 1 year or 2 GiB, `deny_delete`, `deny_purge`) |
| `onemind.event.<type>` (dots of `type` kept, e.g. `onemind.event.node.offline`) | gateway | envelope | `ONEMIND_EVENTS` (file, 7 days or 1 GiB) |
| `onemind.node.<node_id>.event.<type>` | that node | envelope (gateway validates and re-publishes as `onemind.event.<type>`) | `ONEMIND_NODE_OUTBOX` on the node's leaf, sourced by the hub |
| `onemind.node.<node_id>.job.<kind>` | gateway | §12.4 job | `ONEMIND_JOBS` (work queue; consumer `node-<node_id>` filtered to that node) |
| `onemind.node.<node_id>.jobresult.<job_id>` | that node | `{job_id, state: running|succeeded|failed, progress?, summary, finished_at?}` | `ONEMIND_JOBRESULTS` (file, 30 days) |

Node permissions: FABRIC.md §5.2. App streams and app subjects stay in the locked grammar (`evt.`, `cmd.`, `tel.`, `svc.` …) and are out of scope here.

## 12.4 Fabric

| Method and path | Who | Returns |
|---|---|---|
| `POST /v1/fabric/join-tickets` | owner | body `{role: worker|leaf, ttl_s ≤ 3600 (default 900)}` → 201 `{id, role, expires_at, qr_text}` + `one_time: {ticket}`. `qr_text` = `onemind-join:v1?hub=<url>&ca=<sha256>&t=<ticket>&role=<role>` |
| `GET /v1/fabric/join-tickets` | owner | tickets without secrets: `{id, role, created_by, expires_at, used_at}` |
| `DELETE /v1/fabric/join-tickets/{id}` | owner | 204; revokes an unused ticket (audited; not an action, it only removes a right to ask) |
| `POST /v1/fabric/join` | **no session**; the ticket authenticates; `rate_limited` after 10/min per source | body `{ticket, node_id, role, node_pubkey, tls_pubkey, nats_pubkey, facts: <§2 heartbeat>, sig}` (`sig` = Ed25519 by `node_pubkey` over the canonical body without `sig`) → 202 `{join_id, action_id, pairing_code}`. Errors: 409 `conflict` (reason `ticket_used` or `duplicate_node_id`), 409 `expired`, 404 `not_found` (reason `ticket_unknown`) |
| `GET /v1/fabric/join/{join_id}` | the joining node: header `X-OneMind-Node-Sig` over `join_id ‖ timestamp` | `{state: requested|approved|denied|expired}`; when `approved`, once: `{bundle: {node_cert, ca_cert, nats: {url, creds_jwt?, user_pubkey}, job_pubkey, k3s?: {server_url, token}}}`; later calls return `{state: "delivered"}` |
| `POST /v1/fabric/nodes/{id}/renew` | that node, mutual TLS with its current certificate | body `{csr}` → `{node_cert}`; 403 if deny-listed |
| `GET /v1/fabric` | any principal | `{hub_node_id, roles: {hub: 1, worker: n, leaf: n}, nodes: [{node_id, role, state, leaf_link, outbox_pending, cert_expires_at}]}` |
| `GET /v1/nodes`, `/v1/nodes/{id}` | as §3 | §3 plus `role`, `state` (FABRIC.md §6.1: `joining|online|degraded|stale|offline|draining|drained|removed`), `degraded_reasons`, `received_at`, `clock_skew_s`, `apps` (ids placed there). §3's `status` stays `online|stale|offline` |
| `GET /v1/apps/{id}/placement` | any principal | `[{node_id, verdict: fits|fits_with_warning|no, reasons: [..]}]` |

**Job** (published by the gateway):
```json
{"schema": "onemind.job/v1", "job_id": "job_01J…", "action_id": "…", "kind": "backup.run",
 "params": {…}, "params_sha256": "…", "issued_at": "…", "expires_at": "…", "sig": "…"}
```
Job kinds (v1): `backup.run`, `backup.restore`, `backup.verify-restore`, `backup.check`, `backup.prune`, `update.check`, `update.apply`, `update.postpone`, `update.policy`, `node.leave`, `node.renew`, `host.check`, `system.restart_unit`. A node refuses a bad signature, an expired job, a seen `job_id` or an unknown kind. It reports `failed` with `reason` for each.

## 12.5 Backups

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/backups/status` | any principal | `{box: <badge>, system: <badge>, apps: {<id>: <badge>}, targets: [...], last_run, next_run, copies: n, generation}`; badge = `{state: verified|unverified|stale|failing|none, verified_at, last_success_at, reason?}` |
| `GET /v1/backups/targets` | owner | `[{id, kind, name, location (no secrets), primary, state, last_ok_at, free_bytes?, append_only}]` |
| `GET /v1/backups/runs` | owner, agent | list `{id, reason, action_id, target_id, started_at, finished_at, state, units: [{unit, state, snapshot_id?, error?}], bytes_added}` |
| `GET /v1/backups/snapshots?unit=&app_id=&target_id=` | owner | list `{id, unit, app_id?, node_id, taken_at, size_bytes, app_revision?, k3s_version?, reason, tags}` |
| `GET /v1/backups/snapshots/{id}/tree?path=` | owner | `[{name, type: file|dir, size, mtime}]` |
| `GET /v1/backups/snapshots/{id}/file?path=` | owner | the file (streamed); audited |
| `GET /v1/backups/verifications?unit=` | any principal | list `{id, unit, snapshot_id, kind, started_at, finished_at, verdict, details}` |
| `POST /v1/onboarding/restore/candidates` | **setup mode only** (no owner yet), from the LAN | body `{target: {kind, location, sealed creds}, sealed owner key}` → `[{instance_id, box_name, generation, restore_points: [{run_id, taken_at, units, arch, k3s_version}]}]` |

Writes are actions (§12.2): `backup.run`, `backup.verify`, `backup.restore`, `backup.target.*`, `backup.key.rotate`, `backup.prune`, `backup.kit.issue`. During onboarding, `backup.restore {scope: box}` is accepted from the setup session and recorded as the first audit entries of the restored box (`owner_initiated: true`, `phase: onboarding`).

**`onemindd` local API (loopback only, H-24):** `POST :7480/api/v1/backup/run {reason, wait}` → `{run_id, state}` for the updater (BACKUPS.md §6.1).

**restic tags** (normative, so a repository is readable without OneMind): `onemind`, `box=<instance_id>`, `gen=<n>`, `unit=<system|k3s|nats|app|node|fence>`, `node=<id>`, `run=<run_id>`, `reason=<…>`, and when relevant `app=<id>`, `rev=<n>`, `k3s=<version>`, `audit_head=<hash>`.

## 12.6 Deployments

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/apps/{id}` | any principal | catalog entry (§11.4) + `{origin: market|private, current_revision, status, node_id, update_available?, update_policy, drift: {state: in_sync|drifted, fields?, checked_at}, settings: [{name, type, value}], secrets: [{name, key, set: bool}], components: [{name, ready, restarts}], backup: <badge>}` |
| `GET /v1/apps/{id}/revisions` | owner, adult, agent | list `{n, created_at, source, images, plan_sha256, action_id, committed}` |
| `GET /v1/apps/{id}/revisions/{n}` | owner | the rendered objects |
| `GET /v1/apps/{id}/logs?component=&since=&tail=&follow=` | owner, adult; agent with grant `logs:read` | `text/plain` lines, or SSE with `follow=1`; max 2000 lines, 15 min per stream |
| `POST /v1/deploy/bundles` | owner (or a token with `deploy:write`) | `application/x-tar` body ≤ 64 MiB → 201 `{sha256, app_id, manifest, images_lock, findings: [..]}`; refuses unpinned images |
| `GET /v1/secrets/public-key` | any principal | `{alg: "X25519", key, key_id}` for sealed input |
| `GET /v1/os/updates` | any principal | per node: the heartbeat `update` object + `{notes_url, security, history: [..]}` |

App status values (§3 `status`) gain `updating`, `reverting`, `drifted`, `stopped`.

## 12.7 Automation

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/automations`, `GET /v1/automations/{id}` | owner, agent | `{id, name, system: bool, revision, enabled, trigger, action, options, created_by, last_fire_at, last_action_id, breaker: closed|open, stats_30d}` |
| `GET /v1/automations/{id}/fires` | owner | list of fires (AUTOMATION.md §4) |
| `POST /v1/automations/{id}/dry-run` | owner, agent | body `{from?, to?, sample_event?}` → `{id, revision, items: [{at, type, params, target, verdict, policy?}], counts}`; no side effects |
| `POST /v1/automations/{id}/run-now` | owner | creates the action as a fire would (respects concurrency) |
| `GET /v1/policies`, `GET /v1/policies/{id}` | owner | `{id, revision, state, requesters, type, params, plan, window_id, max_per, expires_at, uses_30d, last_uses}` |
| `POST /v1/policies/dry-run` | owner | body `{policy draft}` → past 30 days of actions the draft would have approved |
| `GET /v1/windows`; `PUT /v1/windows/{id}` | any; owner | windows. Editing a window is an audited owner change, **not** an action, unless a policy references it (then it is `policy.update`) |
| `POST /v1/hooks/{hook_id}` | **no session**; HMAC (`X-OneMind-Timestamp`, `X-OneMind-Signature: sha256=<hex>`) | 202 `{event_id}`; 401 bad signature, 409 replay, 413 > 64 KiB, `rate_limited` > 60/min |

Writes are actions: `automation.*`, `policy.*`. A `webhook` trigger's secret is returned as `one_time.hook_secret` in the approve response of `automation.create`.

**Automation object:**
```json
{"name": "Restart Uptime Kuma when unhealthy",
 "trigger": {"event": {"type": "app.unhealthy", "where": {"resource.id": "uptime-kuma"}, "for_s": 180}},
 "action": {"type": "app.restart", "params": {"app_id": "${event.resource.id}"}},
 "options": {"debounce_s": 900, "catch_up": "none", "window_id": null}}
```
Trigger is exactly one of `{"schedule": {"cron": "17 * * * *", "tz": "Europe/Berlin"}}`, `{"event": {...}}`, `{"webhook": {}}`.

**Policy object:**
```json
{"requesters": ["automation:auto_01J…"], "type": "app.restart",
 "params": {"app_id": {"enum": ["uptime-kuma"]}}, "plan": {},
 "window_id": null, "max_per": {"count": 3, "period_s": 86400}, "expires_at": "2027-11-12T00:00:00Z"}
```

## 12.8 Notifications, alerts, activity

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/alerts?state=open` | any principal (filtered by audience) | list `{id, type, severity, title, body, resource, state, opened_at, updated_at, occurrences, flapping, fix: {type, params}?, learn_more_url}` |
| `POST /v1/alerts/{id}/ack`, `/resolve` | owner (resolve only for alerts without an automatic resolve condition) | the alert; audited, not an action |
| `GET /v1/notifications` | the person | own feed, list `{id, type, severity, title, body, link, action_id?, created_at, read_at}` |
| `GET /v1/notifications/{id}` | the person | one notification (the fetch after an iOS ping); 404 for anyone else's |
| `POST /v1/notifications/read` | the person | body `{ids}` or `{before}` |
| `GET /v1/me/notification-preferences`, `PUT …` | the person | NOTIFICATIONS.md §5.1 |
| `GET /v1/me/push-devices`; `POST …`; `DELETE …/{id}` | the person | register `{kind: webpush|unifiedpush|apns, endpoint|token, keys?, label}` |
| `GET /v1/notify/vapid-public-key` | any principal | `{key}` |
| `GET /v1/notify/channels` | owner | `[{id, kind, name, content_level, state, last_error?}]`; never secrets |
| `POST /v1/notify/channels/{id}/test` | owner | 202; sends a test message |
| `GET /v1/activity?node_id=&app_id=&requester_kind=&type=&cursor=` | any principal (filtered) | list of activity items over the audit log, routine runs folded: `{at, kind, summary, action_id?, requester, decider?, outcome?, folded_count?}` |
| `GET /v1/audit/status` | any principal | `{verified_at, head_seq, head_hash, checkpoint: {seq, hash, signed_at}?, ok: bool, broken_at_seq?}` |

Writes that are actions: `notify.channel.*`. Personal state (ack, read, preferences, own devices) is audited but is not an action (NOTIFICATIONS.md §9).

**iOS relay** (separate service, its own contract): `POST /v1/ping {device_token, opaque_id}` → 202. Nothing else is accepted.

## 12.9 Repairs
`GET /v1/repairs` (owner) lists open `repair.*` alerts with their check slug and fix. Fixing is `POST /v1/actions` with the alert's `fix` (or `approve: true` from the owner). There is no separate repair endpoint, so every fix goes through the ledger.

## 12.10 Identity hooks used by this draft (defined by SEC-P1, listed so streams agree)
- People have ids `person:<id>`. Roles stay `owner|adult|guest` (+ `child` later, D-B9.1).
- `GET /v1/me` → `{id, kind, role, passkeys: [{credential_id, label}], sessions_count}`.
- Passkey registration and login endpoints belong to SEC-P1. This draft uses only the assertion check in §12.2.

## 12.11 Heartbeat additions (§2)
Optional fields. Absent means "not supported by this agent", never "false":
```json
"fabric": {"role": "worker", "leaf_link": "up", "outbox_pending": 0, "cert_expires_at": "…"},
"backup": {"running": false, "last_run_at": "…", "last_result": "succeeded"},
"update": { … as defined by feat/onemindd-updater … }
```
The gateway adds `received_at` and `clock_skew_s` when serving nodes; they are not in the published heartbeat.

## 12.12 MCP additions (§11.3)
New tools, all read-only except `propose_automation`. Still `kind: agent` only, and still no approve, deny or policy tool:

| Tool | Equals |
|---|---|
| `get_action` | `GET /v1/actions/{id}` |
| `list_alerts` | `GET /v1/alerts?state=open` (agent audience) |
| `backup_status` | `GET /v1/backups/status` |
| `app_status` | `GET /v1/apps/{id}` without settings values |
| `app_logs` | `GET /v1/apps/{id}/logs?tail=200`; **only with grant `logs:read` for that app** |
| `list_automations` | `GET /v1/automations` |
| `plan_action` | `POST /v1/plans` |
| `propose_automation` | creates an `automation.create` action awaiting the owner |

`request_action` (§11.3) accepts every type the registry (§12.2) lets agents request, with `params` instead of only `app_id`.

## 12.13 Manifest additions (§4, §9.3; schema `sdk/schema/onemind.app.schema.json`)
```yaml
spec:
  health:                       # used by app.update's gate and verified restores
    http: {port: 3001, path: /, expect: 200}
    deadline_s: 600             # ≤ 1800
  migrations: reversible        # reversible (default) | irreversible
  backup:
    mode: hot                   # hot | cold
    pre:  {exec: {container: <name>, command: [..]}}
    post: {exec: {container: <name>, command: [..]}}
    sqlite: [<path inside a volume>]
    exclude: [<glob>]
    restore: {post: {exec: {container: <name>, command: [..]}}}
    verify: {http: {port: 3001, path: /api/status, expect: 200}}
  settings:
    - {name: TZ, type: string, default: UTC, description: Time zone, env: TZ}
  secrets:
    - name: hermes-agent-credentials
      keys: [{key: OPENAI_API_KEY, description: Model provider key, required: true},
             {key: SESSION_SECRET, generate: true}]
  components:
    - {name: web, workload: Deployment/web, health: {http: {port: 8080, path: /healthz}}}
metadata:
  origin: market                # market | private (set by the gateway / CLI, never by hand)
```
`exec.command` is an argv list run in the named container through the Kubernetes API. No host shell is involved. `app-gate` (§9.4) and the box share one validator (H-02, PLG-P2).

## 12.14 CLI verbs (`cmd/onemind/`)
- `onemind node join <qr-text|--hub URL --ticket-file F --ca-sha256 H>` and `onemind node leave`
- `onemind nodes [--watch]`
- `onemind actions list|show|approve|deny <id>`
- `onemind backup status|run|snapshots|restore …`
- `onemind init [--config file] [--restore]` (headless twin of the wizard, ONB-B1)
- `onemind deploy <dir> [--dry-run]`, `onemind deploy history|rollback <app>`
- `onemind app import <compose.yaml>`
- `onemind migrate check|import|copy-data|cutover`
- `onemind automations list|dry-run|run-now`
- `onemind alerts`
- `onemind activity`
- `onemind audit verify`

Every write verb creates the same action as the dashboard, and `--json` prints the API response (UX-B2).

## 12.15 Adoption order (each a separate contract PR)

| PR | Sub-sections | Needed by build steps |
|---|---|---|
| 12-a | §12.1 conventions, §12.2 action additions + registry (types added as their features land), §12.3 envelope and subjects | everything |
| 12-b | §12.4 fabric, §12.11 heartbeat `fabric` | FABRIC F1–F5 |
| 12-c | §12.6 deployments, §12.13 `health`, `settings`, `secrets`, `migrations`, `components` | DEPLOYMENTS D1–D5 |
| 12-d | §12.5 backups, §12.13 `backup:`, §12.11 heartbeat `backup` | BACKUPS K2–K7 |
| 12-e | §12.8 notifications and activity, §12.9 repairs | NOTIFICATIONS N1–N5 |
| 12-f | §12.7 automation | AUTOMATION A1–A4 |
| 12-g | §12.2 approval challenge and assertion, iOS relay contract | NOTIFICATIONS N6–N7, after SEC-P1 |
| 12-h | §12.12 MCP additions, §12.14 CLI | as tools land |

**Open for the contract owner:**
1. Whether `node` belongs in the principal kinds, or join requests should be a separate ledger. The draft chooses the ledger, so join approvals appear in Approvals like everything else.
2. Whether `rate_limited` and `unavailable` are added, or mapped onto `conflict` as §3 does today for validation errors.
3. The `plan_sha256` requirement moving from optional (v0, H-13 logs `plan_unchecked`) to required.
4. `acknowledge_unscanned` on `app.install` for owner-uploaded private bundles relaxes contract §10.3 ("nothing unscanned runs"). It is **not** purely additive and needs an explicit decision (DEPLOYMENTS.md §6, FOUNDER CALL). Until then, private bundles stay blocked unless the on-box scan (DEPLOYMENTS D6) passes.
