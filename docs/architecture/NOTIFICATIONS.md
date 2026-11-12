<!-- SPDX-License-Identifier: Apache-2.0 -->
# Notifications, alerts and repairs

**Status:** design for build agents (2026-11-12). API in [CONTRACT-12-DRAFT.md](CONTRACT-12-DRAFT.md) §12.8.
**Backlog:** core-alignment items 8 (NOT-P1, NOT-P2, NOT-P3), 18 (MOB-P2, NOT-B2), 19 (MOB-B1, SEC-B2, NOT-B3), 20 (NOT-B1); also UX-B1 (activity) and H-28 (alert on update freeze, scan expiry, audit break).
**Builds on:** D-005 (iOS push carries an opaque signal only); research 12 §6 (alert record, delivery per platform, payload budget); context/02 §8 (event envelope); the audit log published on `onemind.audit` (`core/onemind_core/audit.py`); ntfy packaged as an app (`apps/ntfy/`).

> **In plain words.** Everything that happens on the box becomes an **event**. Some events are worth telling someone about. Those become **notifications** on the channels each person chose: the dashboard, a phone push, ntfy, email, a chat app. Problems that last, like "node offline" or "backup failing", become **alerts** that stay open until fixed, and many come with a **Fix** button. The fix is a normal request that you approve. Your phone gets only a meaningless "something new" ping from Apple or Google, then fetches the real message from your own box. When an approval is waiting, the notification opens it directly, and you approve with Face ID.

## 1. Requirements

| ID | Requirement | Source |
|---|---|---|
| N-R1 | One event catalogue with stable types, severities and default audiences | NOT-P1 |
| N-R2 | Alerts are stateful (open, acknowledged, resolved), deduplicated, and resolved automatically when the condition clears | NOT-P1, research 12 §6.1 |
| N-R3 | Channels: in-app, Web Push, ntfy / UnifiedPush, iOS APNs relay (opaque ping, then fetch), email, webhook, Telegram, Matrix | NOT-P2, D-005 |
| N-R4 | Per-person routing by severity, domain and channel; quiet hours; digest | NOT-P3 |
| N-R5 | Approval notifications deep-link to the action and allow approve or deny with strong auth | NOT-B3, MOB-B1, SEC-B2 |
| N-R6 | Repairs: system checks raise alerts with fix actions that go through approval | NOT-B1 |
| N-R7 | Privacy: third-party carriers see as little as possible; content level is set per channel | D-005, M-2 |
| N-R8 | Delivery is recorded, retried with backoff, and failures are visible | — |
| N-R9 | Children and guests receive only what concerns them | research 12 §6.1 |

## 2. Event, notification, alert

| Word | Meaning | Lives in |
|---|---|---|
| **event** | a fact that happened, in the `onemind.event.v1` envelope | `ONEMIND_EVENTS` stream (7 days) |
| **alert** | a condition that is true now (node offline, backup failing). Opened, updated and resolved by events with the same `dedupe_key` | gateway `alerts` table |
| **notification** | one message to one person on one channel, about an event or an alert | gateway `deliveries` table |

**Sources of events:**
1. **The audit log.** Every audit line is already published on `onemind.audit`. The notifier maps audit events to catalogue types (`action.awaiting_approval` → `approval.requested`, `action.failed` → `action.failed`, …). Nothing new is needed in the producers for those.
2. **Node events** re-published by the gateway from `onemind.node.<id>.event.>` (FABRIC.md §5.2).
3. **Gateway watchers:** heartbeat ages (node offline), backup runs and verifications, drift, update states, scan expiry, the audit-chain check.
4. **System checks** (repairs, §4).
5. **Later:** Prometheus Alertmanager rules publishing on the same bus (research 12 §6.1), when monitoring lands.

## 3. Event catalogue (v1)

