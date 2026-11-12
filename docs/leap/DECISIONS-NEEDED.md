<!-- SPDX-License-Identifier: Apache-2.0 -->
# Decisions needed

**Date:** 2026-11-12 · Part of [the leap](README.md). Settled decisions live in [`docs/DECISIONS.md`](../DECISIONS.md); this page lists only open ones.

> **Explain it like I am the founder**
> §1 is the list only you can decide. Each row has a proposed default, so builders can start with the default and change course cheaply if you pick otherwise. The "Needed by" column says when waiting starts to block work.
> §2 is not for you: it lists naming differences between the leap specs and the architecture stream's contract §12 draft, for whoever writes the contract PRs.
> §3 records the contradictions between specs that were fixed on 2026-11-12, and §4 the loose ends that were found but not fixed.

## 1. Founder decisions

F-1 to F-7 keep the numbers used in [core/README.md](core/README.md). The rest gather the open questions from each spec and from the 90-day plan.

| # | Question | Proposed default | Blocks | Needed by | Source |
|---|---|---|---|---|---|
| F-1 | Phone HTTPS: per-box CA or Tailscale certificate first? | Per-box CA by default; Tailscale certificate when remote access is on | CORE-SEC-1, CORE-MOBILE-2 | S1 week 1 | SECURITY, MOBILE, plan §5.2 |
| F-2 | Passkey step-up on every approval, or only on risky types? | Every owner approval once passkeys exist; `destructive` and `actuate` always | CORE-SEC-2, DEV-API-5 | S1 | SECURITY, API §8.4, plan §5.5 |
| F-3 | Mobile shell: Expo/React Native (built) or Capacitor (research 12)? | Keep Expo; share code through `sdk/ts` | CORE-MOBILE-7, DEV-PLG-15 | S2 | MOBILE, PLUGIN-SDK §20.5 |
| F-4 | When to build the iOS APNs relay (needs an Apple developer account)? | After Android push works (week 8+) | CORE-NOTIFY-4, CORE-MOBILE-5 | S2 | NOTIFICATIONS, MOBILE, plan §5.5 |
| F-5 | Website domain and host | GitHub Pages now; self-host on a OneMind box later | CORE-WEB-1, CORE-WEB-4 | S1 | WEBSITE |
| F-6 | May standing approvals cover app patch updates? | Yes, for `verified` apps with a passing scan, inside the maintenance window | CORE-AUTO-3, CORE-UPDATE-5 | S3 | AUTOMATION, UPDATES |
| F-7 | Private deployments: may the owner install an image that failed a scan, with typed confirmation? | No in v0; later yes, with a red "owner override" mark in the audit | CORE-DEPLOY-2 | S3 | DEPLOYMENTS |
| F-8 | Accept `cobra` (Apache-2.0) as a new CLI dependency? | Yes (fallback: stdlib `flag`, bash and zsh completion only, about +1 S of effort) | DEV-CLI-1, DEV-CLI-13 | S1 | CLI §14.1 |
| F-9 | May root on the box approve gateway actions in rescue mode? | Never | DEV-CLI-14, CORE-UPDATE-8 | S1 | CLI §14.2 |
| F-10 | Hermes licence: confirm from the pinned release's LICENSE file | Ship `apps/hermes-agent` only after it is confirmed | W2-HERMES | S0 | plan §5.3 |
| F-11 | Risk policy | Reads allowed; `write` asks and can be remembered by a standing approval; `sensitive`, `destructive` and `actuate` always ask; actuation lab-only until LT-VM-18. Automations may not request `destructive` in v1 (they notify instead) | CORE-AUTO-1, DEV-API-7 | S1 | plan §5.6, API §16 Q1–Q2 |
| F-12 | CLI approvals with a static owner token before passkeys exist | Accept the documented gap until CORE-SEC-2; the approval card shows "approved without passkey" | DEV-CLI-4 | S1 | CLI §14.3, API §16 Q4 |
| F-13 | CLI distribution on the Mac | Both a Homebrew tap and a signed download | DEV-CLI-13 | S1 | CLI §14.4 |
| F-14 | When an upgraded box turns on role scopes, do `adult` and `guest` lose reads they have today? | Off by default on upgraded boxes, on for new boxes | DEV-API-5 | S1 | API §16 Q3 |
| F-15 | Default grant and token expiry for a new personal agent | `reader` grant (`requester` only when asked for); 90-day tokens, renewable | DEV-MCP-2, CORE-SEC-3 | S1 | MCP §13 Q2–Q3 |
| F-16 | May an agent withdraw its own pending request? | Yes: it only reduces what happens, and it is audited | DEV-MCP-3, DEV-API-7 | S2 | MCP §13 Q1 |
| F-17 | npm scope and PyPI project owner for the SDKs | `@onemind/sdk` if the `onemind` npm org can be created, else `@onemindos/sdk`; PyPI owned by an org account with two maintainers and trusted publishing only | DEV-SDK-9 | S3 (reserve names in S1) | SDK §11 Q1–Q2 |
| F-18 | First public SDK release and stability promise | `0.1.0` after DEV-SDK-8 and gateway HTTPS; stay `0.x` until manifest v1 (PLAN-E6) and identity (CORE-SEC-10) land | DEV-SDK-9 | S3 | SDK §11 Q3–Q4 |
| F-19 | May plugin agents ever get `actions:read:all` or `audit:read:all`? | No; personal agents only | DEV-MCP-2, DEV-PLG-3 | S2 | MCP §13 Q4 |
| F-20 | Record every MCP read in the hash chain, or per-minute summaries? | Per-minute summaries (keeps the chain small on a Pi; reads change nothing) | DEV-MCP-6 | S2 | MCP §13 Q5 |
| F-21 | Plugin manifest: an App with an `extensions` block, not a new `onemind.plugin` kind | Confirm | DEV-PLG-1 | S3 | PLUGIN-SDK §20.1 |
| F-22 | Plugin UI: sandboxed iframe and postMessage bridge; reject module federation | Confirm | DEV-PLG-5 | S3 | PLUGIN-SDK §20.2 |
| F-23 | Plugin phase 1 = private tier and first-party only; community plugins and community apps hidden by default in phase 2 | Confirm | DEV-PLG-14, PLAN-E5 | S3 | PLUGIN-SDK §20.3, plan §5.8 |
| F-24 | NATS subject grammar for plugin events | Plugins never publish under `onemind.>`; the gateway relays plugin events as `onemind.plugin.<app-id>.<event>` | DEV-PLG-10 | S4 | PLUGIN-SDK §20.6 |
| F-25 | Day-1 hardware (D-004): Pi 5 16 GB + NVMe, a 4 GB Pi 5 for the soak, Jetson Orin Nano Super | Order now; the Pi soak must start by 2026-12-11 | CORE-UPDATE-4, PLAN-E10, PLAN-E11 | S0 | plan §5.4 |
| F-26 | Approve the 90-day plan's deviations and rewrite gate content G1–G6 for D-007 (Debian) | Approve; rewrite in PLAN-E1 | PLAN-E1 | S0 | plan §5.1 |
| F-27 | OS security channel: run the offline TUF root ceremony and add the signing secrets | Do it before G1 so security updates can publish | OS-SECPIPE publishing, CORE-SEC-8 | S1 | PR #14 |
| F-28 | Enable GitHub Discussions for the forum | Yes, with giscus click-to-load on the site | CORE-WEB-4 | S3 | WEBSITE |
| F-29 | Launch rules: channels; no update claim before G1, no actuation claim before G4; demos on lab hardware with mock data only | Confirm | CORE-WEB-5 | S3 | plan §5.9–§5.10 |
| F-30 | Defer revenue share, certification fee and the D-001 pro/open ADR | Defer past the leap | – | – | plan §5.11 |
| F-31 | TAK licensing (GPL/AGPL servers only as separate apps; official TAK Server bring-your-own-licence?) and drones (no agent flight commands; MAVLink read-only) | Confirm when PLAN-E14/E15 leave parking | PLAN-E14, PLAN-E15 | S4+ | plan §5.7, §5.12 |

