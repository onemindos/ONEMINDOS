<!-- SPDX-License-Identifier: Apache-2.0 -->
# Automation: schedules, event rules and approval policies

**Status:** design for build agents (2026-11-12). API in [CONTRACT-12-DRAFT.md](CONTRACT-12-DRAFT.md) §12.7.
**Backlog:** core-alignment item 21 (AUT-P1, AUT-P2, AUT-B1, AUT-B2); it also carries backup schedules (item 3), repairs (item 20) and update windows (item 10).
**Builds on:** the action ledger with idempotency keys and expiry (`core/onemind_core/actions.py`, `ledger.py`); context/02 §7 (delegated grants: subject, action, resources, expiry, maximum uses, approval reference); brief 30 D-B9.6 (approvals bound to exact parameters and grant revision); research 12 §6.1 ("any fix needs human approval"); hardening backlog H-14 (cap pending actions).

> **In plain words.** An automation never acts by itself. It only **asks**, exactly like an AI agent would: "restart this app", "back up now". What it asks for still needs your approval, unless you wrote a **policy** in advance that says "yes to this kind of request, within these limits". For example: "restart Uptime Kuma at most 3 times a day", or "install security updates between 2 and 5 am". Every automatic yes is written in the audit log with the policy that gave it. Before you switch an automation on, a dry run shows what it would have asked for over the last week, and which of those your policies would have approved.

## 1. Requirements

| ID | Requirement | Source |
|---|---|---|
| A-R1 | Scheduled jobs (cron) per app or per box create actions | AUT-P1 |
| A-R2 | Event triggers on OS events and inbound webhooks create actions | AUT-P2 |
| A-R3 | Owner-defined approval policies auto-approve matching low-risk actions within limits; everything else goes to the approval queue | AUT-B1, SEC-B1 |
| A-R4 | Some action types can never be auto-approved | W5-R13, contract rule |
| A-R5 | Maintenance windows hold approved actions until the window opens | BD-09, OSU-P1 |
| A-R6 | Dry run before enabling: what would be requested, against which resource, with which verdict | AUT-B2 |
| A-R7 | Every automated request and every automatic approval is audited with the automation and policy revisions | contract §3 Audit |
| A-R8 | Agents may propose automations; they never create or change policies | contract rule, D-B9.3 |
| A-R9 | Runaway protection: rate limits, concurrency 1, and a breaker that disables a failing automation | — |

## 2. Concepts

| Thing | What it is | Principal it acts as |
|---|---|---|
| **Automation** | trigger + action template + options | `automation:<id>` (kind `automation`); it can only **request** |
| **Trigger** | `schedule` (cron + time zone), `event` (an `onemind.event.*` type + filter) or `webhook` (inbound, HMAC-signed) | — |
| **Action template** | an action type and its params, with substitutions from the trigger (§4.2) | — |
| **Policy** | rules under which a matching request is approved without a person | decides as `policy:<id>@<rev>` |
| **Window** | named recurring time ranges (e.g. `nightly` 02:00–05:00 local) | — |

**Why the automation is its own principal:** the audit log must show *what* asked, not the person who once set it up (context/02 §7: "an agent acting for Zeus is not Zeus"). The automation's record names its owner (`created_by`), so responsibility is still traceable.

## 3. Design

### 3.1 Flow

```
trigger fires ──► render template (typed substitution) ──► POST action internally
                                                           requested_by automation:<id>
                                                           idempotency_key = <auto id>:<fire id>
                                                                │
                                         policy engine ◄────────┘
                    ┌────────────────────┼─────────────────────────────┐
              hard-deny list       matching policy within limits     no match / over limit
                    │                    │                              │
            action.rejected        accepted (decided_by policy)   awaiting_approval → notify
            (403, audited)         → held until window? → dispatched
```

The policy engine sits in the **approval step** of the existing action service, so it also applies to requests from agents and people, not only automations. An agent's `backup.run` can be auto-approved by the same policy.

### 3.2 Policy evaluation (deterministic order)