| Type | Severity | Alert? (dedupe key) | Default audience | Fix action | Deep link |
|---|---|---|---|---|---|
| `approval.requested` | info (warning when expiring < 1 h) | no | owners | — (approve/deny) | `/approvals/<action_id>` |
| `approval.expiring` | warning | no | owners | — | same |
| `action.succeeded` | info | no | requester (person), owners for owner-initiated | — | `/activity/<action_id>` |
| `action.failed` | error | no | owners + requester | retry where idempotent | `/activity/<action_id>` |
| `action.outcome_unknown` | critical | yes (`action:<id>`) | owners | repair (`system.check`) | `/activity/<action_id>` |
| `action.auto_approved` | info, **off by default** | no | owners | — | `/activity/<action_id>` |
| `node.joined` | info | no | owners | — | `/nodes/<id>` |
| `node.offline` | error | yes (`node:<id>:offline`) | owners | — | `/nodes/<id>` |
| `node.degraded` | warning | yes (`node:<id>:<reason>`) | owners | per reason | `/nodes/<id>` |
| `node.cert_expiring` | warning | yes | owners | `node.renew` | `/nodes/<id>` |
| `app.unhealthy` | error | yes (`app:<id>:health`) | owners + users of the app | `app.restart` | `/apps/<id>` |
| `app.update_available` | info | no (digest daily) | owners | `app.update` | `/apps/<id>` |
| `app.updated` / `app.update_reverted` | info / error | no / yes (`app:<id>:revert`) | owners | `app.rollback` | `/apps/<id>` |
| `app.drifted` | warning | yes (`app:<id>:drift`) | owners | `app.reconcile` | `/apps/<id>` |
| `app.scan_blocked` | critical | yes (`app:<id>:scan`) | owners of boxes with it installed | `app.remove` | `/apps/<id>` |
| `backup.failed` | error | yes (`backup:<target>`) | owners | `backup.run` | `/backups` |
| `backup.stale` | warning | yes (`backup:stale`) | owners | `backup.run` | `/backups` |
| `backup.verify_failed` | error | yes (`verify:<unit>`) | owners | per app (e.g. set `mode: cold`) | `/backups/<unit>` |
| `backup.repo_damaged` | critical | yes (`repo:<target>`) | owners | — (guide link) | `/backups` |
| `backup.replaced` | critical | yes (`fence`) | owners | — | `/backups` |
| `update.available` | info | no | owners | `os.update.apply` | `/updates` |
| `update.committed` | info | no | owners | — | `/updates` |
| `update.rolled_back` | error | yes (`os:<node>:rollback`) | owners | retry once for `environment-bad` (OSU-B3) | `/updates` |
| `update.frozen` | warning | yes (`os:<node>:freeze`) | owners | — | `/updates` (H-28) |
| `security.audit_chain_broken` | critical | yes (`audit`) | owners | — | `/security` (H-28) |
| `security.login_new_device` | warning | no | that person | revoke session | `/me/sessions` |
| `automation.paused` | warning | yes (`auto:<id>`) | owners | `automation.enable` | `/automations/<id>` |
| `notify.channel_failing` | warning, **in-app only** | yes (`channel:<id>`) | owners | `notify.channel.update` | `/settings/notifications` |
| `repair.*` | per check | yes (`repair:<check>:<context>`) | per check | per check | `/repairs/<id>` |
| `hook.received` | debug, never notified | no | — | — | — |

Adding a type is an amendment to this table and to CONTRACT-12-DRAFT §12.3.

**Severity:** `critical | error | warning | info | debug`. The values follow research 12 §6.1, plus `debug` for events that are never notified.

## 4. Repairs (NOT-B1)

The pattern comes from Home Assistant's Supervisor resolution centre: **checks** find issues, **suggestions** propose fixups (`supervisor/resolution/checks/`, `fixups/`, `home-assistant/supervisor` `040f14c`, Apache-2.0; pattern only, no code copied). In HA some fixups run by themselves. In OneMind **every fix is a requested action**: shown with its plan, approved by a person, or by a policy only where the type allows it (AUTOMATION.md §3.2).

**Check interface** (gateway, Python): `slug`, `interval`, `run() -> list[Issue]`. Each issue has `{context (e.g. node id), severity, title, body, learn_more_url, fix: {type, params} | null}`. The system automation `system.check` runs checks every 15 minutes. An issue opens or updates alert `repair:<slug>:<context>`. An issue no longer reported resolves it.

