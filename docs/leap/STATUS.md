<!-- SPDX-License-Identifier: Apache-2.0 -->
# Leap status tracker

**Last updated:** 2026-11-12, about 10:00 UTC (from `gh pr list --state all`, `git branch -a`, the worktree list, CHANGELOG.md and the stream branches). Part of [the leap](README.md). Order and acceptance: [BACKLOG.md](BACKLOG.md). How to claim an epic: [WORKSTREAMS.md](WORKSTREAMS.md) §6.

**Board rule.** Every stream gets its row here on the day it starts, with its branch, even before the first commit. A stream with no epic yet adds one (id, title, row here, size, dependencies, owner paths and acceptance in BACKLOG.md). When its PR opens the row moves to `in-review` with the PR link, and it moves to `done` with the PR link **in the same PR as its CHANGELOG entry**. A partly delivered epic says what landed and what is pending ("in-progress: modules merged in #37, wiring pending"). If work exists that this page does not show, this page is wrong: fix it first.

> **Explain it like I am the founder**
> One row per epic, saying where it stands: `todo`, `in-progress` (being built on a branch, or partly merged with the rest pending; the note says which), `in-review` (a PR is open), `done` (merged), `blocked: founder` (waits on your decision or hardware), `parked` or `superseded`.
> Branch "(local)" means the work is only in a worktree on the build machine, not on GitHub yet.
> Today: 35 of 43 PRs merged, 7 open (this one included), 1 closed; 21 stream branches running and one queued; 30 epics done; 9 rows wait on you (F-25 hardware, F-27 signing keys, F-7 override, F-5 website host, and the photos server choice).

## Summary

