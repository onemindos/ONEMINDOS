<!-- SPDX-License-Identifier: Apache-2.0 -->
# Core alignment: matching and beating the leaders

**Date:** 2026-11-12 · **Status:** proposal for the founder; changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md) or the contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md).
**Scope:** the founder focus of 2026-11-12. The goal is a **core OS** stable, usable and well-designed enough for the founder to replace his own self-run Kubernetes cluster with OneMind OS and use it every day. Priorities: security, multi-node fabric, backups, deployments, automation, notifications, a properly designed UI, Android and iPhone app shells, and the first plugin UI extension points. **Out of scope for now:** robotics, drones, physical actuation and TAK extensions. Headless operation stays first-class; a richer desktop and plugin UI is phase 2.
**Builds on:** the teardowns in [`research-output/02-competitors/`](../../research-output/02-competitors/) and [`MATRIX.md`](../../research-output/02-competitors/MATRIX.md), and research files [`12`](../../research-output/12-dashboard-clients-xr.md), [`13`](../../research-output/13-apps-market-plugins.md), [`29`](../../research-output/29-PLATFORM-ECOSYSTEM-MARKETPLACE.md), [`06`](../../research-output/06-backups-recovery.md), [`07`](../../research-output/07-security-compliance.md), [`09`](../../research-output/09-iot-mesh-offgrid-tak.md) (fabric parts only) and [`30`](../../research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md).

> ### In plain words
> The research already chose what to take from each competitor. This page checks that against **what is actually built**, then re-checks the leaders' latest releases.
>
> **Where we already lead, on paper and partly in code:**
> - an update is kept only after a health check of the system as it runs now (fresh signals);
> - signed updates through TUF;
> - every change is a request that only the owner can approve;
> - agents get their own identities and never act as the owner;
> - a hash-chained audit log;
> - apps can be installed only after a security scan.
>
> No leader has all of these.
>
> **Where we are behind**, the things that make a box usable every day are missing:
> - real login and HTTPS;
> - a first-boot wizard;
> - backups and restore;
> - notifications;
> - app updates and logs;
> - a phone app;
> - a design system;
> - adding a node from the screen.
>
> umbrelOS now has phone apps for iPhone and Android. Home Assistant OS has a repairs inbox. Coolify sends notifications through six channels (email, Discord, Slack, Telegram, Pushover, webhook).
>
> The plan in §5: get to **parity on those first**, and build each one on the parts where we already lead, so it also **beats** the leaders. Examples: a backup is shown as verified only after a test restore passes; an app update is kept only if the app is still healthy afterwards; you approve actions from your phone with Face ID.

---

## 1. How to read this page

- **Leader rows** say what a competitor does, with a source:
  - a claim ID from the teardowns (`C-TD-…`, resolved in `research-output/evidence/claims/`);
  - a file path in that project's repository at the commit in §2;
  - or a release-note URL.
- **Today** lists what OneMind has:
  - **on `main`**: merged code;
  - **in flight**: wave-2 branches that are written but not merged. They are listed so this page plans on top of them, not around them.
- Each **item** has a type:
  - **PARITY**: something we must match to be usable every day.
  - **BEAT**: a feature the leaders lack that we can build on parts we already have.
- **Effort**, for one founder plus coding agents:
  - **S**: up to 3 days.
  - **M**: 1 to 2 weeks.
  - **L**: 3 weeks or more.
- **Depends on** names other item IDs or the brief-30 deliverables (`D-B…`).
- **Code reuse:** we copy **patterns** from any project. We copy **code** only from MIT, BSD or Apache-2.0 sources, at the commit in §2, with a `NOTICE` entry (the repository has no `NOTICE` file yet; the first copy creates it). D-001's guardrail names PolyForm-NC, AGPL, GPL and unlicensed sources; the same reasoning covers LGPL and the Commons Clause. Licences that rule out copying code:
  - umbrelOS (PolyForm Noncommercial);
  - Olares (AGPL-3.0 plus its own non-commercial licence);
  - TrueNAS middleware (LGPL-3.0);
  - Unraid API (GPL-2.0 or later);
  - Runtipi (GPL-3.0);
  - YunoHost (AGPL-3.0);
  - Cosmos (Apache-2.0 with the Commons Clause);
  - ZimaOS (no licence file).

## 2. Leaders re-checked (primary sources, 2026-11-12)

Every repository below was read in a shallow clone outside this repository. **Code copy?** says whether its licence allows copying code into Apache-2.0 OneMind code.