| Check (v1) | Finds | Fix action |
|---|---|---|
| `disk_space` | data partition < 10 % free on any node | `backup.prune` (owner) or guide |
| `failed_units` | failed systemd units in the core set | `system.restart_unit` (allowlisted units) |
| `cert_expiring` | box CA, hub or node certificate < 14 days | `node.renew` |
| `backup_stale` | no successful run in 2× the schedule | `backup.run` |
| `scan_stale` | installed app with a scan > 7 days old | `catalog.refresh` |
| `clock_skew` | node skew > 60 s | guide (enable NTP) |
| `port_conflict` | two apps request the same host port or subdomain | guide |
| `duplicate_machine_id` | FABRIC.md §3 | guide |
| `kine_compaction_lag` | REC-DEC-49 | guide |
| `crash_consistent_backup_failed` | BACKUPS.md §2.3 | `app.configure` (`backup.mode: cold`) |

## 5. Routing

### 5.1 Per-person preferences
```json
{"channels": {"inapp": true, "push": ["dev_01J…"], "ntfy": "chn_01J…", "email": "chn_02J…"},
 "rules": [
   {"match": {"severity_at_least": "error"}, "send_to": ["push", "inapp"]},
   {"match": {"type": "approval.*"}, "send_to": ["push", "inapp"]},
   {"match": {"type": "app.update_available"}, "send_to": ["email"], "digest": "daily"}],
 "quiet_hours": {"tz": "Europe/Berlin", "from": "22:30", "to": "07:00", "allow": ["critical", "approval.expiring"]},
 "language": "en"}
```
- The first matching rule wins. With no match, the notification goes to `inapp` only.
- **Quiet hours:** notifications held during quiet hours are delivered as one summary when they end. Types in `allow` go through anyway. Critical bypass is **on** by default and can be turned off.
- **Digest:** `hourly|daily` batches matching notifications into one message.

### 5.2 Audience
Each event has a default audience (§3). Audience resolves to **people by role**: owners; adults for apps they use; children and guests only for their own sessions and apps shared with them (N-R9). An owner can widen it per type ("also send `app.unhealthy` for Home Assistant to all adults").

### 5.3 Noise control
- **Dedupe:** an alert re-notifies at most once per 30 minutes for the same `dedupe_key` and severity. Escalation to a higher severity notifies at once.
- **Flap damping:** `node.offline` fires only after 120 s offline (stale never alerts). An alert that resolves and re-opens within 10 minutes counts as one, with a "flapping" label.
- **Approval reminders:** `approval.expiring` once, 1 hour before `expires_at`.
- **Rate cap** per channel and person: 30 per hour, beyond that one summary.

## 6. Channels (NOT-P2)

| Channel | How | Content sent to the carrier | Self-hosted? | Pattern source |
|---|---|---|---|---|
| `inapp` | SSE stream `GET /v1/stream` to open dashboards and the phone app when in foreground | full | yes | — |
| `webpush` | RFC 8291-encrypted Web Push with VAPID keys generated on the box (RFC 8292) | encrypted; the browser vendor sees size and timing only | vendor-carried | StartOS self-hosted Web Push with VAPID ES256 (`shared-libs/crates/start-core/src/notifications/push.rs`, MIT, `Start9Labs/start-os` `246876d`; pattern only) |
| `unifiedpush` (Android) | Web Push encryption to the endpoint from the phone's distributor, by default the box's own ntfy | encrypted | **yes** | research 12 §6.2 [C-W11-030] |
| `ntfy` | publish to a topic on the box's ntfy app or any ntfy server, with an access token | level set per channel (default `title`) | yes | ntfy docs |
| `apns_relay` (iOS) | `POST <relay>/v1/ping {device_token, opaque_id}`; the relay sends an APNs push with `mutable-content: 1` and only the opaque id; the app's notification service extension fetches `GET /v1/notifications/{id}` from the box and shows it | **opaque only** (D-005) | relay needed | research 12 §6.2 [C-W11-024…027] |
| `email` | SMTP with STARTTLS or implicit TLS | level per channel (default `title`) | via owner's SMTP | Coolify `EmailChannel` (Apache-2.0; pattern only) |
| `webhook` | `POST` JSON envelope, HMAC-SHA256 signature header as in AUTOMATION.md §3.6 | full by default | yes | Coolify `WebhookChannel` |
| `telegram` | Bot API `sendMessage` to a chat id | default `title`, never params | no (Telegram sees content) | Coolify `TelegramChannel` |
| `matrix` | client-server API `m.room.message` to a room | default `title`; full only if the owner marks the room E2EE (UNVERIFIED that a bot can confirm encryption by itself; the owner asserts it) | yes, with own homeserver | research 12 §6.2 |