| State | Rows | Which |
|---|---|---|
| done | 30 | S0 landed (OS-UPDATER, OS-SECPIPE, CORE-UPDATE-1, W2-GW, W2-PIPE, W2-DEPLOY, W2-HERMES, W2-SEEDS, PA-ALIGN, PA-ARCH, PA-THREAT, PA-UI, PA-SITE, PA-MOBILE, MKT-CANDIDATES, MKT-TAXONOMY, UI-LEAP, CORE-NET-P1, LEAP-DOCS), contract §12 (C12-A…H), CORE-PLUMB, UMB-STUDY, BRAND-0 |
| in-review | 14 | CORE-SANDBOX-1…5, CORE-SEC-9, CORE-SEC-5 (#40); CORE-SEC-2, -3, -10, DEV-API-5 (#41); TEST-CI-1 (#42); UMB-CLIENT-8 (#33); UMB-PHOTO-4 (#34) |
| in-progress | 64 (59 + 5 UMB) | 46 on running branches (see "Running now"); 12 partly merged with the rest pending (DEV-API-1, CORE-NET-3, -4, -8, -9, CORE-BACKUP-2, -3, -4, -7, UMB-STOR-3, UMB-FILES-7, PLAN-E5); 6 streams started with no commits yet |
| todo | 240 (131 + 109 UMB) | |
| blocked: founder | 9 | F-25, F-27, F-7, F-5; CORE-UPDATE-4, CORE-NET-14 (F-25); CORE-WEB-1 (F-5); APP-OVERRIDE-1 (F-7); PHOTOS-SRV-1 (Immich vs built-in) |
| parked | 5 | CORE-NET-15, PH2-DESKTOP, PLAN-E7-LAB, PLAN-E14, PLAN-E15 |
| superseded | 1 | DEV-API-14 |
| **total** | **363** | Alias ids (the last table under "Added 2026-11-12") are not counted again |

**PRs.** 35 merged (#1–#39 except #27, #33, #34, #35). Open: this PR (#43), [#42](https://github.com/onemindos/ONEMINDOS/pull/42) CI test matrix, [#41](https://github.com/onemindos/ONEMINDOS/pull/41) identity, [#40](https://github.com/onemindos/ONEMINDOS/pull/40) security P0 (checks green), [#34](https://github.com/onemindos/ONEMINDOS/pull/34) phone photo backup, [#33](https://github.com/onemindos/ONEMINDOS/pull/33) desktop client, [#27](https://github.com/onemindos/ONEMINDOS/pull/27) deploy kit (overlaps #26; its useful parts are DEPLOY-PORT27-1…7). Closed without merge: #35 (replaced by #36).

### Running now

"Ahead" is commits on the branch that are not on `main`. Branches with no PR are local only: push them so the work is not lost.

| Stream branch | What | Rows it moves | Ahead | PR |
|---|---|---|---|---|
| `feat/e2e-golden-path` | Golden-path e2e (being integrated now) | E2E-GOLDEN | 6 | – |
| `feat/sec-p0` | Install sandbox, gateway RBAC, k3s secrets encryption, limits, headers | CORE-SANDBOX-1…5, CORE-SEC-9, CORE-SEC-5 (part) | 8 | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| `feat/identity` | Household identity, passkeys, sessions, scoped tokens (§12.6); carries #40 merged in | CORE-SEC-2, -3, -10, DEV-API-5 | 14 | [#41](https://github.com/onemindos/ONEMINDOS/pull/41) |
| `feat/devsurface` | OpenAPI export, SDKs (TS, Python, Go), cobra CLI, MCP catalogue v1, stdio bridge, events, audit read | DEV-SDK-1…3, -5…8, DEV-API-8, -9, DEV-CLI-1…5, -12, -13, DEV-MCP-1, -4…8 | 9 | – |
| `feat/notify-monitor` | Notifications, alerts, channels (§12.14); monitoring (§12.15) | CORE-NOTIFY-1, -2, -3, -6, DEV-API-12, CORE-MON-1 | 8 | – |
| `feat/automation` | Rules, standing approvals, dry run, kill switch (§12.17) | CORE-AUTO-2…5, DEV-API-13 | 5 | – |
| `feat/files` | Files service: spaces, tus uploads, trash, quotas, folder grants | UMB-FILES-1, -2, -6 | 3 | – |
| `feat/dashboard-v2` | Dashboard v2 on `@onemind/ui` against the real API | CORE-DASH-2 | 5 | – |
| `feat/image-line` | OneMind in the image, first boot, Pi 5, Jetson, USB installer, cloud images, releases | IMG-1…6 | 6 (+ uncommitted boards) | – |
| `feat/brand-single-source` | `brand.json` and sync, logo everywhere | BRAND-1 | 5 | – |
| `feat/market-batch-1` | 10 Market apps | MKT-BATCH-1, PLAN-E5 | 11 | – |
| `feat/market-batch-2-3` | 20 Market apps | MKT-BATCH-2-3 | 0 | – |
| `test/register` | Test register and `test-all` | TEST-REG-1 | 1 | – |
| `feat/test-security` | Security tests | TEST-SEC-1 | 0 | – |
| `feat/test-property-fuzz` | Property and fuzz tests | TEST-PROP-1 | 0 | – |
| `feat/test-ci-matrix` | CI test matrix: browsers, axe, visual, apps on amd64/arm64, mobile builds, site links | TEST-CI-1 | pushed | [#42](https://github.com/onemindos/ONEMINDOS/pull/42) |
| `docs/slop-audit` | Slop audit and fixer | QUAL-SLOP-1, -2 | 0 | – |
| `feat/plugin-sdk-v0` | Plugin SDK v0 | DEV-PLG-0 | 0 | – |
| `docs/site-user-guides` | Website user guides | CORE-WEB-G | 0 | – |
| `feat/app-lifecycle` | App lifecycle, plan, credentials, health-gated updates | APP-LIFE-1…5 (UMB-APP-3, -4, -5, CORE-UPDATE-5, -6, CORE-DEPLOY-4) | no branch yet | – |
| `feat/mobile-photos` | Phone photo backup (pushed) | UMB-PHOTO-4 | 3 | [#34](https://github.com/onemindos/ONEMINDOS/pull/34) |
| `feat/desktop-client` | Tauri tray client (pushed) | UMB-CLIENT-8 | 2 | [#33](https://github.com/onemindos/ONEMINDOS/pull/33) |

Empty branches with no stream: `feat/app-hermes` and `feat/apps-wave2` (both delivered in #25; safe to delete once confirmed).

### Blocked on the founder

- **F-25 hardware** (Pi 5 16 GB + NVMe, a 4 GB Pi 5, Jetson Orin Nano Super): blocks the metal runs CORE-UPDATE-4, CORE-NET-14, PLAN-E10, PLAN-E11. The Pi soak must start by 2026-12-11.
- **F-27 signing keys** (offline TUF root ceremony and secrets): blocks OS-SECPIPE publishing, CORE-SEC-8 and signed releases (IMG-6).
- **F-7 owner override** for scan-blocked installs: blocks APP-OVERRIDE-1.
- **F-5 website domain and host**: blocks CORE-WEB-1, CORE-WEB-4 and the downloads page.
- **Photos server** (built-in vs Immich, with F-47): blocks PHOTOS-SRV-1, so #34 has no box to upload to yet.

## Already merged

| PR | Merged (UTC) | Branch | What it delivered | Maps to |
|---|---|---|---|---|
| [#39](https://github.com/onemindos/ONEMINDOS/pull/39) | 2026-11-12 | `contract/s12` | Contract §12: phase-B interfaces, binding | C12-A…H |
| [#38](https://github.com/onemindos/ONEMINDOS/pull/38) | 2026-11-12 | `feat/core-plumbing` | Core plumbing: routers, per-feature tables, settings sections, event hook, CLI and onemindd registries | CORE-PLUMB, DEV-API-1 (part) |
| [#37](https://github.com/onemindos/ONEMINDOS/pull/37) | 2026-11-12 | `feat/core-net` | Networking Part 1: mesh lab PASS, onemindd mesh and leaf, gateway mesh client, app proxy, box CA | CORE-NET-P1, CORE-NET-3, -4, -8, -9 (part) |
| [#36](https://github.com/onemindos/ONEMINDOS/pull/36) | 2026-11-12 | `brand/onemind-logo-signed` | OneMind logo | BRAND-0 |
| [#32](https://github.com/onemindos/ONEMINDOS/pull/32) | 2026-11-12 | `feat/onemindd-backup` | Backup agent (restic): schedule, retention, targets, Rewind, restore verification; not wired | CORE-BACKUP-2 (part) |
| [#31](https://github.com/onemindos/ONEMINDOS/pull/31) | 2026-11-12 | `feat/onemindd-storage` | Disk inventory, SMART, btrfs mirror status, dry-run plans; not wired | UMB-STOR-3 (part) |
| [#30](https://github.com/onemindos/ONEMINDOS/pull/30) | 2026-11-12 | `feat/umbrel2-study` | umbrelOS 2 deep dive and the UMB backlog | UMB-STUDY |
| [#29](https://github.com/onemindos/ONEMINDOS/pull/29) | 2026-11-12 | `feat/ui-leap-squash` | UI leap: customization, Home and widgets, Store, palette, notifications, onboarding, Settings, parity audit | UI-LEAP |
| [#28](https://github.com/onemindos/ONEMINDOS/pull/28) | 2026-11-12 | `feat/app-taxonomy` | App and deployment taxonomy | MKT-TAXONOMY |
| [#26](https://github.com/onemindos/ONEMINDOS/pull/26) | 2026-11-12 | `feat/deploy-v0` | `install.sh` hub/node, compose dev hub, `verify.sh` | W2-DEPLOY |
| [#25](https://github.com/onemindos/ONEMINDOS/pull/25) | 2026-11-12 | `feat/app-pipeline` | App pipeline and the wave-2 apps including Hermes | W2-PIPE, W2-HERMES, W2-SEEDS |
| [#24](https://github.com/onemindos/ONEMINDOS/pull/24) | 2026-11-12 | `feat/gateway-agent-mcp` | Gateway wave 2: scan gate, agent principals, `/mcp`, catalog fields | W2-GW |
| [#23](https://github.com/onemindos/ONEMINDOS/pull/23) | 2026-11-12 | `docs/changelog-batch2` | CHANGELOG and STATUS for #16–#22 | LEAP-DOCS |
| [#22](https://github.com/onemindos/ONEMINDOS/pull/22) | 2026-11-12 | `feat/app-candidates` | Ranked Market candidates from 7 stores | MKT-CANDIDATES |
| [#21](https://github.com/onemindos/ONEMINDOS/pull/21) | 2026-11-12 | `feat/mobile-shell` | Android and iPhone app shells | PA-MOBILE |
| [#20](https://github.com/onemindos/ONEMINDOS/pull/20) | 2026-11-12 | `feat/design-system` | Design system `@onemind/ui` | PA-UI |
| [#19](https://github.com/onemindos/ONEMINDOS/pull/19) | 2026-11-12 | `feat/website` | Website (Astro + Starlight) | PA-SITE |
| [#18](https://github.com/onemindos/ONEMINDOS/pull/18) | 2026-11-12 | `docs/security-threat-model` | Threat model and hardening backlog | PA-THREAT |
| [#17](https://github.com/onemindos/ONEMINDOS/pull/17) | 2026-11-12 | `docs/core-architecture` | Core alignment and phase-B architecture | PA-ALIGN, PA-ARCH |
| [#16](https://github.com/onemindos/ONEMINDOS/pull/16) | 2026-11-12 | `docs/leap` | Leap plan and CHANGELOG | LEAP-DOCS |
| [#14](https://github.com/onemindos/ONEMINDOS/pull/14) | 2026-11-12 | `feat/os-security-pipeline` | OS security pipeline (publishing off until F-27) | OS-SECPIPE |
| [#15](https://github.com/onemindos/ONEMINDOS/pull/15) | 2026-11-12 | `feat/onemindd-updater` | onemindd OS updater and `onemind update` | OS-UPDATER |
| [#12](https://github.com/onemindos/ONEMINDOS/pull/12) | 2026-11-12 | `contract/wave2-interfaces` | Contract §11: scan record, agent principals, MCP, catalog fields | wave 2 interfaces |
| [#13](https://github.com/onemindos/ONEMINDOS/pull/13) | 2026-11-12 | `fix/main-ci` | Actions pinned by commit, SPDX headers; `main` green | CI |
| [#11](https://github.com/onemindos/ONEMINDOS/pull/11) | 2026-11-12 | `feat/apps-wave1` | App manifest schema, validator, CI; 3 seed apps | wave 1 apps |
| [#10](https://github.com/onemindos/ONEMINDOS/pull/10) | 2026-11-12 | `build/core-v0` | OS image build (BM0/BM1): Debian 13, RAUC, health gate, QEMU battery | image stream |
| [#8](https://github.com/onemindos/ONEMINDOS/pull/8) | 2026-11-12 | `feat/dashboard-mvp` | Dashboard MVP: Home, Nodes, Market, Approvals | dashboard v0 |
| [#7](https://github.com/onemindos/ONEMINDOS/pull/7) | 2026-11-12 | `feat/onemindd-node-agent` | onemindd node agent and `onemind` CLI v0 | node agent v0 |
| [#9](https://github.com/onemindos/ONEMINDOS/pull/9) | 2026-11-12 | `feat/core-gateway-v0` | FastAPI gateway v0: owner-only approvals, ledger, audit chain | gateway v0 |
| [#6](https://github.com/onemindos/ONEMINDOS/pull/6) | 2026-11-12 | `founder/app-pipeline-and-updates` | Contract §9–§10: app pipeline and automatic updates | contract |
| [#5](https://github.com/onemindos/ONEMINDOS/pull/5) | 2026-11-12 | `founder/hermes-app-spec` | Contract §7–§8: Hermes app and wave-2 seed apps | contract |
| [#4](https://github.com/onemindos/ONEMINDOS/pull/4) | 2026-11-12 | `founder/hardware-bringup` | Lesson 06 and BD-DO-1 hardware bring-up | hardware |
| [#1](https://github.com/onemindos/ONEMINDOS/pull/1) | 2026-11-12 | `research/ultracode-foundation` | Research mission 01: foundation and 10-year plan | research |
| [#3](https://github.com/onemindos/ONEMINDOS/pull/3) | 2026-11-11 | `mission/one-mind-fabric` | Research mission 02 brief (fabric) | research |
| [#2](https://github.com/onemindos/ONEMINDOS/pull/2) | 2026-11-11 | `founder/base-os-lesson-03` | Learning lessons 03–05 | learning |

## Every epic

### S0: land the in-flight work (weeks 0–2)

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| OS-UPDATER | onemindd OS updater: TUF-verified, policy and window, restic pre-sn… | done | `feat/onemindd-updater` | [#15](https://github.com/onemindos/ONEMINDOS/pull/15) |
| OS-SECPIPE | OS security pipeline: nightly Debian check, rebuild, SBOM/CVE+VEX/C… | done | `feat/os-security-pipeline` | [#14](https://github.com/onemindos/ONEMINDOS/pull/14) |
| CORE-UPDATE-1 | Land both update branches with CI green | done | (both update branches) | [#15](https://github.com/onemindos/ONEMINDOS/pull/15) and [#14](https://github.com/onemindos/ONEMINDOS/pull/14) |
| W2-GW | Gateway wave 2: scan gate, app agent principals, `/mcp` with 3 tool… | done | `feat/gateway-agent-mcp` | [#24](https://github.com/onemindos/ONEMINDOS/pull/24) |
| W2-PIPE | App pipeline: scaffolder, app-gate (§9.4), `scan.json` (§11.1), k3d… | done | `feat/app-pipeline` | [#25](https://github.com/onemindos/ONEMINDOS/pull/25) |
| W2-DEPLOY | Developer install: `install.sh --role hub` or `node`, compose dev hub… | done (kit parts of #27 still to port: DEPLOY-PORT27-1…7) | `feat/deploy-v0` | [#26](https://github.com/onemindos/ONEMINDOS/pull/26) |
| W2-HERMES | Hermes packaged as `apps/hermes-agent`, an agent principal | done (`apps/hermes-agent`) | `feat/app-pipeline` | [#25](https://github.com/onemindos/ONEMINDOS/pull/25) |
| W2-SEEDS | Wave-2 seed apps | done (Node-RED, Mosquitto, Vaultwarden, Actual Budget, Zigbee2MQTT) | `feat/app-pipeline` | [#25](https://github.com/onemindos/ONEMINDOS/pull/25) |
| PA-ALIGN | Core alignment against the leading self-hosted OSes | done | `docs/core-architecture` | [#17](https://github.com/onemindos/ONEMINDOS/pull/17) |
| PA-ARCH | Phase-B architecture docs and `CONTRACT-12-DRAFT.md` | done | `docs/core-architecture` | [#17](https://github.com/onemindos/ONEMINDOS/pull/17) |
| PA-THREAT | Threat model and ranked hardening backlog (H-ids) | done | `docs/security-threat-model` | [#18](https://github.com/onemindos/ONEMINDOS/pull/18) |
| PA-UI | Design system `@onemind/ui`: tokens and components, light and dark | done | `feat/design-system` | [#20](https://github.com/onemindos/ONEMINDOS/pull/20) |
| PA-SITE | Website (Astro + Starlight) committed | done | `feat/website` | [#19](https://github.com/onemindos/ONEMINDOS/pull/19) |
| PA-MOBILE | Mobile shell (Expo) committed | done | `feat/mobile-shell` | [#21](https://github.com/onemindos/ONEMINDOS/pull/21) |
| MKT-CANDIDATES | Ranked Market candidate list from 7 competitor stores | done | `feat/app-candidates` | [#22](https://github.com/onemindos/ONEMINDOS/pull/22) |
| CORE-NET-P1 | Mesh (Headscale + DERP), NATS leaf, app proxy, box CA, NAT lab (+ UMB-APP-7, UMB-APP-8) | done (Part 1: new modules and the mesh lab; wiring is CORE-NET-10…13) | `feat/core-net` | [#37](https://github.com/onemindos/ONEMINDOS/pull/37) |
| UI-LEAP | Parity audit, customization, Home widgets, Store + app management, shell, Settings (+ UMB-DESK-2, -3, -4, -8) | done | `feat/ui-leap-squash` | [#29](https://github.com/onemindos/ONEMINDOS/pull/29) |
| MKT-TAXONOMY | App and deployment categories | done | `feat/app-taxonomy` | [#28](https://github.com/onemindos/ONEMINDOS/pull/28) |
| PLAN-E1 | Workbench (G0) and gate content re-synced to D-007 | todo | founder lab kit | – |
| LEAP-DOCS | Leap specs, workstreams, backlog, status, decisions, CHANGELOG | done | `docs/leap` | [#16](https://github.com/onemindos/ONEMINDOS/pull/16) |

### S1: contract §12, plumbing, sandbox, SDK/CLI/MCP foundations (weeks 1–5)

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| C12-A | Contract §12-a: conventions, error codes (`rate_limited`, `policy_r… | done (§12.1–§12.5) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| C12-H | Contract §12-h: MCP additions (scopes in `spec.agent`, preview, wit… | done (§12.19–§12.20) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| DEV-API-1 | Route inventory, conventions, `routes.py` registration seam | in-progress: registration seam merged in #38 (`core/onemind_core/routers/`); route inventory in API.md pending | `feat/core-plumbing` | [#38](https://github.com/onemindos/ONEMINDOS/pull/38) |
| DEV-API-3 | Error model v1: `request_id`, `details`, opt-in new codes, size limits | todo | – | – |
| DEV-SDK-1 | Spec readiness: response models, stable operation ids, open enums… | in-progress | `feat/devsurface` (local) | – |
| DEV-API-2 | OpenAPI compat gate (oasdiff) and `x-onemind` extension linter | todo | – | – |
| DEV-SDK-2 | Generation toolchain and CI staleness check | in-progress | `feat/devsurface` (local) | – |
| DEV-API-4 | Pagination (Link), filters, ETag/If-Match, `Idempotency-Key` header | todo | – | – |
| DEV-API-5 | Scopes, role defaults, `/v1/me`, step-up hook | in-review: `/v1/me` on the branch; scope matrix open | `feat/identity` | [#41](https://github.com/onemindos/ONEMINDOS/pull/41) |
| CORE-SANDBOX-1 | Rule file and pure-Python checker with fixtures | in-review | `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| CORE-SANDBOX-2 | Gateway renders, checks and stores the plan; `apply -f -` with the… | in-review (render, check, `apply -f -`, `policy_refused`; stored plan and `plan_sha256` still open) | `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| CORE-SANDBOX-3 | PSA `restricted` in the image and `install.sh` | in-review (`install.sh` and app namespaces; image change recorded in SECURITY.md §7a) | `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| CORE-SANDBOX-4 | Gateway RBAC, `ValidatingAdmissionPolicy`, short-lived bound token | in-review | `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| CORE-SANDBOX-5 | Default-deny NetworkPolicy per app, host nftables, `spec.network.eg… | in-review (host nftables still open) | `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| CORE-SANDBOX-6 | app-gate uses the same checker; `scan.json` gains `policy_version`… | todo | – | – |
| CORE-AUTO-1 | Risk classes on action types, enforced in the approve path | todo | – | – |
| DEV-API-7 | Actions v1: risk, `plan_sha256` binding, preview, cancel, action-ty… | todo | – | – |
| CORE-SEC-1 | HTTPS with a per-box CA, loopback-only HTTP, pairing QR | todo | – | – |
| CORE-SEC-2 | Owner passkey, sessions, passkey-signed approvals (`approve-options`) | in-review: passkeys, sessions, household accounts, password + TOTP (`docs/leap/core/IDENTITY.md` on the branch) | `feat/identity` | [#41](https://github.com/onemindos/ONEMINDOS/pull/41) |
| CORE-SEC-3 | Token lifecycle: create, rotate, expire, revoke, CLI | in-review: API done, `onemind tokens` CLI not yet | `feat/identity` | [#41](https://github.com/onemindos/ONEMINDOS/pull/41) |
| CORE-SEC-4 | NATS nkeys and TLS | todo | – | – |
| CORE-SEC-6 | `onemind audit verify`, signed checkpoints, agent kill switch | todo | – | – |
| CORE-SEC-7 | Pending cap, plan card fields, "written by agent" label | todo | – | – |
| CORE-SEC-8 | Signing keys in GitHub environments, split jobs | todo | – | – |
| CORE-SEC-9 | CSP and security headers, body and rate limits | in-review (security headers and request limits) | `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| DEV-API-6 | Tokens API and per-plugin tokens from manifest `spec.api` scopes | todo | – | – |
| DEV-API-8 | Events stream over SSE with resume and scope filtering | in-progress | `feat/devsurface` (local) | – |
| DEV-API-9 | Audit read, verify and signed off-box checkpoints | in-progress: audit read API on the branch; signed checkpoints open | `feat/devsurface` (local) | – |
| DEV-SDK-3 | TypeScript `@onemind/sdk` core: client, auth, typed errors, retries… | in-progress | `feat/devsurface` (local) | – |
| DEV-SDK-5 | Go SDK module | in-progress | `feat/devsurface` (local) | – |
| DEV-SDK-6 | Python `onemind-sdk`, sync and async | in-progress | `feat/devsurface` (local) | – |
| DEV-SDK-8 | Shared conformance suite and mock gateway | in-progress | `feat/devsurface` (local) | – |
| DEV-CLI-1 | CLI skeleton: command tree, global flags, `--json`, exit codes, con… | in-progress | `feat/devsurface` (local) | – |
| DEV-CLI-2 | `login`, `logout`, `context`; keychain and 0600 file store; TLS pin | in-progress | `feat/devsurface` (local) | – |
| DEV-CLI-3 | Read commands: `status`, `nodes`, `apps`, `actions`, `version` | in-progress | `feat/devsurface` (local) | – |
| DEV-CLI-4 | Action flow: install/remove, approve/deny/watch, `--wait`, effects… | in-progress | `feat/devsurface` (local) | – |
| DEV-CLI-5 | `audit verify` (file, gateway, checkpoint) and `audit tail` | in-progress | `feat/devsurface` (local) | – |
| DEV-CLI-13 | Completion, generated reference and man pages, signed releases, ima… | in-progress | `feat/devsurface` (local) | – |
| DEV-MCP-1 | Read catalogue v1 and resources; `mcp.py` becomes the `mcp/` packag… | in-progress | `feat/devsurface` (local) | – |
| DEV-MCP-2 | Per-agent scopes and grants, filtered `tools/list`, pause and revok… | todo | – | – |
| DEV-MCP-4 | Rate limits per principal and the pending cap | in-progress | `feat/devsurface` (local) | – |
| DEV-MCP-7 | `onemind mcp` stdio bridge with login (keychain, CA pin), `doctor`… | in-progress | `feat/devsurface` (local) | – |
| DEV-CLI-12 | `onemind mcp` acceptance | in-progress (built inside DEV-MCP-7) | `feat/devsurface` (local) | – |
| CORE-DASH-1 | `ui/` components v0 and dark mode | todo | – | – |
| CORE-DASH-3 | Approvals plan card with passkey approve | todo | – | – |
| CORE-DASH-4 | Activity (audit) and Agents (suspend) screens | todo | – | – |
| DEV-MCP-5 | Prompt-injection defences: `<untrusted>` marking, `AgentNote` on th… | in-progress | `feat/devsurface` (local) | – |
| CORE-UPDATE-2 | Local socket, `/v1/os/*`, `os.update` and `os.rollback` actions | todo | – | – |
| CORE-UPDATE-4 | Metal runs for G1 on the x86 mini PC; start the Pi soak | blocked: founder (F-25 hardware) | – | – |
| DEV-CLI-6 | `update status/check/apply` via the onemindd socket on the box, `os… | todo | – | – |
| DEV-CLI-14 | Headless local context over the onemindd socket with peer-uid check | todo | – | – |
| PLAN-E6 | Manifest v1 freeze: merge with research 29 §6, converter, one valid… | todo | – | – |
| PLAN-E5 | App factory: 15 apps by week 6, 30 by week 13, trust cards | in-progress: 9 apps on `main` (#11, #25); 10 more on the batch-1 branch (MKT-BATCH-1) | `feat/market-batch-1` (local) | – |
| CORE-WEB-1 | Commit `site/`, CI build, link check, axe, deploy to GitHub Pages | blocked: founder (F-5 domain and host) | – | – |

### S2: fabric, backups, notifications, dashboard redesign, mobile v1 (weeks 5–9)

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| C12-B | Contract §12-b: fabric routes, heartbeat `fabric` | done (§12.11) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| C12-D | Contract §12-d: backups, manifest `backup:`, heartbeat `backup` | done (§12.12) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| C12-E | Contract §12-e: notifications, activity, repairs | done (§12.14) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| C12-G | Contract §12-g: approval challenge and iOS relay contract | done (`approve-options` challenge §12.4, iOS relay §12.14) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| CORE-SEC-5 | LUKS2 data, k3s secrets encryption, WireGuard pod traffic | in-review: k3s secrets encryption in #40; LUKS2 data (H-11, STORAGE-LUKS-1) and WireGuard pod traffic todo | `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) |
| CORE-SEC-10 | Identity floor: on-box IdP, roles, retire v0 tokens | in-review: household accounts, roles and sessions in the gateway; on-box IdP and v0-token retirement open | `feat/identity` | [#41](https://github.com/onemindos/ONEMINDOS/pull/41) |
| CORE-FABRIC-1 | `node.join` action, join tickets and requests, `onemind fabric join… | todo | – | – |
| DEV-API-10 | Fabric route shapes | todo | built inside CORE-FABRIC-1 | – |
| CORE-FABRIC-2 | Per-node identity (nkey, cert, principal) and revocation | todo | – | – |
| CORE-FABRIC-3 | `node.remove` with drain | todo | – | – |
| CORE-FABRIC-4 | Capability labels, affinity from `requires`, Market verdict | todo | – | – |
| CORE-FABRIC-5 | Leaf mode in onemindd (no k3s) | todo | – | – |
| CORE-NET-1 | Headscale adapter and config/DERP-map renderer | todo | – | – |
| CORE-NET-2 | Mesh policy generated from OneMind roles | todo | – | – |
| CORE-NET-3 | Node mesh enrollment and LAN-first coordinator resolver | in-progress: enrollment, wait-ip, status and `onemindd mesh` merged in #37; LAN-first resolver pending | `feat/core-net` | [#37](https://github.com/onemindos/ONEMINDOS/pull/37) |
| CORE-NET-4 | NATS hub users + leaf listener and node leaf config renderers | in-progress: node leaf renderer and supervisor merged in #37; hub users + leaf listener renderer pending | `feat/core-net` | [#37](https://github.com/onemindos/ONEMINDOS/pull/37) |
| CORE-NET-5 | `onemind-edge`: SNI/host routes, forward-auth, upgrades, ACME | todo | – | – |
| CORE-NET-6 | LAN names: avahi hosts, conflict check, mesh extra records | todo | – | – |
| CORE-NET-7 | Relay: SNI router, setup endpoint, WireGuard link, derper build | todo | – | – |
| CORE-NET-8 | Gateway mesh routes, forward-auth, `mesh.*` handlers | in-progress: `MeshService`, app proxy and box CA merged in #37; `/v1/mesh` routes, forward-auth endpoint and `mesh.*` handlers pending | `feat/core-net` | [#37](https://github.com/onemindos/ONEMINDOS/pull/37) |
| CORE-NET-9 | Lima lab NT-1…NT-8, NT-17 | in-progress: mesh-across-NAT lab PASS in #37 (T0–T5); NT-1…NT-8, NT-17 not recorded yet | `feat/core-net` | [#37](https://github.com/onemindos/ONEMINDOS/pull/37) |
| CORE-NET-10 | Contract §12.16 networking PR | todo | – | – |
| CORE-NET-11 | Installer and image wiring | todo | – | – |
| CORE-NET-12 | Gateway + onemindd registration; join bundle `mesh` | todo | – | – |
| CORE-NET-13 | Dashboard Network page, Add a device, app links | todo | – | – |
| CORE-NET-14 | Pi budget, throughput and phone matrix on hardware | blocked: founder (F-25 hardware) | – | – |
| CORE-NET-15 | Public app exposure through the relay | parked | – | – |
| DEV-CLI-8 | `fabric qr/join/leave/remove` and `node join` alias | todo | – | – |
| CORE-BACKUP-1 | `onemind-local` Retain StorageClass as default | todo | – | – |
| CORE-BACKUP-2 | `internal/backup` agent: restic, schedule, three keys, emergency kit | in-progress: agent merged in #32; onemindd wiring, heartbeat and image pins pending (BACKUP-WIRE-1) | `feat/onemindd-backup` | [#32](https://github.com/onemindos/ONEMINDOS/pull/32) |
| CORE-BACKUP-3 | k3s datastore online backup with integrity gate | in-progress: k3s `state.db` online backup with integrity check merged in #32, not wired | `feat/onemindd-backup` | [#32](https://github.com/onemindos/ONEMINDOS/pull/32) |
| CORE-BACKUP-4 | Destinations: USB, another OneMind box (append-only), S3 | in-progress: `usb`, `node`, `s3` targets merged in #32, not wired; append-only rest-server unit pending | `feat/onemindd-backup` | [#32](https://github.com/onemindos/ONEMINDOS/pull/32) |
| CORE-BACKUP-5 | Manifest `backup:` hooks | todo | – | – |
| CORE-BACKUP-6 | Restore file, app or box, approval-gated; restore at onboarding | todo | – | – |
| CORE-BACKUP-7 | Verified-restore badge (daily check, weekly scratch restore) | in-progress: `VerifyRestore` and badge rules merged in #32; schedule not wired, no alert yet | `feat/onemindd-backup` | [#32](https://github.com/onemindos/ONEMINDOS/pull/32) |
| CORE-NOTIFY-1 | Alert record and store, `/v1/alerts`, NATS subjects, in-app inbox | in-progress | `feat/notify-monitor` (local) | – |
| DEV-API-12 | Notifications route shapes | in-progress (built inside CORE-NOTIFY-1) | `feat/notify-monitor` (local) | – |
| CORE-BACKUP-8 | Backups API, screen and alerts | todo (built inside BACKUP-WIRE-1) | – | – |
| DEV-API-11 | Backups and restores route shapes | todo | built inside CORE-BACKUP-8 | – |
| DEV-CLI-7 | `backup status/list/now/verify` and `restore` | todo | – | – |
| CORE-NOTIFY-2 | Sources: approvals, nodes, updates, backups, scans, audit (H-28) | in-progress: all sources but the audit-chain check (H-28) | `feat/notify-monitor` (local) | – |
| CORE-NOTIFY-3 | Web Push and Android UnifiedPush via the box's ntfy; push registrat… | in-progress: gateway side (VAPID, RFC 8291, registrations); browser and phone sides open | `feat/notify-monitor` (local) | – |
| CORE-NOTIFY-4 | iOS APNs relay | todo | – | – |
| CORE-NOTIFY-5 | Repairs with fix actions | todo (alert `fix` → request already works on `feat/notify-monitor`) | – | – |
| CORE-NOTIFY-6 | Email, webhook, Matrix, Telegram channels; routing and quiet hours | in-progress: email, webhook, ntfy, routing, quiet hours, digest; Matrix and Telegram open | `feat/notify-monitor` (local) | – |
| CORE-UPDATE-3 | Updates screen and "What's new" | todo | – | – |
| CORE-UPDATE-5 | App updates through approval (catalog diff, `app.update`) | todo | – | – |
| CORE-UPDATE-6 | Health-gated app updates with snapshot and revert | todo | – | – |
| CORE-UPDATE-7 | Offline grace and USB/LAN mirror installs | todo | – | – |
| CORE-UPDATE-8 | Rescue console in onemindd | todo | – | – |
| CORE-DASH-2 | Move the 5 existing screens onto `@onemind/ui` | in-progress: dashboard v2 on `@onemind/ui` (Home, Market, Installed, Approvals, Activity, Nodes, Settings) | `feat/dashboard-v2` (local) | – |
| CORE-DASH-5 | Alerts, Updates and Backups screens | todo | – | – |
| CORE-DASH-7 | PWA and per-app subdomain launcher | todo (the PWA slice is PU-31) | – | – |
| CORE-DASH-8 | Typed widgets on Home; "show the equivalent call" toggle | todo | – | – |
| DEV-SDK-4 | Dashboard and mobile moved onto `@onemind/sdk` | todo | – | – |
| DEV-SDK-7 | SSE in all three SDKs, polling fallback, React Native transport | in-progress | `feat/devsurface` (local) | – |
| CORE-MOBILE-1 | Shell on the generated `sdk/ts`; icon and splash | todo | – | – |
| CORE-MOBILE-2 | QR pairing with CA pinning, HTTPS only | todo | – | – |
| CORE-MOBILE-3 | Passkey sign-in and signed approvals; plan card | todo | – | – |
| CORE-MOBILE-4 | Android UnifiedPush | todo | – | – |
| CORE-MOBILE-5 | iOS service extension and relay registration (with NOTIFY-4) | todo | – | – |
| CORE-MOBILE-6 | Alerts and Activity tabs, offline cache, checkpoint store | todo | – | – |
| CORE-NOTIFY-7 | Actionable notifications open the approval card | todo | – | – |
| DEV-MCP-3 | Request-only writes: `withdraw_request`, `preview_action`, `plan_sh… | todo | – | – |
| DEV-MCP-6 | MCP audit entries, read summaries, trace context, audit tools | in-progress | `feat/devsurface` (local) | – |
| DEV-MCP-8 | Conformance CI with official TS, Python, Go clients and the bridge | in-progress | `feat/devsurface` (local) | – |
| DEV-MCP-9 | MCP revision 2025-11-25 and the `versions.py` adapter split | todo | – | – |
| DEV-MCP-11 | Prompts, `onemind://docs`, `llms.txt`, `search_docs`, status tools | todo | – | – |
| CORE-WEB-2 | Generated references: CLI, API, schema, errors | todo | – | – |
| CORE-WEB-3 | Apps catalog with scan history | todo | – | – |
| PLAN-E10 | Pi 5 image (G2): RAUC + tryboot, signed image, wizard | todo (board image is IMG-2 on `feat/image-line`; hardware run needs F-25) | – | – |

### S3: automation, plugin SDK v0, website launch, dogfood migration (weeks 9–13)

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| C12-C | Contract §12-c: deployments, manifest `health`, `settings`, `secret… | done (§12.18) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| C12-F | Contract §12-f: automation | done (§12.17) | `contract/s12` | [#39](https://github.com/onemindos/ONEMINDOS/pull/39) |
| C12-PLG | Contract plugins amendment: `kind: plugin`, `plugin.invoke`, `plugi… | todo | – | – |
| CORE-AUTO-2 | Scheduler and event/webhook triggers that create actions | in-progress: schedule and event rules built; webhook triggers and the JetStream consumer not yet | `feat/automation` (local) | – |
| CORE-AUTO-3 | Standing approvals with ledger-counted limits | in-progress: built with windows, F-6 and the kill switch; passkey step-up waits for identity | `feat/automation` (local) | – |
| CORE-AUTO-4 | Dry run, CLI (`auto`, `policy`) and Automations page | in-progress: dry run and enable gate built; CLI and page not yet | `feat/automation` (local) | – |
| CORE-AUTO-5 | Failure and recovery notifications, repairs hook-up | in-progress: breaker publishes `automation.breaker.opened`; notification routing not yet | `feat/automation` (local) | – |
| DEV-API-13 | Automation and OS update route shapes | in-progress (automation routes of §12.17; built inside CORE-AUTO-2, CORE-UPDATE-2) | `feat/automation` (local) | – |
| DEV-CLI-9 | `notify test`, `tokens list/create/revoke`, `rules` alias | todo | – | – |
| CORE-DASH-6 | Settings (sessions, tokens, pairing) and Automations screens | todo | – | – |
| CORE-DEPLOY-1 | `onemind deploy` (kustomize, Helm, Compose) → private app | todo | – | – |
| CORE-DEPLOY-2 | On-box scan Job bound to digests | todo | – | – |
| CORE-DEPLOY-3 | Revisions, history and rollback | todo | – | – |
| CORE-DEPLOY-4 | Write-only secrets | todo | – | – |
| CORE-DEPLOY-5 | Watched Git source with a diff card | todo | – | – |
| CORE-DEPLOY-6 | Migration kit (`onemind migrate check/import/pin`) | todo | – | – |
| DEV-CLI-10 | `app scaffold/validate/gate/dev`, one validator shared with Python | todo | – | – |
| DEV-PLG-1 | Manifest `extensions`, `permissions`, `plugin`, `compat` + Go valid… | todo | – | – |
| DEV-PLG-2 | TypeScript `@onemind/plugin` (server and widget) | todo | – | – |
| DEV-PLG-3 | Gateway plugin registry, `kind: plugin` principal, `/v1/plugins/*` | todo | – | – |
| DEV-PLG-4 | Tool projection to `/mcp` and the CLI | todo | – | – |
| DEV-PLG-5 | Widget host: typed templates, sandboxed iframe, postMessage bridge… | todo | – | – |
| DEV-PLG-6 | Settings panel (JSON Schema form) and secrets API | todo | – | – |
| DEV-PLG-7 | OCI pack, private-tier signing, install by digest, `plugin verify` | todo | – | – |
| DEV-PLG-8 | `onemind plugin dev` (mock hub, harness, hot reload) and `init` tem… | todo | – | – |
| DEV-PLG-9 | Revocation list client (phase 1); TUF delegation and countersignatu… | todo | – | – |
| DEV-CLI-11 | `plugin init/dev/pack/publish` acceptance | todo | built inside DEV-PLG-7, -8, -14 | – |
| CORE-UPDATE-9 | Fleet-staged updates | todo | – | – |
| CORE-FABRIC-6 | Read-only fleet view | todo | – | – |
| CORE-MOBILE-7 | Store releases (TestFlight, Play internal → public) with privacy la… | todo | – | – |
| DEV-SDK-9 | Publish to npm, PyPI and the Go proxy with trusted publishing and p… | todo | – | – |
| DEV-SDK-10 | API reference and quickstarts on the website | todo | – | – |
| CORE-WEB-4 | GitHub Discussions and giscus (click-to-load) | todo | – | – |
| CORE-WEB-5 | Blog and launch posts L1/L2/L3 | todo | – | – |
| CORE-DOGFOOD-1 | `onemind doctor --wave N` gate checker | todo | – | – |
| CORE-DOGFOOD-2 | Migration fixtures and docs | todo | – | – |
| CORE-DOGFOOD-3 | Remote access app and exposure review | todo | – | – |
| CORE-DOGFOOD-4 | Per-app metrics and logs; metrics stack as a Market app | todo | – | – |
| CORE-DOGFOOD-5 | GPU enablement (toolkit, device plugin, placement) | todo | – | – |
| CORE-DOGFOOD-6 | Run migration waves 0–5; log gaps against the owning spec | todo | – | – |
| PLAN-E11 | Jetson and platform floor (G3) | todo (board image is IMG-3 on `feat/image-line`; hardware run needs F-25) | – | – |

### S4+: phase 2 and parked

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| DEV-PLG-10 | Gateway-mediated plugin events, alerts with actions, automation tri… | todo | – | – |
| DEV-PLG-11 | Plugin data volume and backup hooks | todo | – | – |
| DEV-PLG-12 | Scan gate for plugin artifacts | todo | – | – |
| DEV-PLG-13 | Testing harness (TS, Python, Go) and `onemind plugin test` | todo | – | – |
| DEV-PLG-14 | Publish from CI (OIDC), public plugin index, review checklist, Mark… | todo | – | – |
| DEV-PLG-15 | Mobile plugin cards (typed templates, native) | todo | – | – |
| DEV-PLG-16 | Plugin docs: tutorial, reference, bridge spec, also over MCP | todo | – | – |
| DEV-MCP-10 | MCP revision 2026-07-28: discover, stateless calls, tasks for appro… | todo | – | – |
| DEV-MCP-12 | OAuth façade: RFC 9728 metadata, audience-bound tokens, browser log… | todo | – | – |
| CORE-WEB-6 | Self-host the site on OneMind; Discourse forum | todo | – | – |
| PH2-DESKTOP | Desktop shell and module host (research 12, D-003) | parked | – | – |
| PLAN-E7-LAB | Typed capabilities and actuation behind the lab flag | parked | – | – |
| PLAN-E14 | TAK field kit preview | parked | – | – |
| PLAN-E15 | Robot in simulation | parked | – | – |
| DEV-API-14 | Superseded by DEV-SDK-1…10 | superseded | – | – |

### Added 2026-11-12: streams and epics that were missing from the board

Every stream that was running without a row, every merged PR that had no row, and the gaps found in merged work. Order, size, dependencies, owner paths and acceptance: [BACKLOG.md](BACKLOG.md#added-2026-11-12-streams-and-epics-missing-from-the-board). "Started, no commits yet" means the stream's worktree exists at `main` with nothing committed.

#### Merged work that had no row

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| CORE-PLUMB | Core plumbing: router registry, per-feature tables and upgrade steps, settings sections, `publish_event`, CLI and onemindd registries | done | `feat/core-plumbing` | [#38](https://github.com/onemindos/ONEMINDOS/pull/38) |
| UMB-STUDY | umbrelOS 2 deep dive (10 areas) and the UMB backlog | done | `feat/umbrel2-study` | [#30](https://github.com/onemindos/ONEMINDOS/pull/30) |
| BRAND-0 | OneMind logo: transparent SVG and PNG, 4 variants | done | `brand/onemind-logo-signed` | [#36](https://github.com/onemindos/ONEMINDOS/pull/36) |

#### Image line

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| IMG-1 | OneMind baked into the OS image (onemindd, NATS, gateway, dashboard) and first boot into OneMind; QEMU battery F0–F4 | in-progress | `feat/image-line` (local) | – |
| IMG-2 | Raspberry Pi 5 board image (feeds PLAN-E10) | in-progress (uncommitted in the worktree) | `feat/image-line` (local) | – |
| IMG-3 | Jetson Orin board image on NVIDIA L4T (feeds PLAN-E11) | in-progress (uncommitted in the worktree) | `feat/image-line` (local) | – |
| IMG-4 | USB installer for x86_64; criteria I1–I5 pre-registered | in-progress (criteria committed; installer uncommitted) | `feat/image-line` (local) | – |
| IMG-5 | Cloud images: generic, AWS, Azure, GCP, Hetzner, Proxmox; criteria C0–C6 pre-registered | in-progress (criteria committed; boards uncommitted) | `feat/image-line` (local) | – |
| IMG-6 | Releases and downloads: signed images with checksums on GitHub Releases, downloads page | todo | – | – |

#### Brand

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| BRAND-1 | One brand source: `brand.json` and `brand-sync`; ui, dashboard and site take name, logo, favicon, manifest and accent from it; CI drift check | in-progress | `feat/brand-single-source` (local) | – |
| MOBILE-V1-1 | Phone app restyle from `brand.json`: icon, splash, colours, logo | todo | – | – |

#### Testing and quality

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| E2E-GOLDEN | Golden-path e2e: `install.sh` hub in a VM (Lima, QEMU/KVM), Playwright dashboard + MCP agent + audit, `verify.sh`; `e2e.yml` on PRs and nightly (green in Lima 2026-11-12) | in-progress (being integrated) | `feat/e2e-golden-path` (local) | – |
| TEST-REG-1 | Test register, results log, test-result issue form and `test-all` workflow | in-progress | `test/register` (local) | – |
| TEST-SEC-1 | Security test suite against the threat model's attack paths | in-progress (started, no commits yet) | `feat/test-security` (local) | – |
| TEST-PROP-1 | Property-based and fuzz tests | in-progress (started, no commits yet) | `feat/test-property-fuzz` (local) | – |
| TEST-CI-1 | CI test matrix: browsers with axe and visual checks, every app on amd64 and arm64, mobile builds, site links | in-review | `feat/test-ci-matrix` | [#42](https://github.com/onemindos/ONEMINDOS/pull/42) |
| QUAL-SLOP-1 | Slop audit: unverified claims, filler, stale or duplicated text, ranked with file:line | in-progress (started, no commits yet) | `docs/slop-audit` (local) | – |
| QUAL-SLOP-2 | Slop fixer: apply the audit's fixes | todo | `docs/slop-audit` | – |

#### Market, apps and app lifecycle

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| MKT-BATCH-1 | Market batch 1: Nextcloud, Immich, Syncthing, Paperless-ngx, Gitea, Grafana, Ollama, LibreChat, SearXNG, AdGuard Home | in-progress (10 apps committed) | `feat/market-batch-1` (local) | – |
| MKT-BATCH-2-3 | Market batches 2 and 3 (next 20 from CANDIDATES.md) | in-progress (started, no commits yet) | `feat/market-batch-2-3` (local) | – |
| MKT-BATCH-4 | Market batch 4 | todo | – | – |
| MKT-BATCH-5 | Market batch 5 | todo | – | – |
| CORE-SECRETS-1 | Owner-entered app secrets: the dashboard asks for them (for example the Hermes model key), the box stores them encrypted | todo | – | – |
| DB-SHARED-1 | Shared PostgreSQL for apps: one database and role per app | todo | – | – |
| APP-OVERRIDE-1 | Owner override for an app the scan blocked (F-7) | blocked: founder (F-7) | – | – |

App lifecycle (APP-LIFE-1…5, umbrel parity PD-03…07) maps onto existing rows; see the alias table below. Its stream `feat/app-lifecycle` has no branch yet (2026-11-12).

#### Core gaps found in merged work

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| BACKUP-WIRE-1 | Wire `internal/backup` (#32) into onemindd, heartbeat, updater and image pins, then the gateway backups router and the Backups screen (delivers CORE-BACKUP-8) | todo | – | – |
| STORAGE-ACT-1 | Mirror create, add disk and replace disk as approved `storage.*` actions on #31's dry-run plans (first slice of UMB-STOR-4, -5) | todo | – | – |
| PHOTOS-SRV-1 | Box side of the phone photo backup (#34): built-in (UMB-PHOTO-1…3) or Immich (UMB-PHOTO-13) | blocked: founder (Immich vs built-in, with F-47) | – | – |
| CORE-MON-1 | Monitoring: app health, restarts, logs, app and node metrics, thresholds (contract §12.15) | in-progress | `feat/notify-monitor` (local) | – |
| DOGFOOD-MIGRATE-1 | Import from an existing Kubernetes cluster: workloads, config and volumes, read-only on the source, then cut over | todo | – | – |

#### Developer surface and website

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| DEV-PLG-0 | Plugin SDK v0: first runnable slice ahead of DEV-PLG-1…8 | in-progress (started, no commits yet) | `feat/plugin-sdk-v0` (local) | – |
| CORE-WEB-G | Website user guides for owners | in-progress (started, no commits yet) | `docs/site-user-guides` (local) | – |

#### Deploy kit parts of PR #27 to port onto `main`

[#27](https://github.com/onemindos/ONEMINDOS/pull/27) is open and overlaps #26, which merged. These are its parts worth keeping; close #27 once they land.

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| DEPLOY-PORT27-1 | `deploy/bundle.sh` and `install.sh --bundle` (offline bundle checked against `SHA256SUMS`) | todo | – | – |
| DEPLOY-PORT27-2 | `install.sh --target debian13\|rpi5\|jetson\|do` and `--dry-run`; Pi 5 memory cgroup; DigitalOcean firewall reminder | todo | – | – |
| DEPLOY-PORT27-3 | Hashed tokens throughout: join, owner and agent tokens printed once, only sha256 on disk (`main` already hashes the owner token) | todo | – | – |
| DEPLOY-PORT27-4 | NATS token auth for nodes on the developer install (step before nkeys, CORE-SEC-4) | todo | – | – |
| DEPLOY-PORT27-5 | `node-check.sh` and `natscheck.py` | todo | – | – |
| DEPLOY-PORT27-6 | Mock gateway for the `verify.sh` tests and the e2e-systemd harness | todo | – | – |
| DEPLOY-PORT27-7 | Simulated rpi5 and jetson-orin nodes in the compose dev hub | todo | – | – |

#### UI parity (from [`docs/strategy/umbrel-parity.md`](../strategy/umbrel-parity.md))

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| PU-31 | PWA: manifest, icons, accent theme colour, installable over HTTPS, labelled offline "last known" view (first slice of CORE-DASH-7) | todo | – | – |
| PU-09 | Login UI: passkey sign-in, TOTP fallback, first-run owner setup (UI side of CORE-SEC-2) | todo | – | – |
| PU-20 | i18n scaffolding: string catalog and locale switch | todo | – | – |

#### Founder blockers

Decisions only the founder can take; each blocks the rows listed. Details and defaults: [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md).

| Id | Title | State | Blocks | PR |
|---|---|---|---|---|
| F-25 | Day-1 hardware: Pi 5 16 GB + NVMe, a 4 GB Pi 5 for the soak, Jetson Orin Nano Super; the Pi soak must start by 2026-12-11 | blocked: founder | CORE-UPDATE-4, CORE-NET-14, PLAN-E10, PLAN-E11, hardware runs of IMG-2, IMG-3 | – |
| F-27 | OS security channel: offline TUF root ceremony and signing secrets | blocked: founder | OS-SECPIPE publishing, CORE-SEC-8, IMG-6 | – |
| F-7 | Owner override for an install that failed a scan | blocked: founder | APP-OVERRIDE-1 | – |
| F-5 | Website domain and host | blocked: founder | CORE-WEB-1, CORE-WEB-4, the IMG-6 downloads page | – |

#### Stream ids that map onto existing rows

These ids are used by streams or plans for work that already has a row. They get no second row: the existing row carries the state and is what the counts include.

| Stream id | What | Existing row(s) | State there | Branch |
|---|---|---|---|---|
| MKT-B1, MKT-B23, MKT-B4, MKT-B5 | Market batches | MKT-BATCH-1, MKT-BATCH-2-3, MKT-BATCH-4, MKT-BATCH-5 (ids used on the branches) | in-progress, in-progress, todo, todo | as above |
| SEC-P0 | Security P0 (PR #40) | CORE-SANDBOX-1…5, CORE-SEC-9, the k3s part of CORE-SEC-5 | in-review | `feat/sec-p0` |
| APP-LIFE-1 (PD-03) | Lifecycle actions start, stop, restart, update, configure, delete data, with progress | UMB-APP-4 | todo | `feat/app-lifecycle` (no branch yet) |
| APP-LIFE-2 (PD-04) | Install plan endpoint | UMB-APP-3 | todo | `feat/app-lifecycle` (no branch yet) |
| APP-LIFE-3 (PD-05) | Health-gated app updates with release notes and revert | CORE-UPDATE-5, CORE-UPDATE-6 | todo | `feat/app-lifecycle` (no branch yet) |
| APP-LIFE-4 (PD-06) | Remove keeps data; separate data delete | UMB-APP-5 | todo | `feat/app-lifecycle` (no branch yet) |
| APP-LIFE-5 (PD-07) | Generated credentials, sealed, owner-only reveal | CORE-DEPLOY-4 (includes UMB-APP-11) | todo | `feat/app-lifecycle` (no branch yet) |
| MOBILE-V1-2 | Phone identity: pairing, passkeys, household sign-in | CORE-MOBILE-2, CORE-MOBILE-3, UMB-ACCT-11 | todo | – |
| MOBILE-V1-3 | Phone push | CORE-MOBILE-4, CORE-MOBILE-5 (with CORE-NOTIFY-3, -4) | todo (gateway side of NOTIFY-3 in progress) | – |
| MOBILE-V1-4 | Phone notifications and activity | CORE-MOBILE-6, CORE-NOTIFY-7 | todo | – |
| NET-P2-1 | Networking Part 2: contract §12.16 | CORE-NET-10 | todo | – |
| NET-P2-2 | Networking Part 2: installer and image wiring | CORE-NET-11 | todo | – |
| NET-P2-3 | Networking Part 2: gateway and onemindd registration, join bundle `mesh` | CORE-NET-12 and the rest of CORE-NET-8 | todo | – |
| NET-P2-4 | Networking Part 2: Network page, Add a device | CORE-NET-13 | todo | – |
| FILES-1, FILES-2, FILES-4, FILES-6 | Ids used on the files branch | UMB-FILES-1, -2, -4, -6 | in-progress (FILES-4 todo) | `feat/files` (local) |
| STORAGE-LUKS-1 (H-11) | LUKS2 data partition from first boot, recovery key shown once | CORE-SEC-5 (LUKS part, includes UMB-STOR-1) | todo | – |
| DESKTOP-FILES-1 | Desktop mounts the box's files over SMB or WebDAV | UMB-CLIENT-9 (adds WebDAV), server side UMB-FILES-5 | todo | – |

### UMB: umbrelOS 2 study epics

From [`docs/umbrel2/`](../umbrel2/README.md). Order and acceptance in [BACKLOG.md](BACKLOG.md#umb-umbrelos-2-study-epics); study epics merged into existing rows are listed there and have no row here. 116 rows: 2 in-review (#33, #34), 5 in-progress (UMB-STOR-3 and UMB-FILES-7 partly merged; UMB-FILES-1, -2, -6 on `feat/files`), 109 todo. UMB-MACH rows wait on founder decision F-57.

#### UMB in S1

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| UMB-STOR-0 | Contract: storage reads, storage.* action types, heartbeat storag… | todo | – | – |
| UMB-STOR-3 | onemindd storage inventory and health collector (lsblk, smartctl, nv… | in-progress: inventory, SMART, btrfs mirror status and dry-run plans merged in #31; onemindd wiring and heartbeat `storage` pending | `feat/onemindd-storage` | [#31](https://github.com/onemindos/ONEMINDOS/pull/31) |
| UMB-FILES-0 | Contract 12-files: roots, file API, action types, MCP tools, manifes… | todo | – | – |
| UMB-ACCT-1 | Kanidm spike: host service, offline first boot, groups, OIDC client,… | todo | – | – |
| UMB-ACCT-2 | Contract: role child, access:* and sessions:self scopes, acce… | todo | – | – |
| UMB-ACCT-13 | Lab: passkey across LAN and mesh names; hybrid sign-in from a TV bro… | todo | – | – |
| UMB-AGT-1 | Contract: agents, pairings, new request types, request_access, tr… | todo | – | – |
| UMB-AGT-3 | Agent pairing (device-code shape): `/v1/agent-pairings*`, limits, pa… | todo | – | – |
| UMB-AGT-4 | Persistent MCP client identity, capped agent_clients, agent.ident… | todo | – | – |
| UMB-APP-0 | Contract: app lifecycle action types, /v1/apps/{id} detail, /plan… | todo | – | – |
| UMB-APP-2 | Signed catalog: CI builds `catalog.json` with a cosign signature; ga… | todo | – | – |
| UMB-APP-12 | Logs endpoint, redacted | todo | – | – |
| UMB-APP-3 | Plan endpoint with dependency resolution, alternatives and dependant… | todo | – | – |
| UMB-APP-18 | Schema: tagline, category, tags, developer, gallery, rela… | todo | – | – |
| UMB-CLIENT-0 | Contract 12-clients: discovery, devices, photo sources, shares, even… | todo | – | – |
| UMB-CLIENT-1 | Discovery: `_onemind._tcp` advert and `GET /v1/discovery` with the C… | todo | – | – |
| UMB-CLIENT-3 | Client kit (TypeScript and Rust) with shared test vectors | todo | – | – |
| UMB-PHOTO-0 | Photos licence rows and contract §12-p | todo | – | – |
| UMB-DESK-0 | Contract: `/v1/me/home`, `/v1/wallpapers`, shortcut preview, widget… | todo | – | – |
| UMB-DESK-1 | Home document store and routes (per person, ETag) | todo | – | – |
| UMB-DESK-7 | `Sheet`, `ImmersiveDialog`, `TargetPicker` | todo | – | – |
| UMB-SYS-13 | Yank a published OS release | todo | – | – |

#### UMB in S2

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| UMB-CLIENT-2 | Device registry, `device.add` action, DPoP tokens, revoke | todo | – | – |
| UMB-STOR-2 | Initrd assembly and recovery mode markers | todo | – | – |
| UMB-STOR-4 | Storage operation engine: protect, add, replace, remove, scrub, sepa… | todo | – | – |
| UMB-STOR-5 | Gateway storage API and action executor | todo | – | – |
| UMB-STOR-6 | Scrub scheduler and health alerts | todo | – | – |
| UMB-STOR-7 | App snapshots: one subvolume per PV, snapshot before app and OS upda… | todo | – | – |
| UMB-STOR-8 | Storage page, disk detail, protect flow, recovery screen, node-card… | todo | – | – |
| UMB-STOR-9 | Storage CLI and MCP tools | todo | – | – |
| UMB-STOR-13 | External USB disks: auto-mount by filesystem UUID as `usb:<uuid>` ro… | todo | – | – |
| UMB-FILES-1 | Node file server: confined operations, trash, resumable (tus) upload… | in-progress: tus uploads and confined paths in the gateway (branch id FILES-1); node file server todo | `feat/files` (local) | – |
| UMB-FILES-2 | Gateway file API, roots, shares; data plane vs action split | in-progress: Home/Shared spaces, browse, preview, ranged downloads, moves, trash, quotas (FILES-2) | `feat/files` (local) | – |
| UMB-FILES-3 | File index, search, thumbnails and previews in a sandbox | todo | – | – |
| UMB-FILES-4 | Files page (list, grid, upload queue, preview, search, trash) | todo | – | – |
| UMB-FILES-6 | Folder grants for apps and agents | in-progress: folder grants behind owner approval (FILES-6); executor mount hook and MCP tools todo | `feat/files` (local) | – |
| UMB-FILES-7 | Rewind: restore points per path, `files.restore` with undo | in-progress: agent-side Rewind browse and restore merged in #32; routes and screen todo | `feat/onemindd-backup` | [#32](https://github.com/onemindos/ONEMINDOS/pull/32) |
| UMB-PHOTO-1 | Photos service skeleton and catalog | todo | – | – |
| UMB-PHOTO-2 | Photo ingest and indexer | todo | – | – |
| UMB-PHOTO-3 | Photo backup protocol server, receipts with digest check (includes U… | todo | – | – |
| UMB-PHOTO-4 | Phone photo backup, iOS and Android (includes UMB-CLIENT-6, -7, UMB-… | in-review (box side waits on PHOTOS-SRV-1) | `feat/mobile-photos` | [#34](https://github.com/onemindos/ONEMINDOS/pull/34) |
| UMB-PHOTO-5 | Dashboard Photos (timeline, viewer, albums, favourites, Trash) | todo | – | – |
| UMB-PHOTO-8 | Photos storage safety and backups (includes UMB-CLIENT-5) | todo | – | – |
| UMB-ACCT-4 | People API: `/v1/users`, enrolment links, disable, tombstoned delete… | todo | – | – |
| UMB-ACCT-5 | App access and forward-auth policy | todo | – | – |
| UMB-ACCT-6 | OIDC clients for apps at install; header mapping for header apps | todo | – | – |
| UMB-ACCT-7 | Child policy and access requests | todo | – | – |
| UMB-ACCT-8 | CLI groups `users`, `access`, `sessions` | todo | – | – |
| UMB-ACCT-9 | MCP tools for people and access requests | todo | – | – |
| UMB-ACCT-10 | Dashboard: sign-in, first boot, People, Access card, child Home, My… | todo | – | – |
| UMB-ACCT-11 | Phone: OIDC sign-in in the system browser, secure refresh token, chi… | todo | – | – |
| UMB-ACCT-12 | Identity in backups and restore | todo | – | – |
| UMB-APP-1 | App gate computes install size, archs, release notes, gallery checks | todo | – | – |
| UMB-APP-4 | Lifecycle actions start, stop, restart, update, configure with progr… | todo | – | – |
| UMB-APP-5 | Remove keeps data; separate owner-only data delete with typed confir… | todo | – | – |
| UMB-APP-9 | Host ports with conflict check in the plan; avahi name per app | todo | – | – |
| UMB-APP-13 | App page and Market polish: facts band, permissions, notes, related… | todo | – | – |
| UMB-AGT-5 | `onemind mcp pair` and `onemind mcp setup <client>`; keychain; confi… | todo | – | – |
| UMB-AGT-6 | Troubleshooting tools: app status and logs, node logs, system health… | todo | – | – |
| UMB-AGT-10 | Agents page, Connect wizard, pairing card, agent activity, "Agent at… | todo | – | – |
| UMB-AGT-9 | `request_access` deep links and the access landing | todo | – | – |
| UMB-AGT-11 | Agent tokens wiped on restore; conformance for pairing and new tools | todo | – | – |
| UMB-CLIENT-8 | Desktop app v1 (Tauri): tray, discovery, pairing, status, open in br… | in-review | `feat/desktop-client` | [#33](https://github.com/onemindos/ONEMINDOS/pull/33) |
| UMB-CLIENT-10 | Desktop approvals, alerts and events | todo | – | – |
| UMB-CLIENT-13 | MCP read tools `list_devices`, `photo_backup_status` | todo | – | – |
| UMB-CLIENT-14 | Dashboard Devices page | todo | – | – |
| UMB-DESK-6 | Jobs tray bound to `action.progress` | todo | – | – |
| UMB-DESK-9 | Home and Edit Home wired to the hub | todo | – | – |
| UMB-DESK-10 | Shortcuts with a fenced icon fetch | todo | – | – |
| UMB-DESK-11 | Welcome tips on a new Home | todo | – | – |
| UMB-DESK-16 | Rendered accessibility and performance gate for Home | todo | – | – |
| UMB-SYS-6 | Wi-Fi and static IP with automatic revert | todo | – | – |
| UMB-SYS-8 | Factory reset as a critical action | todo | – | – |
| UMB-SYS-10 | Restart and shut down a node | todo | – | – |
| UMB-MACH-1 | Machines lab kit and feasibility (LT-MACH-1…3) | todo | – | – |

#### UMB in S3

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| UMB-STOR-10 | Raspberry Pi 5 storage lab: dual-NVMe and NVMe + USB mirror, power-c… | todo | – | – |
| UMB-STOR-12 | Decision: HDD + SSD acceleration and a ZFS "NAS tier" licence review | todo | – | – |
| UMB-STOR-14 | NAS mounts in: SMB with mDNS discovery and NFS; credentials sealed | todo | – | – |
| UMB-FILES-5 | SMB and WebDAV out, per-person and per-device users (includes UMB-CL… | todo | – | – |
| UMB-FILES-8 | Cloud import with rclone: Google Drive, Dropbox, OneDrive, WebDAV; i… | todo | – | – |
| UMB-FILES-9 | Cloud account as a backup target (restic `rclone:` backend; extends… | todo | – | – |
| UMB-FILES-10 | Migrate files in from a NAS, old server or another self-hosted OS | todo | – | – |
| UMB-PHOTO-6 | Household photo sharing | todo | – | – |
| UMB-PHOTO-7 | Map and places, offline | todo | – | – |
| UMB-PHOTO-9 | Photos MCP tools and request-only actions | todo | – | – |
| UMB-PHOTO-10 | Photos CLI | todo | – | – |
| UMB-PHOTO-11 | Importers: USB and SD card, folder, Google Takeout, iCloud Photos ex… | todo | – | – |
| UMB-PHOTO-13 | Immich Market app with read-only attach to the OneMind library | todo | – | – |
| UMB-APP-10 | Community sources pinned to a commit, `source.*` actions, on-box sca… | todo | – | – |
| UMB-APP-14 | CLI `onemind app` lifecycle verbs and `onemind source` (extends DEV-… | todo | – | – |
| UMB-APP-17 | Image cleanup on nodes after update and remove | todo | – | – |
| UMB-AGT-8 | Files read tools and `files.apply_plan` with snapshot and Undo | todo | – | – |
| UMB-CLIENT-9 | Desktop mounts of SMB shares with per-device credentials | todo | – | – |
| UMB-CLIENT-11 | Laptop folder backup with restic to the box (includes UMB-PHOTO-14) | todo | – | – |
| UMB-CLIENT-12 | Desktop release: signing, notarization, MSIX, DMG, AppImage, signed… | todo | – | – |
| UMB-DESK-12 | Live usage across fleet, node and app (includes UMB-SYS-5) | todo | – | – |
| UMB-DESK-13 | CLI `onemind home` and `onemind usage` | todo | – | – |
| UMB-DESK-14 | MCP `get_usage` and `home.change` requests | todo | – | – |
| UMB-MACH-0 | Contract: machine routes, scopes, action types, events | todo | – | – |
| UMB-MACH-2 | KubeVirt + CDI as a signed OS extension; `kvm` and `iommu` capabilit… | todo | – | – |
| UMB-MACH-3 | Gateway machines module: records, render, executor hook, health gate | todo | – | – |
| UMB-MACH-4 | Console broker and dashboard console (noVNC) | todo | – | – |
| UMB-MACH-5 | Machine template catalog and image import or upload | todo | – | – |
| UMB-MACH-13 | Machines dashboard: list, wizard, plan card, settings, Home tile | todo | – | – |

#### UMB in S4+

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| UMB-PHOTO-12 | Opt-in semantic search and face grouping on the box | todo | – | – |
| UMB-CLIENT-15 | macOS File Provider and Windows Cloud Files instead of SMB | todo | – | – |
| UMB-MACH-6 | Windows guests: TPM, secure boot, own answer-file generator, virtio… | todo | – | – |
| UMB-MACH-7 | Machine networking: NAT with forwards, NetworkPolicy, wired LAN bridge | todo | – | – |
| UMB-MACH-8 | USB passthrough (applied on restart) | todo | – | – |
| UMB-MACH-9 | GPU passthrough (VFIO) on the Pro box | todo | – | – |
| UMB-MACH-10 | Machine backups with guest freeze and a restore that boots | todo | – | – |
| UMB-MACH-11 | MCP machine tools and the agent control lease | todo | – | – |
| UMB-MACH-12 | Machine quotas and sharing for the household | todo | – | – |
| UMB-MACH-14 | Machine desktop extras: clipboard, sound, virgl, touch console | todo | – | – |
| UMB-MACH-15 | CLI `onemind machines` | todo | – | – |
| UMB-MACH-16 | Android template (Linux guest + Waydroid, own provisioning) | todo | – | – |

## How to update this page

- Starting a stream: add or claim its row the same day (board rule at the top), with the branch name, even before the first commit.
- Claiming an epic: open a draft PR titled with the epic id; you may set the row to `in-progress` with the branch name in that PR.
- When the PR opens for review: `in-review` and the PR link.
- When it merges: `done`. The same PR adds a CHANGELOG entry.
- Re-check against reality with `gh pr list -R onemindos/ONEMINDOS --state all` and `git log --first-parent main`. Recount the Summary from the rows (every table under "Every epic" except the alias table).