### 1.1 Defaults applied in contract §12 (2026-11-12)

Contract §12 was written against these proposed defaults; a different answer is a follow-up contract PR. **F-1** is applied as: per-box CA by default, and optional Let's Encrypt (DNS-01) when the owner brings a domain (§12.7); a Tailscale certificate may still serve the mesh name when remote access is on. Also applied as listed above: F-2, F-6, F-7, F-8, F-9, F-11, F-12, F-14, F-15, F-16, F-19, F-24.

### 1.2 Identity choices made on `feat/identity` (2026-11-12)

The identity stream relies on F-2 (passkey on every owner approval once one exists), F-12 (token approvals accepted, and audited, until then), F-14 (role scopes) and F-15 (personal agent tokens: `reader`, 90 days). It also made these calls; each is reversible in one module ([core/IDENTITY.md](core/IDENTITY.md) §7):
- **First owner:** `POST /v1/auth/setup` (a path §12.6 implies as "the setup session" but does not name), authorised by the install owner token or a first-boot token file. Proposal: add it to §12.6 in the next contract PR.
- **Password + TOTP** sign-in exists beside passkeys, so a household member without a passkey device can sign in. A password session never counts as step-up.
- **Static-file tokens keep v0 behaviour** (no role scopes, no app sharing), so headless setups do not break; once an owner has a passkey, a file owner token can approve only with that passkey's assertion.
- **Password hashing is stdlib scrypt** (N=2^15), not Argon2, to add no native dependency; logins are rate-limited.