1. **Hard deny:** if the type is in the never-automatable list (CONTRACT-12-DRAFT §12.2, column "policy"), stop. The request stays `awaiting_approval` for a person, or is refused when the requester may not request that type at all.
2. **Requester match:** the policy lists who it covers (`requesters: [automation:*, agent:hermes-agent, person:*]`). Agents are covered only when listed by id. A wildcard never matches agents.
3. **Type and parameters:** the policy names one action type and constraints on its params: `const`, `enum`, `pattern`, `max`, `min` (a small JSON-Schema subset, validated at policy creation). Example: `{type: app.restart, params: {app_id: {enum: [uptime-kuma, ntfy]}}}`.
4. **Plan constraints** (for types with plans, DEPLOYMENTS.md §3): e.g. `app.update` only when `update.kind == patch`, the scan passed, and a pre-update snapshot will be taken.
5. **Window:** if the policy names a window, the approval is given but dispatch is **held** until the window opens (§3.5).
6. **Limits:** `max_per: {count: 3, period_s: 86400}` counted atomically per policy in the database. Over the limit, the request goes to a person with the reason "policy limit reached (3/24h)".
7. **Expiry and revision:** a policy has `expires_at` (≤ 1 year) and a revision number. Any edit makes a new revision that needs approval again. Approvals record `policy:<id>@<rev>` and the counter value.

If several policies match, the **most specific** wins (fewest params left unconstrained). On a tie, the oldest wins, so behaviour does not change when a newer, broader policy is added.

### 3.3 Policy life cycle

- **Created only by an owner**, as an action (`policy.create`), approved with a passkey assertion when SEC-B2 is built. A policy is a standing approval, so it gets the strongest approval there is.
- Agents get `403 permission_denied` on any `policy.*` request (A-R8).
- The Policies screen lists each policy with its last 30 days of use: how many requests it approved, how many it pushed to a person because of its limits, and the last 5 approvals with links.
- **Suggested policies:** after the owner approves the same type and params 3 times in 14 days, the approval card offers "Always allow this, up to N per day?" That pre-fills `policy.create`, which still needs its own approval. This turns approval fatigue (H-14) into a safe policy.

### 3.4 System automations and the default policy

The OS ships **system automations** (read-only, can be paused only with an owner action, visible like any other):

| System automation | Trigger | Action |
|---|---|---|
| backup hourly | schedule `@hourly` (fixed random minute) | `backup.run` |
| backup off-site | daily, window `nightly` | `backup.run {target: offsite}` |
| backup check | daily, window | `backup.verify {kind: check}` |
| verified restore | weekly, window | `backup.verify {kind: restore}` |
| repairs scan | every 15 min | `system.check` (read-only; produces alerts, NOTIFICATIONS.md §4) |
| catalog refresh | every 6 h | `catalog.refresh` |

The **system policy** `pol_system` approves exactly these types with these params, nothing else. It is shown, can be tightened by the owner, and cannot be widened. Routine auto-approved actions are folded in the Activity feed ("24 hourly backups today, all succeeded"), so the feed stays readable. They are still each in the ledger and the audit log.

### 3.5 Maintenance windows and held actions