**Content levels:** `opaque` (only "OneMind: new alert"), `title` (title + severity, no params, no names of people), `full` (title, body, deep link). The level is enforced in the channel worker, so a misconfigured rule cannot leak the body.

**The iOS relay** is a separate small Apache-2.0 service, stateless: it accepts `{device_token, opaque_id}`, rate-limits per token and keeps no logs beyond counters (research 12 §6.2). OneMind runs a public instance; anyone can run their own with their own Apple developer account. Apple's 4 KB payload limit is never near, because the ping carries ~40 bytes. **FOUNDER CALL (F-2 in research 12):** who operates the public relay, and on what domain.

**Delivery:** each channel worker reads from an in-process queue fed by the router. Each send writes a `deliveries` row: `queued → sent | failed`, retries with backoff 30 s, 2 min, 10 min, 1 h, 6 h, then `dead`. Failures over 1 hour raise `notify.channel_failing` for that channel, shown in-app only, so a dead email server cannot hide behind itself.

**Secrets** of channels (SMTP password, bot tokens, ntfy token, webhook secret) live in the gateway secret store and are never returned by the API. Adding or changing a channel is an owner action (`notify.channel.add/update/remove`), because a channel is a way out for data.

## 7. Approvals from a notification (NOT-B3, MOB-B1, SEC-B2)

