<!-- SPDX-License-Identifier: Apache-2.0 -->
# Leap status tracker

**Last updated:** 2026-11-12 (from `git log`, the worktrees and `gh pr list`). Part of [the leap](README.md). Order and acceptance: [BACKLOG.md](BACKLOG.md). How to claim an epic: [WORKSTREAMS.md](WORKSTREAMS.md) §6.

> **Explain it like I am the founder**
> One row per epic, saying where it stands: `todo`, `in-progress` (someone is building it on a branch), `in-review` (a PR is open), `done` (merged), `parked` or `superseded`.
> Every PR that finishes an epic updates its row here, in the same PR, and adds a line to the repo-root [CHANGELOG.md](../../CHANGELOG.md).
> Today: 14 PRs merged (foundation, contract, proof-of-concept code and the OS updater); one PR open (OS security pipeline); ten branches in progress; all leap build epics are still `todo`.

## Summary

| State | Epics |
|---|---|
| done | 1 (OS-UPDATER) |
| in-review | 2 (OS-SECPIPE, CORE-UPDATE-1) |
| in-progress | 10 (W2-GW, W2-PIPE, W2-DEPLOY, PA-ALIGN, PA-ARCH, PA-THREAT, PA-UI, PA-SITE, PA-MOBILE, LEAP-DOCS) |
| todo | 164 |
| parked | 4 (PLAN-E7-LAB, PLAN-E14, PLAN-E15, PH2-DESKTOP) |
| superseded | 1 (DEV-API-14) |

"in-progress" on a branch with no PR means work exists only in a local worktree or on an unpushed branch. Push it so it is not lost.

## Already merged (foundation, before the leap)