- **Windows** are `{id, name, tz, ranges: [{days: [mon…sun], start: "02:00", end: "05:00"}]}`. `nightly` (daily 02:00–05:00, the updater's default) exists at install.
- An action may carry `not_before` or `window_id`. After approval it stays `accepted` with `hold: {window_id, until}` and is dispatched when the window opens. If `expires_at` passes first, it becomes `expired`.
- **Change needed in `reconcile_interrupted`:** today, a gateway restart turns every `accepted` action into `outcome_unknown`. A held action with no dispatch record never reached the executor, so it is safe and must stay `accepted`. Only actions that have a `dispatched_at`, or that are `accepted` without a hold, are marked unknown.

### 3.6 Event and webhook triggers

- **Event triggers** subscribe through a durable JetStream consumer on `ONEMIND_EVENTS` (one consumer for the automation engine, not one per rule; context/02 §8 warns against consumer sprawl). Filter: event `type` (exact, or a prefix ending in `.*`) and field conditions on the envelope (`data.app_id == "x"`, `severity >= warning`).
  - **Debounce** per rule (default 5 min per `resource.id`), so a flapping app does not request 50 restarts. The limit in the policy is the second guard.
  - **Loop guard:** an event caused by an action that this automation requested (`causation_id` chain) does not trigger it again.
- **Webhooks:** `POST /v1/hooks/{hook_id}` with `X-OneMind-Timestamp` and `X-OneMind-Signature: sha256=<HMAC of timestamp + "." + body>` using the hook's secret (one-time output at creation). Requests older than 5 minutes or replayed (same signature seen in the last 10 min) are refused. Body ≤ 64 KiB. A valid call becomes the event `hook.received` (`data` = the JSON body, kept for 7 days), which rules then match. The webhook itself has no other power.

### 3.7 Missed fires and failures

- If the gateway was down when a schedule was due: `catch_up: none` (default) skips it; `catch_up: last` fires once on start. Never all missed fires.
- **Concurrency 1** per automation: a fire while its previous action is not final is skipped and counted.
- **Breaker:** after 3 consecutive `failed`/`outcome_unknown` outcomes, the automation is paused and an alert is raised ("paused after 3 failures"). Resuming is an owner action.
- H-14's cap applies: an automation has at most 5 actions awaiting approval at once.

## 4. Data model

```
automations(id, name, created_by, revision, enabled, trigger_json, template_json,
            options_json{catch_up, debounce, window_id}, breaker_state, last_fire_at,
            last_action_id, dry_run_id_for_revision, created_at, updated_at)
automation_fires(id, automation_id, revision, fired_at, cause{schedule|event_id|hook_call_id},
                 outcome[requested|skipped_concurrency|skipped_debounce|template_error|denied],
                 action_id)
policies(id, revision, created_by, approved_by_action, requesters_json, type, params_json,
         plan_json, window_id, max_count, max_period_s, expires_at, state[active|paused|expired])
policy_uses(policy_id, revision, action_id, decided_at)          -- also the limit counter
windows(id, name, tz, ranges_json)
hooks(id, automation_id, secret_sha256, created_at, last_call_at)
dry_runs(id, automation_id, revision, created_at, window_from, window_to, result_json)
```

### 4.1 Template substitution (typed, not string-building)

Templates use `${trigger.time}`, `${event.resource.id}`, `${event.data.<field>}` **only in parameter positions whose schema is an id or enum**. Each substitution is validated against the action type's param schema after rendering. No substitution into free text that is later run, and no shell anywhere. A template that renders invalid params produces a `template_error` fire record and an alert. It never produces a best-effort action.

### 4.2 Example

```yaml
name: Restart Uptime Kuma when unhealthy
trigger: {event: {type: app.unhealthy, where: {"resource.id": uptime-kuma}, for_s: 180}}
action:  {type: app.restart, params: {app_id: "${event.resource.id}"}}
options: {debounce_s: 900}
# matching policy, created separately by the owner:
policy:  {type: app.restart, requesters: ["automation:auto_01J…"],
          params: {app_id: {enum: [uptime-kuma]}}, max_per: {count: 3, period_s: 86400}}
```

## 5. Dry run (AUT-B2)

`POST /v1/automations/{id}/dry-run {from?, to?, sample_event?}`:
- **Schedule:** list the fire times in the range (default the next 7 days).
- **Event:** replay matching events from `ONEMIND_EVENTS` over the last 7 days (the stream's retention), applying debounce, concurrency and loop guard.
- For each would-be action: rendered type and params, target resource, and the **verdict**: `auto_approved_by policy:<id>@<rev>`, `needs_approval`, `over_limit (n/limit)`, `denied: <reason>`, `template_error`.
- No side effects. No action rows, and nothing published except one audit line `automation.dry_run`.
- **Enabling requires a dry run** of the current revision that is less than 24 hours old (`automation.enable` refuses otherwise with `409 stale_precondition`, reason `dry_run_required`). The enable approval card shows the dry-run summary.

Policies get the same: `POST /v1/policies/dry-run {policy draft}` replays the last 30 days of the action ledger and shows which past requests the draft would have approved.

## 6. Agent tools beyond list and request

Read tools added to `POST /mcp` (CONTRACT-12-DRAFT §12.12): `get_action`, `list_alerts`, `backup_status`, `app_status`, `list_automations`. Plus `propose_automation`, which creates an `automation.create` action awaiting the owner. There are still no approve, deny or policy tools. Logs are a tool only with the `logs:read` grant (DEPLOYMENTS.md §8).

## 7. Competitor patterns

| Who | Has | Licence (as read) | Our difference |
|---|---|---|---|
| Home Assistant | automations, scripts, blueprints; Supervisor "auto" fixups (`supervisor/resolution/fixups/base.py`, property `auto`) | Apache-2.0 (`home-assistant/supervisor` `040f14c`) | HA marks some fixups as automatic in code. OneMind makes "automatic" an owner-written, limited, audited policy |
| Coolify | scheduled tasks per app, notifications on failure and recovery (`app/Notifications/ScheduledTask/`) | Apache-2.0 (`37aaf60`) | Same scheduling; ours requests actions under approval |
| Cosmos | built-in cron (`src/CRON.go`) | Apache-2.0 + Commons Clause | Pattern only |
| umbrelOS, StartOS, CasaOS | none in the core; n8n or Node-RED as apps | — | Those apps stay possible; core automation covers OS operations |

None of them offers dry run against real history, or auto-approval with counted limits that shows up in an audit chain.

## 8. Security

- An automation has no more power than an agent: it requests. Approval comes from a person or a policy a person signed.
- The never-automatable list is code, not configuration: restores, backup targets and keys, node join and remove, identity, policies themselves, exposure changes, app data deletion, and unscanned installs.
- Webhook calls are authenticated, time-boxed and replay-checked, and they only produce events.
- Template substitution is typed, and every rendered action is validated.
- Every fire, every verdict and every automatic approval is audited with revisions.

## 9. Test plan and acceptance criteria

| # | Test | Pass when |
|---|---|---|
| AT-1 | Schedule with fake clock | Fires at the right local times across a DST change (Europe/London, America/New_York fixtures); `catch_up: none` skips missed fires, `last` fires once |
| AT-2 | Policy within limit | 3 `app.restart` requests approved by the policy with `decided_by policy:<id>@<rev>`; the 4th awaits a person with "limit reached" |
| AT-3 | Hard deny | `policy.create` for `backup.restore` is refused; an automation requesting `node.remove` lands in `awaiting_approval`, never auto-approved |
| AT-4 | Agent and policies | Agent `policy.create` → 403; an agent's `backup.run` matching a policy that lists that agent → auto-approved; with a wildcard requester → needs a person |
| AT-5 | Window hold | Approved at 14:00 with window `nightly` → stays `accepted` with hold; a gateway restart keeps it `accepted`; dispatched at 02:00; past `expires_at` → `expired` |
| AT-6 | Event rule debounce and loop guard | 20 `app.unhealthy` events in 5 min → 1 request; an event caused by the rule's own restart does not fire it again |
| AT-7 | Webhook | Valid signature → event and action; wrong signature, old timestamp, replay, or body > 64 KiB → refused and audited |
| AT-8 | Breaker | 3 failing outcomes → automation paused and alert raised; no 4th fire |
| AT-9 | Dry run | Against a fixture event history, the verdict list matches the expected one; `enable` without a fresh dry run → `409 dry_run_required` |
| AT-10 | Template safety | A substituted value that fails the id pattern (e.g. contains `/` or spaces) → `template_error`, no action |
| AT-11 | Audit | Every fire, auto-approval and dry run is in the chain; `onemind audit verify` passes |

## 10. Build steps

| Step | What | Size | Depends on |
|---|---|---|---|
| A1 | Policy engine in the approval path (hard deny, requester, params, limits, revisions); `decided_by` policy; held actions + windows; the `reconcile_interrupted` change | M | action-type registry (CONTRACT §12.2) |
| A2 | Scheduler (cron + tz, catch-up, concurrency, breaker) and system automations + `pol_system` | M | A1 |
| A3 | Event rules over `ONEMIND_EVENTS` (debounce, loop guard) and webhooks | M | A2, NOTIFICATIONS N1 (events) |
| A4 | Dry run for automations and policies; enable requires a fresh dry run | S | A2 |
| A5 | Automations and Policies screens, suggested policies on the approval card, folded routine activity | M | A1–A4, design system |
| A6 | MCP read tools + `propose_automation` | S | A2, gwmcp merged |
