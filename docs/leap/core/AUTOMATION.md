<!-- SPDX-License-Identifier: Apache-2.0 -->
# Automation: schedules, triggers and standing approvals (CORE-AUTO)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** E7 (risk policy part) · **Deeper docs:** `docs/architecture/AUTOMATION.md` (architecture stream, branch `docs/core-architecture`, in progress); core-alignment §4.10 (AUT-P1, AUT-P2, AUT-B1, AUT-B2) · **Serves:** plan §5 decision 6 (risk policy); research 29 §8.3; contract §3 action ledger.

> **Explain it like I am the founder**
> An automation is "when X happens, ask for Y": every night, when a disk fills, or when a webhook arrives.
> It never acts by itself. It creates a normal request. If you set a **standing approval** ("restart uptime-kuma at most 3 times a day"), requests inside those limits go ahead and are logged as approved by your policy; anything outside waits for you.
> Before you turn one on, it shows a dry run of exactly what it would ask for.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| Triggers: schedule (cron), bus event, signed inbound webhook | A visual flow editor (n8n or Node-RED are Market apps) |
| Every firing creates an action in the ledger | Device automations (Home Assistant stays the engine for those) |
| Standing approvals with bounds: types, params, count per window, time window, expiry | Standing approvals for `destructive`, `actuate` or grant-widening types |
| Dry run before enable | Agents enabling automations themselves |
| Failure and recovery notifications | |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| Action ledger with idempotency and expiry | `core/onemind_core/actions.py`, `ledger.py` | `main` |
| NATS bus, audit published on `onemind.audit` | `core/onemind_core/bus.py` | `main` |
| MCP `request_action` | `core/onemind_core/mcp.py` | `feat/gateway-agent-mcp` |
| Scheduler, triggers, policies | – | not built |

## 3. Design

### 3.1 Objects
```yaml
# automation (stored in the gateway DB; YAML is the CLI/API form)
id: au_nightly_backup
trigger: {schedule: "0 3 * * *", tz: "box"}       # or {event: "onemind.alert.disk.low"} or {webhook: true}
request: {type: backup.run, params: {}}
enabled: true
---
# standing approval (owner-created; covers matching requests)
id: pol_kuma_restart
covers: {type: app.restart, params: {app_id: uptime-kuma}}
limits: {max: 3, per: 24h, window: "any", expires_at: "2027-05-16T00:00:00Z"}
```

### 3.2 Risk classes (plan decision 6)

| Class | Examples | Standing approval allowed? |
|---|---|---|
| read | status, list | not needed (reads are not actions) |
| write (routine) | `backup.run`, `app.restart`, `app.update` (patch, verified, scan pass; F-6) | **yes**, within limits |
| sensitive (grant-widening) | `app.install`, `deploy.apply` of a new rev, `node.join`, token create | **no** |
| destructive | `backup.restore`, `backup.forget`, `app.remove` with data, `node.remove` | **no** |
| actuate | anything that moves or switches a device | **no**; lab-only until LT-VM-18 passes |

These are the five risk classes of [API.md](../dev/API.md) §5.11 (`read`, `write`, `sensitive`, `destructive`, `actuate`). The class is a property of the action type in the contract, not of the automation, so an automation cannot relabel it.

### 3.3 Flow
```
trigger fires ─► action created (requested_by: automation:au_x, on_behalf_of: person:owner)
   ├─ a standing approval matches and limits allow ─► accepted (approved_by: policy:pol_y) ─► executor
   └─ otherwise ─► awaiting_approval ─► alert to owner ─► passkey approve/deny
```
Every step goes to the audit log; the policy's creator and creation time are part of the audit line.

