<!-- SPDX-License-Identifier: Apache-2.0 -->
# Slop audit, pass 2: contract drift

**Date:** 2026-11-12 · **Audited:** `origin/main` at `ad81f84` · **Item:** Wave G #4 (`QUALITY-SLOP-2`) · **Pass 1:** [slop-audit-drift.md](slop-audit-drift.md)
**Lens:** the same thing said four ways. [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) (the contract) against the routes the gateway serves (`sdk/openapi/onemind-v1.json`), the SDKs (`sdk/ts`, `sdk/python`, `sdk/go`) and the clients (dashboard, `ui/`, mobile, desktop). Code and docs: [code](slop-audit-2-code.md), [docs](slop-audit-2-docs.md).

> **Explain it like I am the founder**
> The contract is the promise, the OpenAPI file is what the gateway really does, and the SDKs are generated from that file, so those two always agree (a CI check regenerates them and fails on a difference). The gaps are therefore between the **contract and the gateway** and between the **gateway and the screens**. Good news: pass 1's biggest items held (event envelope, heartbeat fields, scan record). What is left: (1) the gateway has seven sign-in routes the contract never names; (2) the gateway still calls the approver `decided_by` where the contract says `approved_by`; (3) the shared settings screens in `ui/` call about thirty routes under names that exist nowhere; (4) the events stream does not send the alert and notification events the contract lists, but the phone listens for them.

## How this was checked

| Method | Result |
|---|---|
| All `METHOD /path` strings in the contract (99 distinct paths after treating `{id}` and `{node_id}` alike) against `paths` in `sdk/openapi/onemind-v1.json` (61 paths) | 52 in both; 7 paths only in OpenAPI (DR2-01; two more, `…/channels/{id}` and `…/registrations/{id}`, are written as `PATCH …/{id}` shorthand in the contract, so they match); the rest of the contract's paths are §12 routes that "exist only once their module ships" (§12 intro, `poc-v0.md:225`), so absence is not drift |
| `sdk/ts/src/gen/schema.ts` paths against OpenAPI | identical (61 = 61, no difference); `sdk/Makefile:43` regenerates all three SDKs and fails on `git diff` |
| Script over `dashboard/src mobile/src mobile/app desktop ui/src site/src tests/e2e sdk cmd internal deploy scripts`: every `/v1/…` literal tested against the OpenAPI paths (path parameters as wildcards) | 98 literals match nothing (counting repeats; `scripts/` excluded); grouped in DR2-03, DR2-05, DR2-06 and the planned-route placeholders already labelled as such |
| §2 heartbeat fields against `internal/heartbeat/heartbeat.go` JSON tags | all 22 §2 field names present |
| §12.8 event types against `core/onemind_core/eventstream.py` | `action.*`, `node.status`, `audit.appended`, `stream.reset` only (DR2-04) |
| §3 / §12.4 Action object against the OpenAPI `Action` schema | DR2-02 |

Owner rule: `orchestrator` = `dashboard/ ui/ docs/ apps/ site/`; `Hermes` = `core/ cmd/ internal/ deploy/ os/ sdk/ mobile/ desktop/` or an open PR. Nothing here is fixed in this PR: every finding is Hermes-owned or in `dashboard/` / `ui/`.

## Findings

