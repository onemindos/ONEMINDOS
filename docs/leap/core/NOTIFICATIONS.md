<!-- SPDX-License-Identifier: Apache-2.0 -->
# Notifications, alert centre and repairs (CORE-NOTIFY)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** E3 (push part) · **Deeper docs:** `docs/architecture/NOTIFICATIONS.md` (architecture stream, branch `docs/core-architecture`, in progress); research 12 §6 (REC-W11-07, -08); [D-005](../../DECISIONS.md) · **Serves:** UX-4; core-alignment NOT-P1…P3, NOT-B1…B3; hardening H-28.

> **Explain it like I am the founder**
> Everything that needs your attention becomes one alert in one inbox: an approval waiting, a node offline, a backup not verified, an update rolled back, a failed scan.
> Your phone is pinged with **no content**, only "something new"; it then fetches the alert from your own box. Apple and Google never see what it was (D-005).
> Some alerts are "repairs" with a fix button, and the fix is a normal request you approve.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| One alert record and inbox (ack, resolve) | Full Alertmanager rule packs for every app (apps bring their own later) |
| Delivery: in-app, Web Push, ntfy/UnifiedPush (Android), APNs ping-then-fetch (iOS), email, webhook, Matrix, Telegram | SMS; satellite channels |
| Per-user routing: severity, channel, quiet hours | Child-account routing (after identity, E8) |
| Repairs: system checks with a fix action through approval | "AI investigate" with write rights (read-only only) |
| Protection-stopped alerts (H-28): update check failing, scan stale, audit broken, new token/node | |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| ntfy as a seed app | `apps/ntfy/` | `main` |
| Audit events on NATS `onemind.audit` | `core/onemind_core/bus.py` | `main` |
| Phone shell polls every 10 s and raises **local** notifications for approvals, finished actions, node offline/online | `mobile/src/lib/alerts.ts`, `src/notify.ts` | `feat/mobile-shell` |
| Push design (UnifiedPush; APNs relay + service extension) | `mobile/README.md` "Notifications" | `feat/mobile-shell` (design only) |
| Alert record, inbox, delivery | – | not built |

## 3. Design

### 3.1 Alert record (research 12 §6.1)
```json
{"id": "al_3b9e", "severity": "warning", "source": "backup",
 "audience": {"roles": ["owner"]}, "title": "Backups not verified for 7 days",
 "body": "The weekly test restore of ntfy failed: probe /v1/health timed out.",
 "fixable": true, "fix_action": {"type": "backup.verify", "params": {"app_id": "ntfy"}},
 "learn_more": "https://docs.onemind.example/errors/backup-unverified",
 "action_id": null, "created_at": "2026-11-16T03:12:00Z",
 "acked_by": null, "resolved_at": null, "dedupe_key": "backup.unverified:ntfy"}
```
- Sources publish on NATS `onemind.alert.<source>.<kind>` (core subjects stay under `onemind.` as in contract §1; app events use the `evt.*` grammar through E7 grants). The alerts module stores, dedupes by `dedupe_key`, and fans out.
- An alert tied to a pending approval carries `action_id`.

### 3.2 Delivery

| Channel | Payload | Vendor sees content? | Epic |
|---|---|---|---|
| In-app (dashboard, phone open) | full alert over HTTPS | – | NOTIFY-1 |
| Web Push (PWA) | `{alert_id, box_id}` RFC 8291-encrypted; fetch on click | No | NOTIFY-3 |
| Android: UnifiedPush via the box's own ntfy | `{alert_id, box_id}` to the app's endpoint | No (self-hosted) | NOTIFY-3 |
| iOS: APNs via a stateless OneMind relay | `{alert_id, box_id}`, `mutable-content: 1`; Notification Service Extension fetches text from the box | Apple sees only that a push arrived | NOTIFY-4 |
| Email, webhook, Matrix, Telegram | owner chooses: title only, or full text (warning shown for Telegram, which is not end-to-end encrypted) | per channel | NOTIFY-6 |

**The relay** (founder decision F-4) accepts only `{device_token, opaque_id}`, logs nothing beyond rate-limit counters, is Apache-2.0 and self-hostable with your own Apple developer account (REC-W11-08).

### 3.3 Commands and API
```console
$ onemind alerts
SEV      WHEN    SOURCE   TITLE                                   STATE
warning  09:12   backup   Backups not verified for 7 days         open  [fix: backup.verify]
info     08:03   update   OS 0.1.2026111604 committed on slot B   resolved
$ onemind alerts fix al_3b9e
action a_95  backup.verify  accepted (policy:pol_verify)  → running
$ onemind notify test --channel ntfy
sent ping to 2 devices (content-free)
```