### 3.4 Commands and API
```console
$ onemind auto create --name nightly-backup --schedule "0 3 * * *" --request backup.run --dry-run
Would request   backup.run  {}   at 03:00 daily (next: 2026-11-17 03:00)
Covered by      pol_backup_daily (max 2/24h) → runs without asking
$ onemind auto create … (same, without --dry-run)
automation au_7  enabled
$ onemind policy create --covers app.restart --app uptime-kuma --max 3 --per 24h --expires 180d
action a_90  policy.create  awaiting_approval   ← creating a standing approval is itself approved with a passkey
```

| Method and path | Who | Does |
|---|---|---|
| `GET/POST /v1/automations`, `POST /v1/automations/{id}/dry-run` | owner (agents: GET only) | manage and test |
| `POST /v1/automations/{id}/disable` | owner | instant (reduces power) |
| `POST /v1/actions {"type": "policy.create", …}` | owner or agent request | owner approval with passkey |
| `POST /v1/policies/{id}/revoke` | owner | instant |
| `POST /v1/hooks/{hook_id}` | anyone with the hook secret | HMAC-SHA256 over body + timestamp; creates the automation's request; 5-minute replay window |

```python
client.automations.dry_run("au_7")                                               # Python
```
```ts
await om.automations.create({ name: "nightly-backup", trigger: { schedule: "0 3 * * *" },
  request: { type: "backup.run", params: {} }, dryRun: true });                   // TypeScript
```
```go
res, _ := om.Automations.DryRun(ctx, "au_7")                                       // Go
```
**MCP:** an agent may **propose** an automation (`request_action` with `automation.create`), which the owner approves; it cannot enable, edit or create policies directly.

## 4. Security model
- No automation and no policy can approve a grant-widening, destructive or actuate type: enforced in the gateway's action path, tested with fixtures.
- Limits are counted in the ledger, not in memory, so a gateway restart cannot reset them.
- Webhooks: per-hook secret shown once, HMAC + timestamp, rate limit, body ≤ 64 KiB; a webhook can only fire its one automation.
- Expired policies stop covering at once; every policy has an expiry (max 1 year).
- A paused gateway (kill switch or maintenance) fires no automations.

## 5. Versioning and compatibility
- Contract §3 gains `risk_class` per action type, the `automation:` principal kind, `approved_by: policy:<id>`, and routes `/v1/automations`, `/v1/policies`, `/v1/hooks`.
- Cron syntax: 5-field standard; time zone of the box unless set.
- An automation stores the action type and params schema version; if the type's schema changes, the automation is disabled with an alert rather than run with old params.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Limits | 4th `app.restart` in 24 h under a `max 3` policy → `awaiting_approval` |
| Forbidden cover | Creating a policy covering `app.install`, `backup.restore` or any actuate type → 422 |
| Dry run | Output equals the action that the first real firing creates (params and match) |
| Webhook | Bad HMAC → 401; replay older than 5 minutes → 401; valid → one action |
| Restart safety | Gateway restart mid-window keeps the count |
| Actuate | Release build refuses the lab flag; an actuate type never auto-approves (plan E7) |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-AUTO-1 | Risk classes on action types (contract) + enforcement in the approve path | S | contract PR |
| CORE-AUTO-2 | Scheduler and event/webhook triggers creating actions | M | 1, NOTIFY-1 |
| CORE-AUTO-3 | Standing approvals with ledger-counted limits | M | 1, SEC-2 |
| CORE-AUTO-4 | Dry run + CLI + dashboard page | S | 2, 3 |
| CORE-AUTO-5 | Failure/recovery notifications and repairs hook-up | S | 2, NOTIFY-5 |

## 8. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/automation` | new `core/onemind_core/automation.py`, new `core/onemind_core/policies.py`, `cmd/onemind/cli/auto.go`, `cmd/onemind/cli/policy.go`, `dashboard/src/pages/Automations.tsx` |
| Hotspots (serialized) | contract §3 (risk classes, routes), `core/onemind_core/app.py`, `core/onemind_core/actions.py` (one hook in the approve path; coordinate with SANDBOX and SECURITY branches) |