| Id | Sev | Owner | Contract says | Gateway / clients do | Fix |
|---|---|---|---|---|---|
| [DR2-01](#dr2-01) | medium | Hermes | §12.6 names the sign-in routes | 7 operations in OpenAPI are in no section of the contract | amend §12.6 (additive) |
| [DR2-02](#dr2-02) | medium | Hermes (+ orchestrator for `dashboard/`) | §12.4: `approved_by`, `approved_via`, `approval`, `risk`, `plan`, `plan_sha256` | OpenAPI `Action` has `decided_by`/`decided_at` and none of the new fields | additive `approved_by`; fill the rest |
| [DR2-03](#dr2-03) | medium | orchestrator (`ui/`) | §12.21: draft names `/v1/notify/*`, `/v1/people` are not used | `ui/src/settings` and `shell` call 30+ paths under the draft names | rename to §12 names |
| [DR2-04](#dr2-04) | medium | Hermes | §12.8 lists `alert.*`, `notification.created`, `app.*` events | the stream sends `action.*`, `node.status`, `audit.appended` only | emit them, or amend the list |
| [DR2-05](#dr2-05) | low | Hermes (`mobile/`) | no `/v1/devices/*`, no `/v1/photos/*` | mobile calls both | add to the contract when the server side lands |
| [DR2-06](#dr2-06) | low | Hermes | `GET /v1/actions/{id}/preview`, `POST …/cancel` (§12.4) | not served; `mobile` and `ui` call `preview` | serve, or keep gating on OpenAPI (mobile does) |
| [DR2-07](#dr2-07) | low | Hermes (`sdk/`) | SDKs wrap the contract | wrappers cover 6 route groups, not `me`, `alerts`, `notifications`, `tokens`, `users`, `auth`, `mcp`; the typed `Node` lacks the hardware fields | extend the wrappers |
| [DR2-08](#dr2-08) | low | orchestrator | `dashboard/` `COMING` lists the contract's paths | four of its "coming" sections already have routes | see code audit CS2-11 |

### DR2-01
**Seven gateway operations the contract never mentions.** · medium
- **Where (OpenAPI):** `POST /v1/auth/setup`, `/v1/auth/enrol`, `/v1/auth/password`, `/v1/auth/refresh`, `/v1/auth/totp/setup`, `/v1/auth/totp/confirm`, `/v1/auth/totp/disable`.
- **Evidence:** `grep -n "auth/setup\|auth/enrol\|totp" sdk/contracts/poc-v0.md` finds nothing. §12.6 (`poc-v0.md:360-380`) lists passkey login and registration, sessions, tokens and users, and mentions a `refresh_token` in the login response (`:369`) without a route. The mobile client says so itself: `mobile/src/api/client.ts:46` "Not in §12.6 (it returns a refresh_token but names no route)".
- **Why it matters:** the contract says it owns "names, paths, bodies, errors" (`:225`). A client written only from the contract cannot do first-owner setup, enrolment from an invitation, a password sign-in, or TOTP, though the gateway and the dashboard offer them.
- **Fix:** one additive PR to §12.6 naming the seven routes, their bodies and errors; regenerate nothing (OpenAPI already has them).

### DR2-02
**`decided_by` against `approved_by`, and the §12.4 Action fields.** · medium · pass 1 CS-12 / D3, still open
- **Where:** contract `poc-v0.md:239, 295, 303` (`approved_by`, `approved_via`, `approval`, `risk`, `reason`, `target`, `plan`, `plan_sha256`, `hold`); OpenAPI `Action` properties are `created_at, decided_at, decided_by, expires_at, id, idempotency_key, params, requested_by, result, state, type, updated_at, version` (`additionalProperties: true`); gateway `core/onemind_core/ledger.py:65, 81`.
- **Evidence in the clients:** `dashboard/src/api/types.ts:155` and `dashboard/src/data/adapters.ts:171, 293` read `decided_by`; `mobile/src/api/types.ts:185` has `decided_by` and `:196` also an `approved_by` string; the SDK `Action` types follow OpenAPI (`sdk/ts/src/gen/schema.ts:1086`). The audit already writes `approved_by` (contract `:303`).
- **Why it matters:** the same fact has two names depending on which API you ask (audit vs actions). A client that follows the contract reads `approved_by` and gets nothing from the gateway; `risk`, `plan` and `plan_sha256` (the preview a person approves) are not in any response, so "approve what you were shown" (H-13) cannot be checked by a client.
- **Fix:** add `approved_by` and `approved_via` next to `decided_by` (additive), then fill `risk`, `plan`, `plan_sha256`; regenerate OpenAPI and the three SDKs; dashboard and mobile adopt. The dashboard part waits for its owner.

### DR2-03
**Shared Settings screens call routes named after a draft the contract rejected.** · medium
- **Where (`ui/src`):** `settings/SectionsCare.tsx:95` `/v1/backups/schedule`, `:236, 246, 300` `/v1/os/settings`, `:325, 349, 376, 382, 390` `/v1/notify/routes`, `/v1/notify/quiet`, `:433, 440` `/v1/automations`; `settings/SectionsAccess.tsx:72` `/v1/auth/policy`, `:223, 262` `/v1/people`, `:328, 332, 391, 409` `/v1/agents/{id}/resume`, `/v1/agents/suspend-all`; `settings/SectionsSystem.tsx:71` `/v1/fabric/join-codes`, `:135, 179` `/v1/remote`, `/v1/network`; `shell/palette.ts:206-211` `/v1/auth/principals`, `/v1/auth/tokens`, `/v1/notify/routes`, `/v1/backups`; `home/widgets.tsx:344` `/v1/updates`; `shell/notifications.ts:106` `/v1/notifications/{id}/unread`.
- **Evidence:** contract §12.21 (`poc-v0.md:647`): "the draft's `/v1/notify/*` and `/v1/me/…` paths are not used". The contract's names are `/v1/notifications/*`, `/v1/users`, `/v1/automation/rules`, `/v1/fabric/join-tickets`, `/v1/os/*`, `/v1/tokens`, `/v1/agents/{id}/suspend`. `dashboard/src/pages/Settings.tsx:12-21` (`COMING`) already uses the contract names, so `ui/` and `dashboard/` disagree with each other.
- **Why it matters:** `ui/` is the shared design system for the dashboard, mobile and the website. Each of these strings is an "intent" a person triggers; when a real route lands, the call will 404 (or worse, hit a different meaning).
- **Fix:** rename in one pass using the §12.21 table; add a test that every `call:` string in `ui/src/settings` is either an OpenAPI path or in an explicit `PLANNED_ROUTES` list taken from the contract. `ui/` is being edited by another worker, so not changed here.

### DR2-04
**The events stream is missing the alert and notification events the contract lists.** · medium
- **Where:** contract §12.8 v1 types (`poc-v0.md:453`): `alert.opened`, `alert.updated`, `alert.resolved`, `notification.created`, `app.status`, `app.health`, `app.restarted`, …; emitted by `core/onemind_core/eventstream.py:38-68`: `action.*`, `node.status`, `audit.appended`, `stream.reset`.
- **Evidence:** `grep -rn "alert.opened\|app.health\|notification.created" core/onemind_core` finds nothing. The phone listens for them: `mobile/src/lib/events.ts:281` (`t.startsWith('alert.')` refreshes the alerts list).
- **Why it matters:** alerts and notifications merged (#44) and the contract says the stream carries them, so a client that relies on events (not polling) never refreshes its alerts. Mobile's polling fallback hides this.
- **Fix:** publish the alert and notification events from the notify service onto the event stream, with the §12.8 envelope; or remove them from the "v1 types" list until they exist (then mobile must poll).

### DR2-05
**Phone routes that are not in the contract.** · low
- **Where:** `mobile/src/api/client.ts:47-48, 437-445` (`/v1/devices/requests`, `/v1/devices/token`), `mobile/src/photos/protocol.ts:176-232` and `discovery.ts:4` (`/v1/photos/sources`, `/v1/photos/uploads`).
- **Evidence:** the files say so ("not yet in the contract", "interim, §12-p pending"); the gateway serves none of them; the app gates on the OpenAPI feature list (`mobile/src/api/client.ts:53-75`), so it does not call them against today's gateway.
- **Fix:** a contract section when the Photos server and device pairing are built (`feat/photos-server`).

### DR2-06
**`/v1/actions/{id}/preview` and `/cancel` are promised and called, not served.** · low
- **Where:** contract §12.4 table; `mobile/src/api/client.ts:38, 379-380`; `ui/src/settings/ApprovalsBoard.tsx:106`.
- **Evidence:** absent from OpenAPI. Allowed by §12's intro ("exists only once its module ships"), so this is a tracking item, not a contract break. Mobile checks `Features` first; `ui` does not (DR2-03).
- **Fix:** with DR2-02 (the preview is where `plan` and `plan_sha256` come from).

### DR2-07
**The SDK wrappers cover part of the API.** · low
- **Where:** `sdk/ts/src/client.ts:129-191` and the Python and Go clients wrap `instance`, `nodes`, `apps`, `actions`, `audit`, `events`. Not wrapped: `me`, `alerts`, `notifications`, `push`, `monitoring`, `tokens`, `users`, `auth`, `/mcp`. The generated types do include them, and the Go `Do` and Python `request` methods let callers reach any route.
- **Evidence:** `sdk/ts/src/gen/schema.ts` has all 61 paths; typed `Node` has no `cpu_model`, `mem_total_mb` etc. (the dashboard and mobile declare their own: `dashboard/src/api/types.ts:27-29`, `mobile/src/api/types.ts:29-31`), though §2 and the gateway send them (`additionalProperties: true`).
- **Fix:** wrappers per DEV-SDK-3/5/6 follow-ups; add the §2 fields to the OpenAPI `Node` schema so all three SDKs and both clients share one type.

### DR2-08
Same item as code audit CS2-11 (dashboard "coming" placeholders for sections whose routes now exist). Owner: orchestrator (`dashboard/`).

## Checked and clean

- **Heartbeat (§2)** matches `internal/heartbeat/heartbeat.go` and the OpenAPI `Node` required fields (`node_id`, `status`, `last_seen`).
- **Error codes (§3, §12.2)** and the **event envelope (§12.8)** match the gateway (pass 1 DS-10 fix held).
- **Scan record and catalog fields (§11.1, §11.4)**: `CatalogApp` has `links`, `tier`, `scan`.
- **Generated SDKs** equal the OpenAPI file; the repo has a staleness check (`sdk/Makefile:43`).
- **Desktop** (`desktop/`) calls no `/v1/…` path outside OpenAPI.
- **Founder decisions D-001 to D-007**: no file contradicts them. Several apps being `tier: blocked` does not touch them.