1. `approval.requested` goes to owners on their push channels. The deep link is `https://<box>/approvals/<action_id>` and, for the phone app, `onemind://box/<box_id>/approvals/<action_id>`.
2. On iOS the ping arrives, the extension fetches the notification, and shows "Hermes asks to install ntfy" with **Review** as the action. Approve and Deny buttons inside the notification would bypass the plan screen, so the button opens the app.
3. The app shows the approval card: exact params and plan (H-13), requester kind and id, the "written by an agent" mark on agent-supplied text, and the expiry.
4. **Approve:** the app gets a challenge, `POST /v1/actions/{id}/approval-challenge` → `{challenge, plan_sha256, expires_at}`. The challenge is `sha256(action_id ‖ plan_sha256 ‖ nonce)`. The app runs a WebAuthn assertion with the owner's passkey (Face ID / fingerprint) over that challenge, then sends `POST /v1/actions/{id}/approve {plan_sha256, assertion}`.
5. The gateway verifies the assertion against the owner's registered passkey, the challenge and the plan hash. The audit line records `assertion: {credential_id, sign_count}`. A stolen session cookie cannot approve, because it has no passkey (SEC-B2). For `risk: high|critical` actions the assertion is **required** (CONTRACT-12-DRAFT §12.2).
6. Android: the same flow, with push via UnifiedPush (full content allowed, since the carrier is the box's own ntfy).

## 8. Activity feed (UX-B1)

`GET /v1/activity` is a read model over the audit log: requests, approvals (by whom or which policy), runs, failures and alerts. Routine auto-approved actions are folded (AUTOMATION.md §3.4). Filters: node, app, requester (person/agent/automation), type, time. The header shows **"chain verified at <time>, head <hash prefix>"** from the latest `onemind audit verify` run (hourly) and the latest signed checkpoint (H-10). The phone app keeps the last checkpoint it saw, so a rewritten log is detectable from the phone too (H-10).

## 9. Data model (gateway database)

```
alerts(id, dedupe_key UNIQUE (when open), type, severity, source_id, resource_json, title, body,
       audience_json, fix_json, learn_more_url, state[open|acked|resolved], opened_at, updated_at,
       acked_by, acked_at, resolved_at, occurrences, flapping bool)
notifications(id, event_id, alert_id, person_id, type, severity, title, body, link,
              action_id, created_at, read_at)
deliveries(id, notification_id, channel_id, state[queued|sent|failed|dead], attempts,
           next_attempt_at, last_error, sent_at)
channels(id, kind, name, owner_scope[box|person], person_id, config_json, secret_ref,
         content_level[opaque|title|full], state, created_at)
push_devices(id, person_id, kind[webpush|unifiedpush|apns], endpoint_or_token_enc, keys_enc,
             label, created_at, last_seen_at)
preferences(person_id PK, json, updated_at)
```

Retention: notifications 90 days, deliveries 30 days, resolved alerts 180 days. Every acknowledge and resolve is also in the audit log.

**Not actions:** acknowledging an alert, marking a notification read, and editing one's own preferences and push devices are **personal state**, not changes to the system. They do not go through the action ledger, but they are audited. Adding box-wide channels is an action.

## 10. Security

- Third-party carriers get opaque or title-only content by default. iOS content never leaves the box (D-005).
- Push device tokens and endpoints are encrypted at rest. A person can see and revoke their devices.
- Approvals from notifications always pass through the plan screen and a passkey assertion. A notification alone can never approve.
- Webhook and chat channels are owner-added actions, because each one is an egress path.
- The notifier reads the audit stream and never writes to it, except its own acknowledge, resolve and channel events.

## 11. Test plan and acceptance criteria

| # | Test | Pass when |
|---|---|---|
| NT-1 | Audit → event mapping | An agent request produces `approval.requested` for each owner and none for guests |
| NT-2 | Alert life cycle (fake clock) | Node silent 121 s → `node.offline` opens once; another 30 min → one re-notify; heartbeat → resolved and a "back online" message |
| NT-3 | Flap | Offline/online 4 times in 10 min → one alert marked flapping |
| NT-4 | Quiet hours | A warning at 23:00 is held and summarised at 07:00; a critical goes through at once; with the bypass off, it is held too |
| NT-5 | Content levels | With `title` on Telegram, the sent text contains no params or body (asserted on the HTTP request to a fake Bot API) |
| NT-6 | Web Push | A real browser (Playwright, Chromium) receives an encrypted push from the box's VAPID key |
| NT-7 | iOS relay contract | The relay receives only `{device_token, opaque_id}`; the fetch by id requires the person's session and returns 404 for another person's notification |
| NT-8 | Passkey approval | Approve with a valid assertion → `succeeded`; same request without assertion on a `high` risk action → 403 (`assertion_required`); assertion over an old `plan_sha256` → 409 |
| NT-9 | Retry and dead | A failing SMTP fake → attempts at the backoff times, then `dead` and `notify.channel_failing` in-app |
| NT-10 | Repairs | Fill a test disk to 95 % → `repair:disk_space:<node>` with a fix; free it → resolved |
| NT-11 | Activity "chain verified" | Editing an audit line flips the header to "chain broken at seq N" and raises `security.audit_chain_broken` |

## 12. Build steps

| Step | What | Size | Depends on |
|---|---|---|---|
| N1 | `onemind.event.v1` envelope; `ONEMIND_EVENTS` stream; audit → event mapper; gateway watchers (node, backup, update, scan) | M | JetStream on the hub NATS |
| N2 | Alerts (dedupe, flap, resolve), notifications, in-app inbox + SSE stream; Activity feed with "chain verified" | M | N1, design system |
| N3 | Routing: preferences, quiet hours, digest, rate caps | S | N2, SEC-P1 (people) |
| N4 | Channels: Web Push (VAPID), ntfy, email, webhook, Telegram, Matrix; deliveries with retry | M | N3 |
| N5 | Repairs framework + v1 checks | M | N2, AUTOMATION A2 |
| N6 | Mobile push: UnifiedPush on Android; iOS relay service + notification service extension | M | N4, mobile shell (MOB-P1) |
| N7 | Approval challenge + passkey-signed approval; deep links | M | SEC-P1 (passkeys), N6 |
