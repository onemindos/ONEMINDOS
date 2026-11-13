<!-- SPDX-License-Identifier: Apache-2.0 -->
# umbrelOS 2 vs OneMind

**Date:** 2026-11-12 · **Status:** summary of the ten area studies in this folder. It changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md) and does not edit the contract. The epics are in [BACKLOG.md](../leap/BACKLOG.md) under "UMB" and tracked in [STATUS.md](../leap/STATUS.md); open founder questions are F-32 to F-60 in [DECISIONS-NEEDED.md](../leap/DECISIONS-NEEDED.md).

> **Explain it like I am the founder**
> Yes, umbrelOS has a desktop. Its web page looks like a computer desktop: wallpaper, a dock, an app grid, widgets and a right-click menu. It also has small native apps: a Mac menu-bar app, a Windows tray app and phone apps. The desktop look is the umbrelOS web page, not a native program.
> umbrelOS 2 is polished. It includes Files, Rewind (going back in time through backups), Photos with phone backup, virtual machines and AI agents over MCP. Its weak points are safety: AI agents act with the owner's full rights, app updates cannot be undone, backups are never test-restored, everyone in the house shares one login inside each app, and disk encryption uses the same passphrase on every box.
> OneMind matches the look and the features, built its own way. It wins where you said it matters: every disk, app or account change is a plan you approve, backups count only after a restore has been checked, photos stay on the phone until a checked backup holds them, every person signs in with a passkey, and agents can only request changes.

## Licence rule (applies to everything below)

umbrelOS is PolyForm Noncommercial 1.0.0 (checked at tag `2.1.0-beta.1`, commit `6f357e18d0a4`). OneMind is sold commercially. The studies **read and describe** umbrelOS code, architecture and flows and cite file paths. Nothing from umbrelOS (code, strings, UI text, icons, wallpapers or other assets) is copied into this repository, and its code is not paraphrased line by line. Every OneMind implementation is our own and uses components with permissive or separately shipped licences. Each adopting PR records the component's licence at a pinned version.

## Area studies

| Area | Study | Epic ids |
|---|---|---|
| OS, updates, events, network, reset | [system.md](system.md) | UMB-SYS |
| App store, install, updates, exposure | [apps-deploy.md](apps-deploy.md) | UMB-APP |
| AI agents over MCP | [mcp-agents.md](mcp-agents.md) | UMB-AGT |
| Home desktop, dock, widgets, customization | [desktop-ui.md](desktop-ui.md) | UMB-DESK |
| Disks, mirrors, health, encryption | [storage.md](storage.md) | UMB-STOR |
| Household accounts | [accounts.md](accounts.md) | UMB-ACCT |
| Native clients (desktop, phone, shares) | [clients.md](clients.md) | UMB-CLIENT |
| Files, Rewind, cloud import, backups | [files-backups.md](files-backups.md) | UMB-FILES |
| Photos | [photos.md](photos.md) | UMB-PHOTO |
| Virtual machines | [machines.md](machines.md) | UMB-MACH |