| Method and path | Who | Does |
|---|---|---|
| `GET /v1/alerts?state=open` | principal in the audience | list |
| `GET /v1/alerts/{id}` | same | fetch (what a push wakes the phone to call) |
| `POST /v1/alerts/{id}/ack`, `/resolve` | owner, adult | state change of the alert only (no system change) |
| `POST /v1/alerts/{id}/fix` | owner, agent | creates `fix_action` as a normal request |
| `POST /v1/push/registrations` | signed-in device | `{kind: webpush\|unifiedpush\|apns, endpoint\|token}` |
| `GET/PUT /v1/notify/routes` | owner | per-user routing (severity, channels, quiet hours) |

```python
for a in client.alerts.list(state="open"): print(a.severity, a.title)            # Python
```
```ts
await om.push.register({ kind: "unifiedpush", endpoint });                         // TypeScript
```
```go
alerts, _ := om.Alerts.List(ctx, onemind.AlertFilter{State: "open"})             // Go
```
**MCP:** a read tool `list_alerts` (later); `request_action` can request a `fix_action`; agents cannot ack or silence alerts addressed to people.

### 3.4 Repairs (CORE-NOTIFY-5, NOT-B1)
Built-in checks every 5 minutes: disk > 85 %, failed systemd unit, certificate expiring < 14 days, backup unverified > 7 days, app scan stale or failing, update check failing > 48 h, audit verify failure at start, clock skew. Each check has an id, a doc page and an optional fix action (pattern from Home Assistant's resolution centre, Apache-2.0; studied, attributed if any code is reused).

### 3.5 Actionable notifications (CORE-NOTIFY-7)
A notification for a pending approval opens the approval card in the app; **the notification itself never approves**. Approval needs the passkey step (SECURITY CORE-SEC-2).

## 4. Security model
- Push payloads carry only a random 128-bit alert id and a box id (well under the 4 KB APNs limit); content is fetched over HTTPS with the device's session.
- Push registrations are per device and revoked with the device's session.
- Alerts are authorization-filtered at fetch time: a guest's device cannot fetch an owner alert even with its id.
- Outbound channels (email, webhook) store their credentials as write-only secrets; webhook bodies are signed (HMAC) so receivers can verify.
- Flood control: dedupe, per-source rate limit, and a digest after 20 alerts in 10 minutes.

## 5. Versioning and compatibility
- Alert record schema `onemind.alert/v1`; additive fields only within v1.
- The mobile shell keeps local polling as a fallback when no push channel is registered.
- Contract §3 gains `/v1/alerts`, `/v1/push`, `/v1/notify`; the NATS subject family `onemind.alert.>` is added to §1.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Inbox | A pending approval, a node offline and a stale backup each create exactly one alert; dedupe holds on repeats |
| Content-free push | Captured UnifiedPush and APNs payloads contain only `alert_id` and `box_id` |
| Fetch auth | A guest device fetching an owner alert id → 403 |
| Android end to end | Approval alert arrives on a real Android phone with the app closed in < 5 s on LAN; approve in < 10 s total (plan E3) |
| Protection stopped (H-28) | Expired TUF timestamp + clock +48 h → one alert; broken audit line + restart → one alert |
| Repairs | Each check's fix creates a request; nothing changes without approval unless a standing approval covers it |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-NOTIFY-1 | Alert record, store, `/v1/alerts`, NATS subjects, in-app inbox | M | – |
| CORE-NOTIFY-2 | Sources: approvals, nodes, updates, backups, scans, audit (H-28) | S | 1 |
| CORE-NOTIFY-3 | Web Push + Android UnifiedPush (box ntfy), push registrations | M | 1, SEC-1 |
| CORE-NOTIFY-4 | iOS relay + Notification Service Extension | M | 3, F-4; built together with MOBILE-5 (relay here, app extension there) |
| CORE-NOTIFY-5 | Repairs with fix actions | M | 1 |
| CORE-NOTIFY-6 | Email, webhook, Matrix, Telegram channels; routing and quiet hours | S | 1 |
| CORE-NOTIFY-7 | Actionable notifications → approval card | S | 3, MOBILE-3 |

## 8. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/notifications` | new `core/onemind_core/alerts.py`, new `core/onemind_core/notify/` (one file per channel), `cmd/onemind/cli/alerts.go`, `dashboard/src/pages/Alerts.tsx` |
| `feat/repairs` | new `core/onemind_core/repairs.py` |
| `feat/push-relay` | new top-level `relay/` (stateless APNs relay, its own README and licence header) |
| `feat/mobile-shell` | `mobile/src/notify.ts`, native module for UnifiedPush, iOS service extension |
| `feat/onemindd-updater` follow-up | emit `onemind.alert.update.*` from `internal/update/engine.go` |
| Hotspots (serialized) | `core/onemind_core/app.py`, contract §1/§3 |