## 2. For the contract owner: leap specs vs the contract §12 draft

**Settled 2026-11-12** in contract §12 ([`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §12.21). Every row below took the proposal, except: `offline_not_supported` is not added (it is `503 unavailable` with reason `node_offline`); the join ticket role is `worker|leaf`; the heartbeat mesh object is top-level `mesh`. Specs that still use a losing name are renamed when next edited. The table is kept as the record.

The architecture stream's `docs/architecture/CONTRACT-12-DRAFT.md` (branch `docs/core-architecture`, not merged) and the leap specs were written in parallel. Settle each row in contract PR C12-A, then rename in one PR across whichever side loses.

| Topic | Leap specs | §12 draft | Proposal |
|---|---|---|---|
| Risk classes | `read`, `write`, `sensitive`, `destructive`, `actuate` (API §5.11, AUTOMATION §3.2) | `low`, `medium`, `high`, `critical` | Leap names: they say what the action does, and standing-approval rules key on them. If the draft's scale is kept, map read→low, write→medium, sensitive→high, destructive and actuate→critical |
| Live stream route | `GET /v1/events` (API §10) | `GET /v1/stream` | `/v1/events`; the SDKs and CLI already use it |
| Approval challenge | `POST /v1/actions/{id}/approve-options`, body field `webauthn`, 120 s (SECURITY §3.2) | `POST /v1/actions/{id}/approval-challenge`, field `assertion`, 60 s | Either works; pick one name and one lifetime. Leap default: `approve-options` (same pattern as the login routes), 120 s |
| Plan preview | `GET /v1/actions/{id}/preview` and MCP `preview_action` | `POST /v1/plans` (before a request) | Both: `POST /v1/plans` before a request (MCP `preview_action` maps to it), the action's stored plan for the card |
| Approval binding | `plan_sha256` | `plan_sha256` | Agreed. Draft open point 3 (optional → required): optional for v0 clients with an audited `plan_unchecked`, required for `OneMind-API-Version: 1` |
| New principal kinds | `plugin` (PLUGIN-SDK §7) | `automation`, `node` | Add all three in one PR |
| Error codes | `rate_limited`, `policy_refused`, `payload_too_large`, opt-in `invalid_request` and `method_not_allowed` (API §6) | `rate_limited`, `unavailable`, plus a `reason` field | Add the union; `invalid_request` and `method_not_allowed` only behind `OneMind-Errors: 2` |
| List shape for new endpoints | `Link` header pagination, arrays kept for v0 routes (API §7.1) | `{"items": [...], "next_cursor": ...}` | One style for every new endpoint; leap default follows API §7.1 because the SDK iterators were designed on it |
| Scope and permission names | API §8.2 (`actions:read`, `audit:read`, `notifications:send`, `events:read`, suffix `actions:request:<type>`); MCP §4.1 (`actions:read:own`/`:all`, `audit:read:own`/`:all`, `actions:withdraw:own`, `docs:read`, bundles); PLUGIN-SDK §5.2 (`actions:read:self`, `alerts:raise`, `events:subscribe:<pattern>`) | – | API §8.2 names as the base; `:own`/`:all` and `:<pattern>` become narrowing suffixes like `actions:request:<type>`; `actions:read:self` → `actions:read:own`; `alerts:raise` → `notifications:send` |
| Manifest fields for app and plugin principals | MCP §5.2 `spec.agent.scopes` and `limits`; PLUGIN-SDK §4.2 `spec.plugin` + `spec.permissions` (API §5.9 now follows it) | `spec.agent` only (contract §11.2) | Agents: `spec.agent.scopes`; plugins: `spec.plugin` + `spec.permissions`; one schema PR with C12-H and C12-PLG |
| CLI verbs | One tree in CLI.md §3 (`fabric join`, `auto`, `policy`, `backup now`, `restore`) | `node join`, `automations`, `activity`, `init`, `app import`, `backup run/snapshots/restore` | CLI.md §3 is the tree; draft verbs become aliases (`node join` and `backup run` already are). `init` and `app import` get added to CLI.md when their epics start |

## 3. Contradictions fixed between the leap specs (2026-11-12)

| Topic | Was | Now |
|---|---|---|
| Approval binding field | `params_digest` (API), `effects_digest` (MCP), `plan_sha256` (SANDBOX, SECURITY, MOBILE) | `plan_sha256` everywhere |
| Approve body | `{"step_up": {"webauthn": …}}` (API) vs `{"webauthn": …}` (SECURITY, MOBILE) | `{"plan_sha256", "webauthn"}` after `approve-options` |
| Pending cap | 20 per requester (API) vs 10 (MCP, SECURITY, CLI, plan E3) | 10; the 11th gets 429 `rate_limited` |
| Who-am-I route | `/v1/me` (API, MCP), `/v1/whoami` (CLI), `/v1/auth/whoami` (SECURITY, DASHBOARD) | `/v1/me` |
| Risk classes | API's four levels vs AUTOMATION's routine write / grant-widening / destructive / actuate; `app.install` was `write` in one and grant-widening in the other | Five classes; `app.install` and `node.join` are `sensitive` |
| Node join | Three flows: API (ticket + request), CLI (`/v1/fabric/invites`, `/v1/fabric/join`), FABRIC (URL + CA, no ticket) | API §5.1 flow in all three; CLI `fabric qr` / `fabric join <code>` |
| SDK generation | DEV-API-14 and DEV-SDK-* both built the SDKs, with different Python package names and generators | DEV-SDK-* own it; DEV-API-14 superseded; Python package `onemind-sdk` |
| Events wire format | SDK used `?topics=`, `action.updated`, `event: reset`, `: ping` | API §10 names: `?types=`, `action.state_changed`, `stream.reset`, `: keepalive` |
| Phase-B route modules | DEV-API-10…13 and the core epics both owned `fabric.py`, `backups.py`, `notify.py`/`notify/`, `automation.py`, `policies.py`, `os_updates.py` | Core epics own the files; API rows define the shapes |
| CLI file layout | Core specs used `cmd/onemind/<x>.go`; CLI uses `cmd/onemind/cli/<group>.go` | `cmd/onemind/cli/<group>.go` everywhere; `mcp` by DEV-MCP-7, `plugin` by DEV-PLG-* |
| CLI command names | `onemind token`, `onemind join`, `onemind backup run/restore`, `onemind app check`, and core groups missing from the CLI tree | One tree in CLI.md §3 with the core groups added; old names are aliases or renamed |
| MCP code location | PLUGIN-SDK extended `mcp.py`; MCP turns it into a package | `core/onemind_core/mcp/` package, projection via `mcp/catalog.py` |
| Architecture links | `docs/FABRIC.md` and siblings | `docs/architecture/FABRIC.md` and siblings (where the arch branch puts them) |
| Circular dependency | CORE-NOTIFY-4 and CORE-MOBILE-5 each depended on the other | Built together; NOTIFY-4 depends on NOTIFY-3 and F-4 |
| Standing-approval creation (review, 2026-11-12) | AUTOMATION let an agent request `policy.create`; CLI let a rule carry `approve: auto` | Owner-only direct write with step-up (API §5.5.3) everywhere; rules only request; policies never cover `sensitive`, `destructive` or `actuate` (API §5.5.3 now lists `actuate` too) |
| Agent-requestable types (review) | MCP listed `node.join` as agent-requestable and `update.apply`; it barred restore while API and BACKUPS allowed an agent to request one | Only the joining node requests `node.join`; `os.update.apply`; `backup.restore` requestable only with an explicit owner grant, always `destructive` |
| Token prefixes (review) | `om_agent_` (SECURITY), `omt_agent_` (CLI), `om_agt_` (API, MCP) | API §5.9 kinds everywhere |
| Routes and names (review) | MCP used `POST /v1/actions:preview`, `GET /v1/audit`, `/v1/audit/status`; SANDBOX `GET /v1/apps/{id}/plan`; CLI `/v1/notify/test`, `/v1/rules`, `os.update`; UPDATES `os.update`, `PUT /v1/os/policy`; BACKUPS `GET /v1/backups`; AUTOMATION `/v1/automations`, `/v1/policies`; FABRIC an older join body | API names: `POST /v1/plans`, `/v1/audit/events`, `/v1/audit/verify`, `/v1/notifications/channels/{id}/test`, `/v1/automation/rules`, `/v1/approval-policies`, `os.update.apply`, `/v1/os/settings`, `/v1/backups/status`, API §5.1 join body; `os.rollback` added to API §5.12 |
| SDK names (review) | Examples used `from onemind import Client`, Go `NewClientFromEnv`, `*onemind.APIError`, module `…/sdk/go/onemind`, `/v1/principal`, `decided_by` | SDK.md names: `onemind_sdk`, `onemind.FromEnv()`, `*onemind.Error`, module `…/sdk/go`, `/v1/me`, `approved_by` |
| Backlog order (review) | DEV-CLI-11 (S3) accepted `publish`, built by DEV-PLG-14 in S4+; DEV-API-3/-4 used new contract names without C12-A; CORE-DASH-7 tested Web Push without NOTIFY-3 | `publish` acceptance moved to PLG-14; C12-A and NOTIFY-3 added as dependencies |
| File ownership (review) | `executors.py`, `internal/detect/`, `mcp/catalog.py`, feature dashboard pages, `site/**` and `os/**` pieces were claimed by two streams without a rule | WORKSTREAMS §3 rows name one owner and the hook order |

## 4. Loose ends found, not fixed here

- Core plumbing (`feat/core-plumbing`, [core/PLUMBING.md](core/PLUMBING.md)) changes three WORKSTREAMS §4 hotspot rules; update them when it merges: routes register in `ROUTERS` in `app.py` (not a `routes.py`); `ledger.py` gets no numbered migration files (each feature has its own `FeatureSchema` step chain in its module); the CLI registry is `groups` in `cmd/onemind/cli/root.go` with stdlib `flag`. F-8 (cobra) is allowed but not used yet, because the refactor had to keep the CLI output identical. DEV-CLI-1 can switch `root.go` to cobra without touching the group files. `onemindd` registrations go in `cmd/onemindd/registry.go`, not `main.go`.

- `feat/app-hermes` and `feat/apps-wave2` have no work yet, so W2-HERMES and W2-SEEDS may slip into S1.
- `feat/app-pipeline` has an uncommitted `renovate.json`; `feat/design-system`, `feat/mobile-shell` and the arch branch's `docs/architecture/` are untracked. Commit and push them so they are not lost.
- The updater merged as PR #15 after the specs were written. The review corrected the "what exists" rows in API, CLI, SDK, MCP, PLUGIN-SDK, UPDATES and BACKUPS; FABRIC and UPDATES still name the heartbeat `update` object's branch. STATUS.md has the live state.
- NOTIFICATIONS uses `/v1/alerts` (alert records, ack, resolve, fix) and `/v1/notify/routes`; API §5.4 uses `/v1/notifications/*` (per-person inbox, channels, preferences). Settle in C12-E: proposal, keep `/v1/alerts` for system alerts and API §5.4 for inbox and channels, and add `/v1/alerts` to API.md.
- DEPLOYMENTS action types (`deploy.apply`, `deploy.rollback`), `backup.key.rotate`, `app.update` and `app.restart` are not yet in API.md §5.12; add them with C12-C and C12-D.
- CLI.md `onemind fabric leave` calls `POST /v1/fabric/leave`, which API.md §5.1 does not define yet.
- The updater PR leaves open: shipping it in the image, the offline grace period, and where the owner's settings override lives (CORE-UPDATE-2, CORE-UPDATE-7).
- `onemind fabric join <code>` needs the hub address when mDNS cannot find it; CLI.md now takes `--hub`, but the QR content rule ("no network details") should be settled in C12-B.
- API.md §17 follow-ups remain: `errors.py` maps 405 to `not_found` and 422 to `conflict`; the event stream must read from the same append path as NATS `onemind.audit`.
- The leap branch was cut before PR #15 merged; rebase before merging it.