Epic `UMB-<area>-n` is epic `n` of that study. For example, UMB-STOR-4 is STOR-4 in storage.md and UMB-AGT-3 is U2-AGT-3 in mcp-agents.md. Three study ids changed: APPDEP-C1 became UMB-APP-0, APPDEP-C2 became UMB-APP-18 and ACCT-T1 became UMB-ACCT-13. The files study used STOR-1 and STOR-2 for its disk epics; those became UMB-STOR-13 and UMB-STOR-14. When an epic duplicated an existing leap epic or one from another study, it was merged into that epic; the merge table is in [BACKLOG.md](../leap/BACKLOG.md#umb-merged-into-existing-epics).

## Feature by feature

"Today" means merged on `main` unless a branch is named. Work on a named branch is not merged.

| Feature | umbrelOS 2.1 has | OneMind today | OneMind plan | How we beat it |
|---|---|---|---|---|
| Desktop look | Web desktop with wallpaper, greeting, paged app grid, dock with magnification, widgets, right-click menu and Search | Dashboard MVP (Home, Nodes, Market, Approvals). Home launcher, dock, widgets, command palette and appearance engine are on `feat/ui-leap` | UI-LEAP, UMB-DESK-0/1/6/7/9–16, CORE-DASH-8 | Home is a per-person document stored on the hub and changed through the API, so it syncs to every screen and the CLI. Pending approvals appear on Home. Every widget shows how old its data is. Our own wallpapers are contrast-tested in light and dark, and both layouts are tested with axe |
| Native clients | Mac menu-bar app, Windows tray app (WPF), iOS and Android apps. They find the box, sign in, mount shares and back up photos | Expo phone shell (Android build). A Tauri tray skeleton is on `feat/desktop-client` | UMB-CLIENT-0–3, 8–15 | A new device is a request the owner approves. Device keys cannot be copied off the device, so a copied credential file is useless. There is a Linux build. Approvals work from the tray. Laptop folders are backed up to the box |
| App store and install | Official and community stores, install dialog showing dependencies and folders | Manifest schema, validator and 3 seed apps. App gate and `scan.json` are on `feat/app-pipeline` | UMB-APP-0–5, 9, 10, 12–14, 18; CORE-SANDBOX-* | The install plan is bound by hash to what gets applied. Apps run in a sandbox (restricted pod security, default-deny network). The catalog is signed and community sources are pinned to a commit. Community apps are scanned on the box |
| App updates and removal | Pull and start with no undo. Uninstall deletes the app's data | Nothing yet for apps | CORE-UPDATE-5/6 (with UMB-APP-6), UMB-APP-5, UMB-APP-17 | A snapshot is taken first, then a health check runs and a failed update reverts by itself. An update that widens permissions needs a fresh approval. Removing an app keeps its data |
| App URLs and local HTTPS | Per-box CA without name constraints. Each app is on its own port | HTTP gateway. Mesh, app proxy and box CA designed on `feat/core-net` | CORE-SEC-1, CORE-NET-P1 (with UMB-APP-7/8) | A name-constrained ECDSA CA. Each app gets its own address behind the person's sign-in, and the app learns who that person is |
| Household accounts | One owner and members with passwords and TOTP. The owner sets each member's password | Owner token and agent principals (contract §11) | CORE-SEC-2, CORE-SEC-10 (with UMB-ACCT-3), UMB-ACCT-1, 2, 4–13 | Passkeys. Invites and recovery use enrolment links, so nobody learns anyone's password. Roles are owner, adult, child and guest. Single sign-on gives each person their own account inside apps. Children get time windows and can ask for an app |
| AI agents (MCP) | MCP clients act with the owner's rights and their writes take effect at once. Setup puts a token into chat | `/mcp` with 3 tools and agent principals on `feat/gateway-agent-mcp` | DEV-MCP-*, UMB-AGT-1, 3–6, 8–11 | Agents can only request changes, and the owner approves with a passkey. Pairing uses a code, so no secret appears in chat. Each agent gets its own scopes, expiry and kill switch. Logs are redacted for troubleshooting. A batch of file changes can be undone |
| Disks and redundancy | OpenZFS with stripe, raidz or mirror. HDD+SSD acceleration. Encryption with one fixed passphrase on every box | Disk inventory, SMART health, mirror status and dry-run plans on `feat/onemindd-storage` | CORE-SEC-5 (with UMB-STOR-1), UMB-STOR-0, 2–10, 12–14 | btrfs inside LUKS2 with a TPM2 key and a recovery key per box. Never a stripe without redundancy. Every disk operation is power-cut tested. Each wipe plan names the disk by its serial number |
| Disk health | SMART temperature, wear and pass/fail. USB disks are excluded | SMART verdicts (ok, warning, critical) on `feat/onemindd-storage` | UMB-STOR-3, 6 | Alerts show trends. USB disks are supported. Scrub results go into the audit log. The alert says which bay holds the disk to replace |
| Files | Full file manager in the core with trash, search, thumbnails and member shares | None | UMB-FILES-0–7 | Uploads resume after a dropped connection. Each person has their own space. Thumbnails are made in a sandbox with no network. Shares and folder grants are approved, audited actions, and agents ask for folders the same way |
| Network shares | SMB out (Samba) and SMB in (CIFS) | None | UMB-FILES-5, UMB-STOR-14, UMB-CLIENT-9 | Also NFS in and WebDAV out. SMB credentials are per person and per device and can be revoked. Mounts work on Linux too |
| Backups | Kopia, whole box, hourly. The repository key is a password cut to 64 bits and stored on the box. Restores are never tested | restic snapshot before each OS update (`internal/update`). Backup agent with three keys and pinned restic on `feat/onemindd-backup` | CORE-BACKUP-1–8, UMB-FILES-9, UMB-ACCT-12 | Random 256-bit keys, and the owner key exists only in the emergency kit. Each app has hooks for consistent dumps. Another box can be an append-only target. The backup badge turns green only after a scratch restore passes |
| Rewind | Timeline over snapshots, copy back | None | UMB-FILES-7 | Every restore is an action, and a snapshot is taken first, so the restore can be undone. Nothing needs to be mounted |
| Cloud import | rclone pulls from Google, Dropbox, OneDrive, WebDAV and iCloud, with sign-in through a vendor proxy | None | UMB-FILES-8–10 | No vendor proxy holds the tokens. Files deleted upstream go to Trash. A cloud drive can also be a backup target. Imports from any NAS or old server resume after interruption |
| Photos | Built-in Photos with phone backup on both OSes, timeline and map | Resumable phone backup with hash dedupe on `feat/mobile-photos` | UMB-PHOTO-0–13 | The phone frees space only for photos inside a checked backup. Uploads use HTTPS only and resume. The household can share libraries. The map and place names work offline. Optional search uses permissively licensed models. Immich can be attached read-only |
| OS updates | A/B slots. A new version is kept as soon as the daemon starts | TUF-verified updater, health gate, nightly security rebuild (#14, #15) | CORE-UPDATE-2/3/7 (with UMB-SYS-1, 2, 12), UMB-SYS-13 | Already ahead: a version is kept only after health checks pass, and rollback names the failing check. Next: apply is bound to the checked target, release notes are signed, and a bad release can be withdrawn |
| System controls | Factory reset, Wi-Fi and static IP, restart, move to new hardware | None | UMB-SYS-6, 8, 10; CORE-BACKUP-6 (with UMB-SYS-9) | Factory reset is a critical action: it needs a passkey and offers a final backup. Network changes revert by themselves unless confirmed. Moving to new hardware is a checked restore |
| Live usage and events | Per-app usage, in-process event bus | Node heartbeat over NATS | DEV-API-8 (with UMB-SYS-3), UMB-DESK-12 (with UMB-SYS-5) | Covers every node in the house, and stale values are labelled. One NATS stream feeds the UI, the phone, the desktop app, agents and alerts |
| Notifications | Local only | None | CORE-NOTIFY-1–7 (with UMB-SYS-4) | Push to phones (UnifiedPush and APNs). Tapping a notification opens the approval card |
| Virtual machines | libvirt/QEMU, Windows 11, browser console, USB passthrough. Agents control the VM's screen, keyboard and mouse | None | UMB-MACH-0–16 (timing is F-57) | An agent gets a time-boxed control lease that the owner approves. The machine can run on any box in the house. Backups are tested by booting the copy. GPU passthrough on the Pro box |
| More than one box | One box | onemindd node agent and heartbeat | CORE-FABRIC-* | Many boxes act as one: apps are placed by each box's capabilities, and updates roll out in stages |

## Top 15 moves, ranked by impact on the founder focus

Ranking: lost data or a broken box first, then the daily experience of the household, then reach.

| # | Move | Epics | Why this rank |
|---|---|---|---|
| 1 | **Disks that cannot silently lose data:** btrfs mirror inside LUKS2, power-cut-safe add, replace and remove, recovery screen | CORE-SEC-5, UMB-STOR-0, 2–5, 8 | Losing data is the only failure a household cannot undo. umbrelOS ships a fixed passphrase and allows a stripe with no redundancy |
| 2 | **Backups proven by restore,** plus Rewind with undo | CORE-BACKUP-2–8, UMB-FILES-7 | umbrelOS never test-restores. Our badge turns green only after a checked restore |
| 3 | **Phone photo backup with safe-to-free** | UMB-PHOTO-3, 4, 8 | Photos are what families most fear losing. The phone frees space only after a checked backup holds the photo |
| 4 | **Deployments that never fail silently:** plan bound by hash, snapshot, health check, automatic revert, remove keeps data | CORE-SANDBOX-2, CORE-UPDATE-5/6, UMB-APP-3–5 | A founder rule. umbrelOS updates cannot be undone |
| 5 | **Accounts for the whole house:** passkeys, roles, single sign-on into apps | CORE-SEC-2, CORE-SEC-10, UMB-ACCT-1, 2, 4–7, 10 | Without this every app has one shared login. It is also required for per-person Files, Photos and Home |
| 6 | **Agents request, the owner approves,** with pairing that keeps secrets out of chat | DEV-MCP-2/3, UMB-AGT-1, 3, 5, 6, 10 | This is our clearest difference from umbrelOS, and the demo shows it |
| 7 | **Home desktop wired to the hub:** per-person Home, dock, widgets that show freshness, jobs tray | UI-LEAP, UMB-DESK-0, 1, 6, 9, CORE-DASH-8 | The look you asked for. The UI already exists on `feat/ui-leap` and needs the hub side |
| 8 | **Files as a core page** with resumable uploads, per-person spaces and folder grants | UMB-FILES-0–4, 6 | Needed for photos, cloud import, shares and agent file access |
| 9 | **Devices are requests,** with keys that cannot be copied | UMB-CLIENT-0–3, 14 | Every phone and laptop becomes an approved principal that can be revoked |
| 10 | **Desktop companion:** tray app, approvals, laptop backup, signed releases | UMB-CLIENT-8, 10–12 | Answers the "does it have a desktop app" question with something umbrelOS lacks: laptop backup, approvals and Linux |
| 11 | **Trusted app supply:** signed catalog, pinned community sources, richer app page | UMB-APP-1, 2, 10, 13, 18 | Keeps the Market safe as it grows past the seed apps |
| 12 | **Photos app:** timeline, household sharing, offline map, importers | UMB-PHOTO-1, 2, 5–7, 11 | Matches umbrelOS Photos and beats it on sharing and privacy |
| 13 | **System controls:** factory reset, Wi-Fi and static IP with revert, restart, withdrawing a bad release, moving to new hardware | UMB-SYS-6, 8, 10, 13, CORE-BACKUP-6 | Table stakes. Each one is a safe, audited action |
| 14 | **Bring data in:** cloud import, NAS mounts, migration from another server | UMB-FILES-8–10, UMB-STOR-13, 14 | Makes switching to OneMind easy |
| 15 | **Virtual machines with control leases** | UMB-MACH-0–5, 13 | Matches a headline umbrelOS feature. Planned for after the leap's core (F-57) |

## What was not taken, and why

- Tor exposure and native TLS passthrough for apps (apps-deploy §5): no current app needs them.
- A native phone Home with wallpaper and tiles (clients C17): on the phone, Home stays a status screen. Customization lives in the dashboard.
- HDD+SSD acceleration and a ZFS "NAS tier" (storage): btrfs has no tiering. UMB-STOR-12 decides after measuring.
- Machines and agents disagree: the agents study accepted VMs as a gap for this cycle, while the machines study plans them. F-57 decides.

## Re-score against `main` (2026-11-12, Wave G #5)

> **Explain it like I am the founder**
> The table above says "Today" means merged on `main`, but it was written before most of the leap landed. This section re-checks every row against the code on `origin/main` (`ad81f84`) and the open PR list, not against STATUS.md. Short version: **the look is there, the safety backbone is there as daemons and APIs, and the glue between them and the dashboard is what is missing.** For example the backup agent, the disk inventory, the OS updater, passkeys and notifications all exist and have tests, but the dashboard cannot yet show or drive any of them, and `main` still cannot start, stop or update an app. The ranked streams that follow from this are in [docs/strategy/umbrel-parity.md](../strategy/umbrel-parity.md) section 0.3.

Marks: `done-on-main` (code and tests on `origin/main`), `in-open-PR (#n)`, `not started` (nothing on `main` or in an open PR). "Partial" says what is missing. Paths are in this repository.

| Feature | Mark | What is on `main` (evidence), and what is not |
|---|---|---|
| Desktop look | done-on-main (partial) | Wallpapers, accents, density: `ui/src/customize/`; Home launcher, dock, widgets: `ui/src/home/`; command palette: `ui/src/shell/CommandPalette.tsx`; wired in `dashboard/src/pages/Home.tsx` and `dashboard/src/shell/Shell.tsx` (#29, #73). Not done: the per-person Home document on the hub (UMB-DESK-0/1; preferences are browser-only, `dashboard/src/data/prefs.ts`) |
| Native clients | done-on-main (partial) | Phone: `mobile/` with Approvals, Inbox, Push, Photos screens (#21, #34, #63). Desktop tray: `desktop/src-tauri/src/{approvals,inbox,discovery}.rs` (#33, #51). Not done: device keys as approved requests, laptop backup, signed desktop releases (UMB-CLIENT-3, 10 to 12) |
| App store and install | done-on-main (partial) | Schema, validator, app gate, `scan.json` (#11, #25: `sdk/tools/app-gate`); Market UI with categories (`ui/src/store/`); 19 apps in `apps/`. Install plan bound by hash: **in-open-PR (#72)**. Signed catalog and pinned community sources: **in-open-PR (#57)**, contract #47. Market batches 1: #61 merged, batches 2 to 5: #49 and #62 open |
| App updates and removal | removal done-on-main; updates **in-open-PR (#72)** | `app.remove` keeps data (`core/onemind_core/executors.py`). No `app.update`, snapshot-first or automatic revert on `main` |
| App URLs and local HTTPS | not started (partial) | Box CA `core/onemind_core/ca.py`, mesh `internal/mesh`, app proxy `core/onemind_core/proxy.py` with tests, but the proxy is "NOT MOUNTED YET" and `app.py` does not register it |
| Household accounts | done-on-main (API); dashboard not started | Passkeys, sessions, TOTP, users, roles, per-app sharing, `/v1/me` in `core/onemind_core/routers/identity.py` (#41). `dashboard/src/pages/SignIn.tsx` still takes a static token; the household settings sections say "coming" |
| AI agents (MCP) | done-on-main (partial) | `/mcp` with agent principals, request-only tool, untrusted-content marking: `core/onemind_core/routers/mcp.py`, `core/onemind_core/mcp/` (#24, #48); stdio bridge `internal/mcpbridge`. Not done: per-agent scope UI, pairing by code, withdraw/preview tools (DEV-MCP-2/3 todo) |
| Disks and redundancy | agent done-on-main; gateway and UI not started | `internal/storage` (inventory, btrfs, SMART, dry-run plans, #31). No `/v1/storage` route; Settings Storage has no API (`dashboard/src/pages/Settings.tsx`) |
| Disk health | agent done-on-main; alerts not wired | SMART verdicts in `internal/storage/smart.go`; no alert path from them in `core/onemind_core/notify/catalogue.py` |
| Files | **in-open-PR (#77)** | Gateway file API, tus uploads, confined paths, folder grants (FILES-1/2/6); nothing on `main` |
| Network shares | not started | |
| Backups | agent done-on-main; gateway and UI not started | `internal/backup` (restic pinned, schedule, verify, rewind, #32). No `/v1/backups/*` route on `main`; the verified-restore badge has no data |
| Rewind | agent done-on-main; UI not started | `internal/backup/rewind.go` |
| Cloud import | not started | |
| Photos | done-on-main (phone side) | Resumable phone backup with hash dedupe: `mobile/src/photos/` (#34). Not done: hub timeline, sharing, map, importers (UMB-PHOTO-1, 2, 5 to 7) |
| OS updates | done-on-main (daemon); gateway and UI not started | `internal/update` (TUF, window, restic snapshot, health gate; #15), nightly security rebuild (#14). No `/v1/os/*` route, Updates screen "coming" |
| System controls | not started | No factory reset, Wi-Fi, restart or move-to-new-hardware action types registered |
| Live usage and events | done-on-main (API) | `GET /v1/events` (SSE), `/v1/nodes/{id}/metrics`, `/v1/apps/{id}/metrics`, `/v1/monitoring/summary`; dashboard client calls none of the metrics routes |
| Notifications | done-on-main (API, partial clients) | `/v1/alerts`, `/v1/notifications*`, `/v1/push/*` (#44); phone inbox and push registration (#63). Dashboard bell is fed by approvals only |
| Virtual machines | not started (spike only) | Machines runtime spike merged (#70, docs and lab kit only; F-57 still open) |
| More than one box | done-on-main (partial) | onemindd node agent and heartbeat (#7), mesh and NATS leaf (#37), `/v1/nodes`. Not done: join approval route and fabric placement (CORE-FABRIC; `docs/leap/fabric/EPICS.md` has the plan) |

### Top 15 moves: where each stands

| # | Move | Mark |
|---|---|---|
| 1 | Disks that cannot silently lose data | agent done-on-main (#31); gateway, UI, LUKS/TPM2 not started |
| 2 | Backups proven by restore, Rewind | agent done-on-main (#32); no gateway or UI |
| 3 | Phone photo backup with safe-to-free | phone side done-on-main (#34); safe-to-free needs the backup gateway |
| 4 | Deployments that never fail silently | in-open-PR (#72) |
| 5 | Accounts for the whole house | API done-on-main (#41); dashboard not started |
| 6 | Agents request, owner approves | done-on-main for `/mcp` and passkey approvals; pairing and per-agent scopes not started |
| 7 | Home desktop wired to the hub | done-on-main in the browser; hub storage not started |
| 8 | Files as a core page | in-open-PR (#77) |
| 9 | Devices are requests | not started |
| 10 | Desktop companion | tray done-on-main (#33, #51); laptop backup and signed releases not started |
| 11 | Trusted app supply | partial (scan gate done-on-main; signed catalog and pinned sources in #57) |
| 12 | Photos app | not started on the hub |
| 13 | System controls | not started |
| 14 | Bring data in | not started (a migration kit for clusters is in #76) |
| 15 | Virtual machines | not started (spike only) |

**Why the pattern matters (plain words):** the daemons were built first on purpose, because the safe way to do a disk or backup change is a small, tested program on the box. What is missing is the middle layer, gateway routes that file each action for approval, and the screens that show the result. That is why the next streams (see the parity page, section 0.3) are mostly "wire what exists" and not "build something new".