| PR | Merged (UTC) | Branch | What it delivered | Maps to |
|---|---|---|---|---|
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
| CORE-UPDATE-1 | Land both update branches with CI green | done | (both update branches) | #15 and [#14](https://github.com/onemindos/ONEMINDOS/pull/14) merged |
| W2-GW | Gateway wave 2: scan gate, app agent principals, `/mcp` with 3 tool… | in-progress | `feat/gateway-agent-mcp` | – (3 commits) |
| W2-PIPE | App pipeline: scaffolder, app-gate (§9.4), `scan.json` (§11.1), k3d… | in-progress | `feat/app-pipeline` | – (4 commits) |
| W2-DEPLOY | Developer install: `install.sh --role hub` or `node`, compose dev hub… | in-progress | `feat/deploy-v0` | – (6 commits) |
| W2-HERMES | Hermes packaged as `apps/hermes-agent`, an agent principal | todo | `feat/app-hermes` (empty) | – |
| W2-SEEDS | Wave-2 seed apps | todo | `feat/apps-wave2` (empty) | – |
| PA-ALIGN | Core alignment against the leading self-hosted OSes | done | `docs/core-architecture` | [#17](https://github.com/onemindos/ONEMINDOS/pull/17) |
| PA-ARCH | Phase-B architecture docs and `CONTRACT-12-DRAFT.md` | done | `docs/core-architecture` | [#17](https://github.com/onemindos/ONEMINDOS/pull/17) |
| PA-THREAT | Threat model and ranked hardening backlog (H-ids) | done | `docs/security-threat-model` | [#18](https://github.com/onemindos/ONEMINDOS/pull/18) |
| PA-UI | Design system `@onemind/ui`: tokens and components, light and dark | done | `feat/design-system` | [#20](https://github.com/onemindos/ONEMINDOS/pull/20) |
| PA-SITE | Website (Astro + Starlight) committed | done | `feat/website` | [#19](https://github.com/onemindos/ONEMINDOS/pull/19) |
| PA-MOBILE | Mobile shell (Expo) committed | done | `feat/mobile-shell` | [#21](https://github.com/onemindos/ONEMINDOS/pull/21) |
| MKT-CANDIDATES | Ranked Market candidate list from 7 competitor stores | done | `feat/app-candidates` | [#22](https://github.com/onemindos/ONEMINDOS/pull/22) |
| CORE-NET-P1 | Mesh (Headscale + DERP), NATS leaf, app proxy, box CA, NAT lab | in-progress | `feat/core-net` | – |
| UI-LEAP | Parity audit, customization, Home widgets, Store + app management, shell, Settings | in-progress | `feat/ui-leap` | – |
| MKT-TAXONOMY | App and deployment categories | in-progress | `feat/app-taxonomy` | – |
| PLAN-E1 | Workbench (G0) and gate content re-synced to D-007 | todo | founder lab kit | – |
| LEAP-DOCS | Leap specs, workstreams, backlog, status, decisions, CHANGELOG | done | `docs/leap` | [#16](https://github.com/onemindos/ONEMINDOS/pull/16) |

### S1: contract §12, plumbing, sandbox, SDK/CLI/MCP foundations (weeks 1–5)

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| C12-A | Contract §12-a: conventions, error codes (`rate_limited`, `policy_r… | todo | – | – |
| C12-H | Contract §12-h: MCP additions (scopes in `spec.agent`, preview, wit… | todo | – | – |
| DEV-API-1 | Route inventory, conventions, `routes.py` registration seam | todo | – | – |
| DEV-API-3 | Error model v1: `request_id`, `details`, opt-in new codes, size limits | todo | – | – |
| DEV-SDK-1 | Spec readiness: response models, stable operation ids, open enums… | in-progress | `feat/devsurface` (local) | – |
| DEV-API-2 | OpenAPI compat gate (oasdiff) and `x-onemind` extension linter | todo | – | – |
| DEV-SDK-2 | Generation toolchain and CI staleness check | in-progress | `feat/devsurface` (local) | – |
| DEV-API-4 | Pagination (Link), filters, ETag/If-Match, `Idempotency-Key` header | todo | – | – |
| DEV-API-5 | Scopes, role defaults, `/v1/me`, step-up hook | todo | – | – |
| CORE-SANDBOX-1 | Rule file and pure-Python checker with fixtures | todo | – | – |
| CORE-SANDBOX-2 | Gateway renders, checks and stores the plan; `apply -f -` with the… | todo | – | – |
| CORE-SANDBOX-3 | PSA `restricted` in the image and `install.sh` | todo | – | – |
| CORE-SANDBOX-4 | Gateway RBAC, `ValidatingAdmissionPolicy`, short-lived bound token | todo | – | – |
| CORE-SANDBOX-5 | Default-deny NetworkPolicy per app, host nftables, `spec.network.eg… | todo | – | – |
| CORE-SANDBOX-6 | app-gate uses the same checker; `scan.json` gains `policy_version`… | todo | – | – |
| CORE-AUTO-1 | Risk classes on action types, enforced in the approve path | todo | – | – |
| DEV-API-7 | Actions v1: risk, `plan_sha256` binding, preview, cancel, action-ty… | todo | – | – |
| CORE-SEC-1 | HTTPS with a per-box CA, loopback-only HTTP, pairing QR | todo | – | – |
| CORE-SEC-2 | Owner passkey, sessions, passkey-signed approvals (`approve-options`) | todo | – | – |
| CORE-SEC-3 | Token lifecycle: create, rotate, expire, revoke, CLI | todo | – | – |
| CORE-SEC-4 | NATS nkeys and TLS | todo | – | – |
| CORE-SEC-6 | `onemind audit verify`, signed checkpoints, agent kill switch | todo | – | – |
| CORE-SEC-7 | Pending cap, plan card fields, "written by agent" label | todo | – | – |
| CORE-SEC-8 | Signing keys in GitHub environments, split jobs | todo | – | – |
| CORE-SEC-9 | CSP and security headers, body and rate limits | todo | – | – |
| DEV-API-6 | Tokens API and per-plugin tokens from manifest `spec.api` scopes | todo | – | – |
| DEV-API-8 | Events stream over SSE with resume and scope filtering | in-progress | `feat/devsurface` (local) | – |
| DEV-API-9 | Audit read, verify and signed off-box checkpoints | todo | – | – |
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
| DEV-CLI-12 | `onemind mcp` acceptance | in-progress | `feat/devsurface` (local) | – |
| CORE-DASH-1 | `ui/` components v0 and dark mode | todo | – | – |
| CORE-DASH-3 | Approvals plan card with passkey approve | todo | – | – |
| CORE-DASH-4 | Activity (audit) and Agents (suspend) screens | todo | – | – |
| DEV-MCP-5 | Prompt-injection defences: `<untrusted>` marking, `AgentNote` on th… | in-progress | `feat/devsurface` (local) | – |
| CORE-UPDATE-2 | Local socket, `/v1/os/*`, `os.update` and `os.rollback` actions | todo | – | – |
| CORE-UPDATE-4 | Metal runs for G1 on the x86 mini PC; start the Pi soak | todo | – | – |
| DEV-CLI-6 | `update status/check/apply` via the onemindd socket on the box, `os… | todo | – | – |
| DEV-CLI-14 | Headless local context over the onemindd socket with peer-uid check | todo | – | – |
| PLAN-E6 | Manifest v1 freeze: merge with research 29 §6, converter, one valid… | todo | – | – |
| PLAN-E5 | App factory: 15 apps by week 6, 30 by week 13, trust cards | todo | – | – |
| CORE-WEB-1 | Commit `site/`, CI build, link check, axe, deploy to GitHub Pages | todo | – | – |

### S2: fabric, backups, notifications, dashboard redesign, mobile v1 (weeks 5–9)

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| C12-B | Contract §12-b: fabric routes, heartbeat `fabric` | todo | – | – |
| C12-D | Contract §12-d: backups, manifest `backup:`, heartbeat `backup` | todo | – | – |
| C12-E | Contract §12-e: notifications, activity, repairs | todo | – | – |
| C12-G | Contract §12-g: approval challenge and iOS relay contract | todo | – | – |
| CORE-SEC-5 | LUKS2 data, k3s secrets encryption, WireGuard pod traffic | todo | – | – |
| CORE-SEC-10 | Identity floor: on-box IdP, roles, retire v0 tokens | todo | – | – |
| CORE-FABRIC-1 | `node.join` action, join tickets and requests, `onemind fabric join… | todo | – | – |
| DEV-API-10 | Fabric route shapes | todo | built inside CORE-FABRIC-1 | – |
| CORE-FABRIC-2 | Per-node identity (nkey, cert, principal) and revocation | todo | – | – |
| CORE-FABRIC-3 | `node.remove` with drain | todo | – | – |
| CORE-FABRIC-4 | Capability labels, affinity from `requires`, Market verdict | todo | – | – |
| CORE-FABRIC-5 | Leaf mode in onemindd (no k3s) | todo | – | – |
| DEV-CLI-8 | `fabric qr/join/leave/remove` and `node join` alias | todo | – | – |
| CORE-BACKUP-1 | `onemind-local` Retain StorageClass as default | todo | – | – |
| CORE-BACKUP-2 | `internal/backup` agent: restic, schedule, three keys, emergency kit | todo | – | – |
| CORE-BACKUP-3 | k3s datastore online backup with integrity gate | todo | – | – |
| CORE-BACKUP-4 | Destinations: USB, another OneMind box (append-only), S3 | todo | – | – |
| CORE-BACKUP-5 | Manifest `backup:` hooks | todo | – | – |
| CORE-BACKUP-6 | Restore file, app or box, approval-gated; restore at onboarding | todo | – | – |
| CORE-BACKUP-7 | Verified-restore badge (daily check, weekly scratch restore) | todo | – | – |
| CORE-NOTIFY-1 | Alert record and store, `/v1/alerts`, NATS subjects, in-app inbox | todo | – | – |
| DEV-API-12 | Notifications route shapes | todo | built inside CORE-NOTIFY-1 | – |
| CORE-BACKUP-8 | Backups API, screen and alerts | todo | – | – |
| DEV-API-11 | Backups and restores route shapes | todo | built inside CORE-BACKUP-8 | – |
| DEV-CLI-7 | `backup status/list/now/verify` and `restore` | todo | – | – |
| CORE-NOTIFY-2 | Sources: approvals, nodes, updates, backups, scans, audit (H-28) | todo | – | – |
| CORE-NOTIFY-3 | Web Push and Android UnifiedPush via the box's ntfy; push registrat… | todo | – | – |
| CORE-NOTIFY-4 | iOS APNs relay | todo | – | – |
| CORE-NOTIFY-5 | Repairs with fix actions | todo | – | – |
| CORE-NOTIFY-6 | Email, webhook, Matrix, Telegram channels; routing and quiet hours | todo | – | – |
| CORE-UPDATE-3 | Updates screen and "What's new" | todo | – | – |
| CORE-UPDATE-5 | App updates through approval (catalog diff, `app.update`) | todo | – | – |
| CORE-UPDATE-6 | Health-gated app updates with snapshot and revert | todo | – | – |
| CORE-UPDATE-7 | Offline grace and USB/LAN mirror installs | todo | – | – |
| CORE-UPDATE-8 | Rescue console in onemindd | todo | – | – |
| CORE-DASH-2 | Move the 5 existing screens onto `@onemind/ui` | todo | – | – |
| CORE-DASH-5 | Alerts, Updates and Backups screens | todo | – | – |
| CORE-DASH-7 | PWA and per-app subdomain launcher | todo | – | – |
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
| PLAN-E10 | Pi 5 image (G2): RAUC + tryboot, signed image, wizard | todo | – | – |

### S3: automation, plugin SDK v0, website launch, dogfood migration (weeks 9–13)

| Id | Title | State | Branch | PR |
|---|---|---|---|---|
| C12-C | Contract §12-c: deployments, manifest `health`, `settings`, `secret… | todo | – | – |
| C12-F | Contract §12-f: automation | todo | – | – |
| C12-PLG | Contract plugins amendment: `kind: plugin`, `plugin.invoke`, `plugi… | todo | – | – |
| CORE-AUTO-2 | Scheduler and event/webhook triggers that create actions | todo | – | – |
| CORE-AUTO-3 | Standing approvals with ledger-counted limits | todo | – | – |
| CORE-AUTO-4 | Dry run, CLI (`auto`, `policy`) and Automations page | todo | – | – |
| CORE-AUTO-5 | Failure and recovery notifications, repairs hook-up | todo | – | – |
| DEV-API-13 | Automation and OS update route shapes | todo | built inside CORE-AUTO-2, CORE-UPDATE-2 | – |
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
| PLAN-E11 | Jetson and platform floor (G3) | todo | – | – |

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

## How to update this page

- Claiming an epic: open a draft PR titled with the epic id; you may set the row to `in-progress` with the branch name in that PR.
- When the PR opens for review: `in-review` and the PR link.
- When it merges: `done`. The same PR adds a CHANGELOG entry.
- Re-check against reality with `gh pr list -R onemindos/ONEMINDOS --state all` and `git log --first-parent main`.