| Leader | Latest release seen | Commit read | Licence at that commit | Code copy? |
|---|---|---|---|---|
| umbrelOS | 2.1.0-beta.1, 2026-11-03 ([release](https://github.com/getumbrel/umbrel/releases/tag/2.1.0-beta.1)) | `getumbrel/umbrel` `c43beed` (2026-11-04) | PolyForm Noncommercial 1.0.0 (`LICENSE.md`) | **No.** Study only. |
| Home Assistant OS | 18.5, 2026-11-06 ([release](https://github.com/home-assistant/operating-system/releases/tag/18.5)) | `home-assistant/operating-system` `ab7d0f1`; `home-assistant/supervisor` `040f14c` (2026-11-10) | Apache-2.0 | Yes, with NOTICE |
| CasaOS / ZimaOS | ZimaOS 1.8.0, 2026-10-15 ([release](https://github.com/IceWhaleTech/ZimaOS/releases/tag/1.8.0)); CasaOS last tagged v0.4.17-alpha1 (2025-04-17) | `IceWhaleTech/CasaOS` `e099dd6`; `IceWhaleTech/ZimaOS` `8bc1599` | CasaOS Apache-2.0; ZimaOS repository has no licence file (release notes and assets only) | CasaOS yes; ZimaOS no |
| StartOS | monorepo `main` (the `start-os` repository has moved to a monorepo) | `Start9Labs/start-os` `246876d` (2026-11-10) | MIT | Yes, with NOTICE |
| Olares | 1.12.9-20261111 ([release](https://github.com/beclab/Olares/releases/tag/1.12.9-20261111)) | `beclab/Olares` `e7fe1c96` (2026-11-10) | `LICENSE` AGPL-3.0 **and** `LICENSE.md` "Olares License" (non-commercial use only) | **No** |
| TrueNAS | — | `truenas/middleware` `29ed02b` (2026-10-26) | LGPL-3.0 | No |
| Unraid | API v4.37.11, 2026-11-04 ([release](https://github.com/unraid/api/releases/tag/v4.37.11)) | `unraid/api` `8e587fe` | GPL-2.0-or-later (`LICENSE.txt`) | No |
| Cosmos | — | `azukaar/Cosmos-Server` `69c5303` (2026-08-30) | Apache-2.0 + Commons Clause + anti-tampering clause (`LICENCE`) | **No** (not Apache-compatible) |
| Runtipi | — | `runtipi/runtipi` `a8f22ed` (2026-11-03) | GPL-3.0 | No |
| YunoHost | debian/13.0.9, 2026-10-26 | `YunoHost/yunohost` `2734f23` | AGPL-3.0 | No |
| Coolify | v4.7.5, 2026-11-10 ([release](https://github.com/coollabsio/coolify/releases/tag/v4.7.5)) | `coollabsio/coolify` `37aaf60` | Apache-2.0 | Yes, with NOTICE |
| Omarchy | `main` | `omacom/omarchy` `ceb30ed` (2026-11-11); `omacom/omarchy-plugin-marketplace` `f01e186` | MIT (both) | Yes, with NOTICE |

**What changed since the teardowns (2026-11-10):**
1. **umbrelOS 2.1 beta 1 adds native phone and desktop apps.**
   - The iPhone app existed already. The new Android app backs up photos and videos and opens umbrelOS and its apps already signed in.
   - A new Windows app adds the box's shared folders to File Explorer, as the existing Mac app already does in Finder ([release notes](https://github.com/getumbrel/umbrel/releases/tag/2.1.0-beta.1)).
   - **The mobile bar has moved: a phone app is now table stakes for this market.**
2. **ZimaOS 1.8.0 is about media and hardware** (AI photo gallery, Spotlight search, fan policies). It has no core changes to updates, backups or security.
3. **Home Assistant now calls add-ons "apps".** The Supervisor tree has `supervisor/apps/` where it used to have `addons/`.
4. **Olares now dual-licenses** with a non-commercial `LICENSE.md` alongside AGPL-3.0. The patterns-only rule for Olares stands.

## 3. What the research took from each leader, and what is built

| Leader | What the research said to take | Where | Built? |
|---|---|---|---|
| umbrelOS | Debian image built from a container by a small team; onboarding that offers restore; host daemon for recovery; signing design from 2.1 (pattern only) | MATRIX §5; 12 §17; 30 §12 | Image pipeline on `main` (`os/rootfs/Containerfile`, `os/assemble/`). Signing: TUF client in flight (updater). Onboarding with restore: **not built**. Rescue console in `onemindd`: **not built** (`os/gate/onemind-local-api-respond` is only the gate's probe). |
| Home Assistant OS | RAUC A/B with verity bundles; the repairs model for alerts; encrypted backups that are on by default; Local Push; restore during onboarding | MATRIX §5; 12 §6.1, §17 | RAUC + gate on `main` (`os/rauc/`, `os/gate/`). Repairs, backups, Local Push: **not built**. |
| StartOS | Signs OS updates and packages; user-owned trust list; restore onto a different CPU architecture | MATRIX §5; 02-competitors/startos.md REC-TD-startos-03 | TUF in flight. Trust list, backups: **not built**. |
| Olares | k3s app platform; render-and-lint; one app per subdomain; one codebase for all clients | MATRIX §5; 12 §17 | k3s + kustomize executor on `main` (`core/onemind_core/executors.py`). Lint and scan gate in flight (`sdk/tools/app-gate`, pipeline). Subdomains, clients: **not built**. |
| Coolify | MCP with token abilities, hidden tools, `confirm=true`, redacted secrets | 02-competitors/coolify-dokploy.md | Better on `main` + in flight: agent principals; MCP with **no approve tool** (contract §11.2–11.3, gwmcp). |
| TrueNAS | MCP confirmations; restic for cloud backup | MATRIX §5 | Approvals built; restic: in flight only as the updater's pre-update snapshot. |
| Proxmox | Realms and RBAC; any node shows the whole cluster | MATRIX §5; 12 §17 | Static token roles on `main` (`core/onemind_core/auth.py`). Realms: **not built**. |
| Homarr (not an OS) | Widget catalogue; its Apache-2.0 integration code may be reused | 12 REC-W11-06 | **Not built** |
| Omarchy | Plugin manifest + validator + reserved namespace; client-and-plugin pack, not an image | 12 REC-W11-13; 29 | Manifest schema + `sdk/tools/validate-apps` on `main`. Plugin UI: **not built**. |
| ntfy | Ping-then-fetch push | 12 §6.2 | ntfy app manifest only (`apps/ntfy/`) |

## 4. Core areas

**Built on `main` (shared baseline for every area):**
- `onemindd`: heartbeat over NATS plus `GET :7480/api/v1/node` (`cmd/onemindd/`, `internal/`).
- `onemind` CLI (`cmd/onemind/`).
- Gateway (`core/onemind_core/`):
  - REST: instance, nodes, apps, actions;
  - owner-only approvals;
  - idempotency keys and expiry;
  - hash-chained JSONL audit log, also published to NATS;
  - `noop` and `kubernetes` executors.
- Dashboard (`dashboard/src/pages/`: Home, Nodes, Market, Approvals, SignIn; WCAG 2.2 AA tests in `dashboard/src/ui.test.tsx`).
- 3 apps (`apps/`).
- Image + RAUC + health gate (`os/`).

**In flight (wave 2):** (status when this page was written; `feat/onemindd-updater` has since merged to `main` as PR #15, so rebase before relying on the "in flight" labels below)
- `feat/app-pipeline`: schema fields, `app-gate`, `app-scaffold`, `app-readme`.
- `feat/gateway-agent-mcp`:
  - scan gate (§11.1);
  - app agent principals (§11.2);
  - `POST /mcp` (§11.3);
  - trust card and app page (`dashboard/src/components/AppTrust.tsx`, `dashboard/src/pages/AppDetail.tsx`).
- `feat/deploy-v0`: `deploy/install.sh --role hub|node`, Docker Compose dev hub, `deploy/verify/verify.sh`.
- `feat/os-security-pipeline`: `os/update/` (`scan-gate.py`, `tuf-repo.py`, `channel.json`, `debian-vex.py`), nightly security workflow.
- `feat/onemindd-updater`: `internal/update/` (TUF client, channels, maintenance window, pre-update restic snapshot, state read back from the gate; the heartbeat gains `update`).
- The design-system, mobile-shell and Hermes branches have no commits yet.

### 4.1 Install and onboarding

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | Browser onboarding: create account, choose storage or RAID, **restore from a backup during onboarding** | `packages/ui/src/routes/onboarding/` (`create-account.tsx`, `restore.tsx`, `raid/`); test `packages/umbreld/source/modules/backups/backups-restore-onboarding.vm.test.ts` |
| Home Assistant OS | Onboarding offers restore from a backup | 12 §17 [C-W11-013…019] |
| StartOS | Setup service: fresh install, restore, or transfer from an old drive | `shared-libs/crates/start-core/src/setup.rs` |
| Olares | Activation wizard needs the LarePass phone app | `cli/cmd/ctl/wizard/`; 12 §17 |
| Coolify / CasaOS | One-line `curl \| bash` installer; CasaOS's installer has no checksum or signature | [C-TD-casaos-zimaos-021]; Coolify docs |

**Today:**
- `os/assemble/` builds disk images and an OVA.
- The SignIn page asks for a bearer token (`dashboard/src/pages/SignIn.tsx`).
- In flight: `deploy/install.sh` (pinned, checksum-checked downloads; separate agent-only join token) and `deploy/verify/verify.sh`.
- No first-boot wizard.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| ONB-P1 | PARITY | First-boot web wizard: name the box, create the owner, set the time zone, choose the data disk | M | SEC-P1 |
| ONB-P2 | PARITY | Find the box on the LAN as `onemind.local` (mDNS) and print its address on the console | S | — |
| ONB-P3 | PARITY | Restore from a backup during onboarding (new hardware, same data) | M | BAK-P4, ONB-P1 |
| ONB-B1 | BEAT | **Headless twin:** `onemind init` runs the same wizard steps from a terminal or a config file, so a box can be set up without a screen (none of the leaders treats headless setup as equal) | S | ONB-P1 |
| ONB-B2 | BEAT | **Emergency kit cannot be skipped** (owner recovery key + backup key, D-B7.2), and onboarding ends with a first backup that a test restore has checked | M | BAK-P1, BAK-B1 |
| ONB-B3 | BEAT | **Verified installer:** `install.sh` checks a signed manifest of the pinned versions before it changes the host, not just checksums | S | deploy-v0, TUF keys |

### 4.2 Dashboard UX and design

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | Desktop with app grid and wallpaper; up to 3 widgets per account from typed templates (stats, list, progress); a progress "island" for long jobs; command palette in settings; "What's new" dialog after an update; layout for phones and tablets | `packages/ui/src/modules/widgets/`, `.../floating-island/`, `packages/ui/src/routes/settings/cmdk-entries.ts`, `routes/whats-new-modal.tsx`; widget limit in `packages/umbreld/source/modules/widgets/routes.ts`; 2.1 release notes |
| Home Assistant | Repairs inbox; dashboards; dropped the global "advanced mode" in favour of role and detail per screen | 12 §17 [C-W11-018, C-W11-019] |
| StartOS | Portal sections: services, marketplace, sideload, updates, backups, notifications, metrics, logs, system | `projects/start-os/web/ui/src/app/routes/portal/routes/` |
| ZimaOS 1.8 | Spotlight search across features and content | [1.8.0 notes](https://github.com/IceWhaleTech/ZimaOS/releases/tag/1.8.0) |
| Olares | Web desktop; apps in windows or on their own subdomains | 12 §17 [C-W11-009…012] |

**Today:**
- 5 screens.
- Freshness rules: stale values are never shown as live; age is computed on the hub's clock (`dashboard/README.md`).
- WCAG 2.2 AA tests.
- 18 CSS custom properties in `dashboard/src/styles.css`, with no dark mode and no component library.
- In flight: app page + trust card.
- No design system yet (that branch is empty).

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| UX-P1 | PARITY | Design system: tokens (colour, type, spacing, radius), light and dark themes, core components (card, list, table, dialog, toast, status pill, progress), one icon set | M | — |
| UX-P2 | PARITY | App launcher: open each installed app on its own subdomain behind the gateway login (REC-W11-03) | M | SEC-P2 |
| UX-P3 | PARITY | Command palette (search for apps, nodes, settings and actions) and a jobs tray that shows long-running actions with progress | S | UX-P1 |
| UX-P4 | PARITY | Per-app and per-node logs and basic metrics (CPU, memory, disk) | M | APP-P3 |
| UX-P5 | PARITY | "What's new" after an OS update, from the release notes | S | OSU-P1 |
| UX-B1 | BEAT | **Activity timeline:** every request, approval, run and failure from the hash-chained audit log, filtered by node, app and agent, with a "chain verified" mark | S | `core/onemind_core/audit.py` |
| UX-B2 | BEAT | **Show the equivalent call:** every button can show the API, CLI or MCP call it makes, so GUI, headless and agent use are the same (REC-W11-20); no leader shows this | S | — |
| UX-B3 | BEAT | **Truthful status everywhere:** extend the existing stale/offline rule to apps, backups and updates ("last verified N ago", never a cached green) | S | — |

### 4.3 App store, app install and app updates

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | App store plus community app stores added by Git URL; the community stores follow a mutable branch head | `packages/ui/src/modules/community-app-store/`; 30 §12 [C-W19-012] |
| StartOS | Signed S9PK packages and signed registry index; sideload; data snapshot restored if an app update fails | [C-TD-startos-024][C-TD-startos-028][C-TD-startos-022]; `portal/routes/sideload` |
| Home Assistant | App security rating 1–8; app images not verified on the device | [C-TD-home-assistant-os-025][C-TD-home-assistant-os-024] |
| Olares | Helm + manifest + strict linter that exempts its own images | [C-TD-olares-028][C-TD-olares-030] |
| Cloudron / YunoHost / Runtipi | Backup before every update (mandatory / automatic / optional) | [C-TD-tier-c-selfhost-064][C-TD-tier-c-selfhost-024][C-TD-tier-c-selfhost-045] |
| Omarchy marketplace | Lists a plugin only after a scan of an exact commit and an explicit "approved-and-verified" decision; admits that installs still clone the mutable head | `omarchy-plugin-marketplace/README.md`, `VERIFICATION.md` |

**Today:**
- On `main`:
  - catalog from `apps/*/onemind.app.yaml`;
  - install and remove go through approval;
  - the kustomize executor installs into `app-<id>`.
- In flight:
  - daily scan record `scan.json`, and install is refused when the scan is missing, failing or older than 7 days (§11.1);
  - Market and app page show links, licence, tier and scan date (§11.4);
  - `sdk/tools/app-gate` and `app-scaffold`.
- No app updates, logs, settings or rollback.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| APP-P1 | PARITY | App updates: "update available", update through approval, an auto-update policy per app (off, security only, all) | M | gwmcp, pipeline |
| APP-P2 | PARITY | Remove keeps the data by default; "delete data" is a separate action that needs approval | S | D-B7.1 |
| APP-P3 | PARITY | App detail: status, restart, logs, settings (environment and ports from the manifest) | M | — |
| APP-P4 | PARITY | Custom app: install from a Compose file or a folder through the same scan gate (`onemind app import`, E1) | M | DEP-P1 |
| APP-B1 | BEAT | **Health-gated app updates:** snapshot the app's volumes, update, run the manifest's probes with fresh signals, and revert to the old version and snapshot if they fail. This brings the OS gate's rule to apps; StartOS restores data, but no leader gates on fresh health | M | APP-P1, BAK-P1 |
| APP-B2 | BEAT | **Scan-gated market with public records:** each app's `scan.json` and history are visible on the app page and the website, and a failed daily rescan raises an alert and blocks updates | S | gwmcp, NOT-P1 |
| APP-B3 | BEAT | **"Why not?" verdict:** before install, say per node whether the app fits (arch, memory, GPU) and what it will be granted (E2 capability verdict) | M | FAB-P3 |

### 4.4 Deployments (your own services)

The founder runs his own services today, not only store apps, so this area is added to the thirteen in the brief.

| Leader | What they do | Source |
|---|---|---|
| Coolify | Deploy from Git, a Dockerfile or Compose to one or many servers over SSH; 388 templates; scheduled tasks | [C-TD-tier-c-selfhost-085][C-TD-tier-c-selfhost-089] |
| Dokploy | Same idea on Docker Swarm; an AI drafts Compose files | [C-TD-tier-c-selfhost-103][C-TD-tier-c-selfhost-106] |
| TrueNAS | Any Compose file as a "custom app" | [C-TD-truenas-scale-023] |
| umbrelOS / HA | No deploy-your-own path beyond the store; umbrelOS runs full VMs ("Machines") instead | `packages/umbreld/source/modules/machines/` |

**Today:** the `kubernetes` executor applies a kustomization (`core/onemind_core/executors.py`). There is no Git source, no deploy history and no rollback.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| DEP-P1 | PARITY | `onemind deploy <dir or git-url>`: turn a kustomization, Helm chart or Compose file into a private OneMind app (manifest generated), then install through approval | M | APP-P4 |
| DEP-P2 | PARITY | Deploy history per service with one-step rollback to the previous digests | M | DEP-P1 |
| DEP-P3 | PARITY | Secrets for your own services, sealed on the box and never shown back (Coolify redacts secrets too) | M | SEC-P1 |
| DEP-B1 | BEAT | **Watched Git source with approval:** a new commit becomes a pending action showing the diff, the image digests and the scan result; approve from the phone | M | DEP-P1, MOB-B1 |
| DEP-B2 | BEAT | **Migration kit:** import existing Kubernetes manifests or Helm values, check them (resources, pinned digests, retained volumes), run old and new side by side, and switch over | M | DEP-P1 |

### 4.5 OS updates and rollback

| Leader | What they do | Source |
|---|---|---|
| Home Assistant OS | RAUC A/B, 3 tries; marks the new slot good when the Supervisor starts | [C-TD-home-assistant-os-009][C-TD-home-assistant-os-018] |
| umbrelOS | Rugix A/B; stable runs a server-supplied script; 2.1 beta adds offline-root, M-of-N signing; commits when the daemon starts | [C-TD-umbrelos-011][C-TD-umbrelos-013][C-TD-umbrelos-019]; `packages/umbreld/source/modules/update/release-signing.ts` |
| ZimaOS | RAUC; marks good once services start; the UI said "succeeded" on a slot that panicked | [C-TD-casaos-zimaos-013][C-TD-casaos-zimaos-044] |
| TrueNAS / Unraid | Boot environments or one previous version; manual rollback | [C-TD-truenas-scale-011][C-TD-tier-c-nas-007] |
| Omarchy | Filesystem snapshot before update, with restore | `bin/omarchy-snapshot`, `bin/omarchy-update` |
| Synology | Postpone up to 28 days; staged by region | [C-TD-tier-c-nas-034] |

**Today:**
- On `main`: RAUC bundle build (`os/rauc/`) and the fresh-signal health gate (`os/gate/onemind-health-gate`, `onemind-k3s-check`).
- In flight (updater):
  - TUF client;
  - `security` and `stable` channels;
  - maintenance window, postpone, and reboot-inhibit;
  - pre-update restic snapshot;
  - the state after reboot is read from the gate's own files;
  - `onemind update status|check|apply`.
- In flight (ossec): signed channel and scan gate.
- No Updates screen.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| OSU-P1 | PARITY | Updates screen: running version and **booted slot**, available release with notes, policy, window, postpone, apply (approval), history, from the heartbeat's `update` object | S | updater |
| OSU-P2 | PARITY | Beta or preview channel the owner opts into | S | ossec |
| OSU-B1 | BEAT | **Fleet-staged updates:** update one canary node first and wait for its gate verdict; a `committed` verdict releases the next nodes, an `image-bad` verdict stops the whole fleet. None of the leaders has a multi-node, health-gated rollout | M | updater, FAB-P1 |
| OSU-B2 | BEAT | **Security updates explained:** show which CVEs a security release fixes and which listed CVEs do not affect the box (from `os/update/debian-vex.py`) | S | ossec |
| OSU-B3 | BEAT | **Rollback you can trust:** after a rollback, an alert names the failed check from the gate log and offers "retry once" only for `environment-bad` verdicts (REC-DEC-45) | S | NOT-P1, updater |

### 4.6 Backups and restore

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | Kopia every hour, encrypted, to another Umbrel, a NAS or USB (no cloud); browse and mount snapshots; ignored paths; restore during onboarding | [C-TD-umbrelos-030][C-TD-umbrelos-031]; `packages/umbreld/source/modules/backups/backups.ts` (`backupInterval` 1 h, `mountBackup`, `addIgnoredPath`) |
| Home Assistant | SecureTar v3 encrypted archives; daily, keeps 3; local, NAS or cloud agents; full or partial; freezes apps during backup | [C-TD-home-assistant-os-033][C-TD-home-assistant-os-036]; `supervisor/backups/manager.py` (`do_backup_partial`, `freeze_all`) |
| StartOS | Its own encrypted backup filesystem; restores onto a different CPU architecture | [C-TD-startos-034][C-TD-startos-035] |
| HexOS | Encrypted "Buddy Backup" to a friend's box | [C-TD-tier-c-nas-029] |
| Cloudron / YunoHost | Backup before every update | [C-TD-tier-c-selfhost-064][C-TD-tier-c-selfhost-024] |

**Today:**
- Only the updater's pre-update `/data` snapshot (in flight).
- Brief 30 B7 specifies the rest: retained storage class, three-key restic, online k3s SQLite backup, app hooks, verified restores.
- None of it is built.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| BAK-P1 | PARITY | Backup agent: restic, hourly with grandfather-father-son retention, encrypted; covers app volumes and the k3s datastore (online `.backup` + `integrity_check`, D-B7.3) | L | D-B7.1 |
| BAK-P2 | PARITY | Destinations: USB disk, another OneMind box (append-only rest-server), S3-compatible | M | BAK-P1 |
| BAK-P3 | PARITY | Browse snapshots and restore one file or one app (approval-gated) | M | BAK-P1 |
| BAK-P4 | PARITY | Full restore to new hardware (onboarding entry point: ONB-P3) | M | BAK-P1 |
| BAK-P5 | PARITY | App hooks from the manifest `backup:` block (pre/post, database dumps, excludes) | M | BAK-P1 |
| BAK-B1 | BEAT | **Verified-restore badge:** each week, restore into a scratch namespace, run the app's probes with fresh signals, and show "last verified restore" per app and per box. A backup that has not passed this test restore is never shown as green (D-B7.6). No leader proves its restores | M | BAK-P1 |
| BAK-B2 | BEAT | **Three keys + emergency kit:** device, owner recovery and optional escrow keys; the owner key alone restores | S | BAK-P1 |
| BAK-B3 | BEAT | **Fabric buddy backup:** back up to another OneMind node or a friend's box over the fabric, append-only, so a stolen box cannot delete its own backups | M | BAK-P2, FAB-P1 |
| BAK-B4 | BEAT | **Agent-safe backups:** agents may start a backup and read its status; restore, key changes, destination changes and deletes need the owner's approval (W5-R13) | S | BAK-P1 |

### 4.7 Multi-node fabric

| Leader | What they do | Source |
|---|---|---|
| Olares | `olares-cli node add` / `join` / `delete`; k3s with external etcd | `cli/cmd/ctl/node/` (`add.go`, `join.go`, `join_command.go`); [C-TD-olares-021] |
| Cosmos | Several servers linked by NATS + a Nebula VPN ("Constellation"), with devices and pings | `src/constellation/`; [C-TD-tier-c-selfhost-007] |
| Coolify | Many servers driven over SSH | [C-TD-tier-c-selfhost-089] |
| Proxmox / Synology | Cluster where any node shows the whole cluster; two-box HA pair | 12 §17 [C-W11-056][C-W11-057] |
| umbrelOS / HA / StartOS / CasaOS | Single box | MATRIX §2.3 |

**Today:**
- On `main`:
  - heartbeats over NATS every 10 s;
  - stale after 30 s and offline after 120 s;
  - Nodes screen;
  - `onemind nodes` (`internal/heartbeat/`, `core/onemind_core/nodes.py`).
- In flight: `install.sh --role node` with a separate agent-only k3s token.
- No join flow in the UI, no node removal, no placement.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| FAB-P1 | PARITY | Add a node from the dashboard: short-lived join code and QR code (lifetime of 1 hour or less, REC-W11-16); `onemind node join <code>` on the new machine | M | deploy-v0, SEC-P1 |
| FAB-P2 | PARITY | Remove or drain a node; node roles (hub, worker, leaf) shown and changeable | M | FAB-P1 |
| FAB-P3 | PARITY | Placement: apps run only on nodes whose capabilities match the manifest's `requires` | M | — |
| FAB-B1 | BEAT | **Leaf nodes that tolerate being offline:** small or remote machines join as NATS leaves (no k3s), keep working when the hub is unreachable, and sync back; the Nodes screen labels them honestly as stale | M | FAB-P1 |
| FAB-B2 | BEAT | **One fleet view of what happens:** nodes, apps per node, update state, backup state and alerts on one screen, all from the same stream | M | FAB-P1, OSU-P1, BAK-B1 |
| FAB-B3 | BEAT | **Signed node identity:** every node gets its own principal and a certificate from the box CA; a stolen join code expires and is recorded in the audit log | M | SEC-P2 |

### 4.8 Security and identity

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | Owner + members, TOTP, sessions screen; MCP with **one shared grant set**, agents act as the owner | [C-TD-umbrelos-033][C-TD-umbrelos-037]; `packages/ui/src/routes/settings/sessions.tsx`, `packages/umbreld/source/modules/mcp/mcp.ts` |
| StartOS | One master password; MCP with 208 admin tools, on unless switched off | [C-TD-startos-031][C-TD-startos-030] |
| Proxmox / TrueNAS | Realms (PAM, LDAP, OIDC), TOTP and WebAuthn; about 141 RBAC roles | [C-TD-proxmox-ve-031][C-TD-truenas-scale-030] |
| Cosmos / YunoHost | Built-in OIDC server with 2FA; LDAP + SSO for apps | [C-TD-tier-c-selfhost-008][C-TD-tier-c-selfhost-025] |
| Coolify | MCP token abilities, hidden tools, `confirm=true`, secrets redacted (the one to beat) | [C-TD-tier-c-selfhost-082][C-TD-tier-c-selfhost-083] |

**Today:**
- On `main`:
  - static token file with owner, adult, guest and agent roles (`core/onemind_core/auth.py`);
  - owner-only approval;
  - hash-chained audit log with a `verify` command (`core/onemind_core/audit.py`).
- In flight:
  - app agent principals with hashed tokens;
  - MCP for agent principals only, with no approve tool;
  - scan gate;
  - TUF;
  - nightly security workflow.
- Missing: passwords, passkeys, HTTPS, single sign-on for apps.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| SEC-P1 | PARITY | Real accounts: owner with a passkey (password + TOTP as fallback), sessions list and revoke, household roles (D-B9.1, Kanidm) | M | — |
| SEC-P2 | PARITY | HTTPS on the LAN with a per-box CA, installed through the phone app (REC-W11-11) | M | — |
| SEC-P3 | PARITY | Single sign-on for apps: forward-auth at the gateway, with identity headers stripped at ingress | M | SEC-P1, UX-P2 |
| SEC-B1 | BEAT | **Per-action approvals bound to exact parameters**, expiry and grant revision (D-B9.6); already the core model, now visible on every surface. No leader has per-agent scopes, approvals and an audit log together (MATRIX §4.6) | S | — |
| SEC-B2 | BEAT | **Passkey-signed approvals:** the approval carries a WebAuthn assertion over the action hash, so a stolen session cannot approve | M | SEC-P1 |
| SEC-B3 | BEAT | **Agent console:** list agent principals, their grants, recent requests and approval rate; revoke in one tap (D-B9.3) | S | gwmcp |
| SEC-B4 | BEAT | **Security posture page:** shows the signing state, the last scan, open CVEs with VEX, exposed apps, the audit chain check and the backup check, each with a fix action | S | REM-B1; OSU-B2 for the CVE panel |

### 4.9 Notifications

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | Notifications are plain strings stored per account; owner sees global ones | `packages/umbreld/source/modules/notifications/notifications.ts` |
| StartOS | Notification centre plus self-hosted Web Push (VAPID, ES256) | `shared-libs/crates/start-core/src/notifications/push.rs` |
| Home Assistant | Persistent notifications and Repairs with fix flows; phone push through Firebase, unencrypted, 500 a day | `supervisor/resolution/checks/`, `.../fixups/`; 12 §6.2 [C-W11-016] |
| Coolify | Channels: email, Discord, Slack, Telegram, Pushover, webhook; per-event toggles | `app/Notifications/Channels/` |
| TrueNAS / Unraid | Alert sources with severity and alert services; notification agents | MATRIX; `api/src/unraid-api/graph/resolvers/notifications/` |

**Today:**
- ntfy is packaged as an app (`apps/ntfy/`).
- Audit events go to NATS `onemind.audit`.
- No alert record, inbox or delivery.
- D-005 fixes the iOS design: an opaque APNs ping, after which the app fetches the alert from the box.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| NOT-P1 | PARITY | Alert centre: alert record `{id, severity, source, audience, title, body, fixable, fix_action, created, acked_by, resolved}` built from `evt.*` (12 §6.1); inbox with acknowledge and resolve | M | — |
| NOT-P2 | PARITY | Delivery: in-app, Web Push, ntfy/UnifiedPush; email, webhook, Telegram and Matrix as NATS consumers | M | NOT-P1 |
| NOT-P3 | PARITY | Routing per user: by severity, channel and quiet hours | S | NOT-P1, SEC-P1 |
| NOT-B1 | BEAT | **Repairs that go through approval:** system checks (disk space, failed units, expired certificate, stale backup, failed scan, port conflict) each offer a fix action that becomes a normal request. Pattern from HA's resolution centre (Apache-2.0, `supervisor/resolution/`), with the owner's approval added | M | NOT-P1 |
| NOT-B2 | BEAT | **Private push on both phones:** iOS gets an opaque ping and then fetches (D-005); Android uses UnifiedPush to the box's own ntfy, with no Google needed. HA's push is unencrypted | M | MOB-P1 |
| NOT-B3 | BEAT | **Actionable alerts:** an alert that needs a decision carries the pending action; approve or deny from the notification | S | MOB-B1 |

### 4.10 Automation

| Leader | What they do | Source |
|---|---|---|
| Home Assistant | Automations, scripts and blueprints (device-focused) | home-assistant-os.md |
| Coolify | Scheduled tasks per app, with notifications for failure and recovery | `app/Notifications/ScheduledTask/` |
| Cosmos | Built-in CRON jobs | `src/CRON.go`, `src/cron/` |
| Unraid | User Scripts through a community plugin | unraid.md |
| umbrelOS / StartOS / CasaOS | None in the core; n8n or Node-RED as store apps | MATRIX §2.3 |

**Today:**
- Action ledger with idempotency and expiry.
- NATS bus.
- MCP `request_action` (in flight).
- No scheduler, no triggers.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| AUT-P1 | PARITY | Scheduled jobs: cron entries per app or per box (backup now, restart, run a command in an app) as requests | M | — |
| AUT-P2 | PARITY | Event triggers: on an `evt.*` subject or an inbound webhook, create a request | M | NOT-P1 |
| AUT-B1 | BEAT | **Approval policies with limits:** the owner can pre-approve an action type within bounds ("restart uptime-kuma at most 3 times a day", "security updates in the window"); anything outside the bounds goes to the approval queue. Every automated step is in the audit log | M | AUT-P1, SEC-B1 |
| AUT-B2 | BEAT | **Dry run:** every automation shows what it would request, and against which resource, before it is enabled | S | AUT-P1 |

### 4.11 Remote access

| Leader | What they do | Source |
|---|---|---|
| StartOS | StartTunnel: a self-hosted WireGuard "virtual private router" on a VPS; TLS ends at the service | `projects/start-tunnel/README.md` (MIT) |
| umbrelOS | Tor; HTTPS access settings; Tailscale as an app | `packages/ui/src/routes/settings/advanced.tsx` (Tor toggle, `hooks/use-tor-enabled.ts`), `routes/settings/https-access.tsx` |
| Home Assistant | Paid cloud relay (Nabu Casa) | 12 §8.2 |
| Olares | Tailscale/Headscale reached through the LarePass app | olares.md |
| Unraid | Connect service + Tailscale integration | unraid.md |

**Today:** nothing. The research's choice is Tailscale/Headscale first, with no OneMind relay (REC-W11-12).

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| REM-P1 | PARITY | Remote access app: Tailscale or Headscale, off by default, enabled through approval; certificates for the tailnet name | M | SEC-P2 |
| REM-B1 | BEAT | **Exposure review:** one page lists every app with where it can be reached from (LAN, tailnet, public), when that changed and who approved it; making an app public is a request with a warning | S | REM-P1 |
| REM-B2 | BEAT | **Self-hosted tunnel option:** a WireGuard relay on the owner's own VPS (the StartTunnel pattern, MIT) for owners without Tailscale | L | REM-P1 |

### 4.12 Mobile apps (Android and iPhone)

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | iPhone app; Android app in 2.1 beta (photo backup, opens apps already signed in); Mac and Windows apps | [2.1.0-beta.1 notes](https://github.com/getumbrel/umbrel/releases/tag/2.1.0-beta.1) |
| Home Assistant | Native companion apps: Local Push on home Wi-Fi, sensors, Firebase push | 12 §7.1 [C-W11-015][C-W11-017] |
| Olares | LarePass on Capacitor + Electron from one codebase; required for activation | 12 §7.1 [C-W11-011] |

**Today:**
- The dashboard works at 375 px (`dashboard/README.md`).
- The `feat/mobile-shell` branch is empty.
- Research choice: Capacitor shells for iOS and Android over the same web UI, with a UnifiedPush plugin on Android (REC-W11-09).

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| MOB-P1 | PARITY | Capacitor shell for iOS and Android: pair with a box by QR code, sign in with a passkey, tabs for Home, Nodes, Apps, Approvals, Activity and Alerts, open apps signed in | L | SEC-P1, SEC-P2, UX-P1 |
| MOB-P2 | PARITY | Push: Android UnifiedPush; iOS APNs ping-then-fetch through a stateless relay (D-005, REC-W11-08) | M | MOB-P1, NOT-P2 |
| MOB-B1 | BEAT | **Approve from the phone with Face ID or a passkey**, showing the exact parameters, who asked (person or agent) and when it expires; the approval is signed (SEC-B2) | M | MOB-P1, SEC-B2 |
| MOB-B2 | BEAT | **Honest offline view:** the last known state is cached and labelled with its age, never shown as live (the dashboard's freshness rule) | S | MOB-P1 |
| MOB-B3 | BEAT | **Phone optional:** unlike Olares, the box never needs the app to activate; everything in the app also works in a browser or from the CLI | S | — |

### 4.13 Plugin and extension UI

| Leader | What they do | Source |
|---|---|---|
| umbrelOS | Apps declare widgets; owners pick up to 3; widgets fill typed templates; members see only widgets for apps shared with them | `packages/umbreld/source/modules/widgets/routes.ts`, `packages/ui/src/modules/widgets/` |
| Omarchy | Shell plugins with `kinds` (bar widget, panel), required manifest fields, a validator that matches the shell's own checks, enable/disable/remove commands, and a marketplace that lists exact scanned commits | `shell/services/PluginRegistry.qml`, `bin/omarchy-plugin-validate`, `bin/omarchy-plugin-*`; `omarchy-plugin-marketplace/VERIFICATION.md` |
| Home Assistant | Custom cards through HACS; force-uninstall for bad ones | 30 §12 [C-W19-015, C-W19-018] |
| Olares | Apps in iframe windows on the web desktop | 12 §17 |
| MCP Apps | `ui://` resources rendered in agent clients | `modelcontextprotocol/ext-apps`; 30 B8 E5 |

**Today:** the E5 UI slot is specified (brief 30 B8: separate origin per widget, CSP from declared domains, no inherited credentials). Nothing is built.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| PLG-P1 | PARITY | App-declared widgets in `onemind.app.yaml`; typed templates (stat, list, progress) fed by a gateway proxy; arrange widgets on Home | M | UX-P1 |
| PLG-P2 | PARITY | `onemind plugin validate` uses the same Go package as the box (Omarchy's "the CLI refuses what the shell would refuse") | S | pipeline |
| PLG-B1 | BEAT | **Sandboxed custom widgets:** each runs in an iframe on its own origin with a CSP from the manifest and only the grants it declared. Omarchy's plugins run unsandboxed | M | PLG-P1, SEC-P2 |
| PLG-B2 | BEAT | **One widget, three surfaces:** the same widget renders in the dashboard, the phone app and an MCP Apps `ui://` view for agents | M | PLG-B1, MOB-P1 |
| PLG-B3 | BEAT | **Scan-gated, digest-pinned plugins** with an expiring revocation list (E9). Omarchy's own notice says its installs follow the mutable head | M | APP-B2 |

### 4.14 Docs and community

| Leader | What they do | Source |
|---|---|---|
| Home Assistant | Large docs site, community forum, quality scale for integrations | home-assistant-os.md |
| Omarchy | Manual, plugin marketplace site with submit and verify forms, security baseline | `omarchy-plugin-marketplace/README.md`, `SUBMISSION.md`, `SECURITY.md` |
| StartOS | Docs project in the monorepo | `projects/start-docs/` |
| umbrelOS | Community app stores anyone can host | `packages/ui/src/modules/community-app-store/` |

**Today:**
- `docs/` (architecture, decisions, apps, dashboard, learning path), contributor rules in `AGENTS.md`, per-app READMEs, research.
- No user guide, no submission guide, no public changelog.

| ID | Type | Item | Effort | Depends on |
|---|---|---|---|---|
| DOC-P1 | PARITY | User guide: install, first boot, add a node, backups, restore, updates, remote access | M | as each feature lands |
| DOC-P2 | PARITY | App submission guide and template repository (`app-scaffold`), changelog per release | S | pipeline |
| DOC-B1 | BEAT | **Error codes link to docs:** every gateway error and repair links to a page; docs are also served to agents over MCP (REC-W11-17) | S | NOT-B1 |
| DOC-B2 | BEAT | **Public verification records:** the website shows every app's scan history and every release's signatures from the same signed index the boxes read (W12-R13) | M | APP-B2 |

## 5. Core sprint backlog (ranked, founder focus only)

Ranked by what blocks the founder from moving his own services onto OneMind and using it daily:
1. Can I log in safely?
2. Will I lose data?
3. Can I run my services?
4. Will I know when something breaks?
5. Can I see and approve it from my phone?

Each item builds a parity feature on top of a part we already lead in, so one change gives both.

| Rank | Item | IDs | Effort | Depends on |
|---|---|---|---|---|
| 1 | Real accounts: owner passkey, sessions, roles; replaces the static token file | SEC-P1 | M | — |
| 2 | HTTPS on the LAN (per-box CA) and per-app subdomains behind the gateway login | SEC-P2, UX-P2 | M | 1 |
| 3 | Backup agent v0: restic, k3s datastore + app volumes, hourly, USB / other box / S3 | BAK-P1, BAK-P2, BAK-B2 | L | D-B7.1 |
| 4 | Verified-restore badge: weekly scratch restore with fresh probes | BAK-B1 | M | 3 |
| 5 | Restore one file, one app or the whole box, approval-gated | BAK-P3, BAK-P4, BAK-B4 | M | 3 |
| 6 | First-boot wizard with emergency kit and "restore from a backup", plus `onemind init` for headless setup | ONB-P1, ONB-B1, ONB-B2, ONB-P2, ONB-P3 | M | 1, 3, 5 |
| 7 | Design system v0 (tokens, dark mode, components) applied to the 5 existing screens | UX-P1 | M | — |
| 8 | Alert centre + delivery (in-app, Web Push, ntfy, email/webhook/Telegram/Matrix) | NOT-P1, NOT-P2, NOT-P3 | M | 1 |
| 9 | Activity timeline over the audit chain, with "chain verified" | UX-B1 | S | — |
| 10 | Updates screen (booted slot, notes, window, postpone, apply via approval) | OSU-P1, UX-P5 | S | updater merged |
| 11 | App lifecycle: update through approval, restart, logs, settings; remove keeps data | APP-P1, APP-P2, APP-P3 | M | gwmcp merged |
| 12 | Health-gated app updates with snapshot and automatic revert | APP-B1 | M | 3, 11 |
| 13 | `onemind deploy` for your own services + deploy history and rollback | DEP-P1, DEP-P2, APP-P4 | M | 11 |
| 14 | Migration kit from an existing Kubernetes setup (import, check, run side by side, switch over) | DEP-B2 | M | 13 |
| 15 | Add or remove a node from the dashboard (join QR code, `onemind node join`, drain) | FAB-P1, FAB-P2 | M | 1, deploy-v0 merged |
| 16 | Placement by node capability + "why not?" verdict in the Market | FAB-P3, APP-B3 | M | 15 |
| 17 | Mobile shell v0 (Capacitor, iOS + Android): pairing, Home, Nodes, Apps, Approvals, Activity, Alerts | MOB-P1, MOB-B2 | L | 1, 2, 7 |
| 18 | Private push: Android UnifiedPush, iOS ping-then-fetch relay | MOB-P2, NOT-B2 | M | 8, 17 |
| 19 | Approve from the phone with a passkey-signed approval; actionable notifications | MOB-B1, SEC-B2, NOT-B3 | M | 17, 18 |
| 20 | Repairs: system checks with fix actions through approval | NOT-B1 | M | 8 |
| 21 | Automation v0: schedules and event triggers as requests, approval policies with limits, dry run | AUT-P1, AUT-P2, AUT-B1, AUT-B2 | M | 8 |
| 22 | Remote access app (Tailscale/Headscale, off by default) + exposure review | REM-P1, REM-B1 | M | 2 |
| 23 | Fleet-staged OS updates (canary node, gate verdict releases the rest) | OSU-B1 | M | 10, 15 |
| 24 | Home widgets v0: manifest-declared typed widgets, then sandboxed custom widgets | PLG-P1, PLG-P2, PLG-B1 | M | 2, 7 |
| 25 | Agent console + security posture page (CVE panel waits for OSU-B2) | SEC-B3, SEC-B4 | S | 8, 22 |

**Left for later** (keep the IDs):
- UX-P3, UX-P4, UX-B2, UX-B3;
- OSU-P2, OSU-B2, OSU-B3;
- APP-B2;
- DEP-P3, DEP-B1;
- BAK-P5, BAK-B3;
- FAB-B1, FAB-B2, FAB-B3;
- SEC-P3, SEC-B1 (already the model; only the surfaces remain);
- REM-B2;
- PLG-B2, PLG-B3;
- ONB-B3;
- DOC-*.

Robotics, drones, physical actuation and TAK items stay out until the founder reopens them.

## 6. Limits of this page

- **Leader behaviour comes from reading code and release notes, plus the teardowns' cited labs.** No leader was re-run in a VM for this page.
- **Release checks:**
  - StartOS and Omarchy returned "moved" from the GitHub releases API, so their rows use the latest commit on the default branch.
  - TrueNAS, Cosmos and Runtipi have no release in that API that could be read, so their rows use the commit read.
- **Effort sizes are estimates for one founder plus coding agents.** Re-size them once the wave-2 branches are merged.
- **umbrelOS was studied only.** Nothing on this page reproduces its code, assets or text. The rows describe its behaviour in our own words and cite file paths.
