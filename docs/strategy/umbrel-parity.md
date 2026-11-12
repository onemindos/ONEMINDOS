<!-- SPDX-License-Identifier: Apache-2.0 -->
# umbrelOS and competitor parity: UI and deployment

**Date:** 2026-11-12 · **Status:** audit and proposal for the founder; changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md) or the contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md).
**Founder brief (2026-11-12):** "the UI is major for me: it must look good and have customizations"; match and beat umbrelOS's polish and deployment experience; **categorize apps and deployment**; ship fast.
**Builds on:** [`core-alignment.md`](core-alignment.md) (backlog IDs such as APP-P1 are defined there), [`docs/design/`](../design/) (PRINCIPLES, IA, TOKENS, COMPONENTS, PLUGIN-UI), [`ui/`](../../ui/) (`@onemind/ui`), [`docs/leap/core/DASHBOARD.md`](../leap/core/DASHBOARD.md), [`MOBILE.md`](../leap/core/MOBILE.md), [`PLUGIN-SDK.md`](../leap/dev/PLUGIN-SDK.md), contract §3, §4, §9.3, §11, and the teardowns in [`research-output/02-competitors/`](../../research-output/02-competitors/).
**Core rules that do not move:** agents request and the owner approves (the approvals UI is first-class); the UI is honest about stale and offline state; headless first (every UI action is an API or CLI action).

> ### In plain words
> umbrelOS looks better than OneMind today because it has spent years on the parts a person touches first: a wallpaper and greeting, an app store with categories and screenshots, a stepped install review, a progress "island" while things install, per-app settings (credentials, environment, folders), and a settings app that covers everything from 2FA to factory reset in 29 languages.
>
> OneMind's design system and mocks (`ui/`) already cover the *serious* screens umbrelOS lacks: approvals, an audit timeline, multi-node fabric, honest stale/offline states and backups that say when a restore was last verified. What is missing is the **delight and customization layer** (wallpaper, accent colour, widgets, launcher, command palette, install progress) and the **wiring** (the mocks run on fixtures; the live dashboard on `main` is still the 5-screen MVP).
>
> On deployment, umbrelOS is a mature Docker Compose app manager with a per-app login gateway, start/stop/restart/update/logs, dependencies with alternatives, and community stores. It does **not** snapshot before an app update and has no rollback (a failed update leaves the app "unknown"). OneMind today can only install and remove through approval. The fastest route to parity is: **categories and deployment kinds in the manifest (§2), app lifecycle verbs, a per-app gateway URL, and health-gated updates**, then the screens on top.
>
> §5 is the ranked list. 12 items are P0.

---

## 1. Method and pinned sources

Every row below names the file or doc read. **Licence rule:** umbrelOS is PolyForm Noncommercial 1.0.0 (`getumbrel/umbrel@c43beed:LICENSE.md`): **studied, nothing copied** (no code, assets, icons, wallpapers or text). Only MIT/BSD/Apache-2.0 code may be copied, with a `NOTICE` entry; no code is copied by this document.

| Project | Repository and commit read | Date of commit | Licence | Use |
|---|---|---|---|---|
| umbrelOS | `getumbrel/umbrel@c43beed` (`packages/ui`, `packages/umbreld`, `releases/`) | 2026-11-04 ("Archive umbrelOS 2.1 Beta 1") | PolyForm NC 1.0.0 | study only |
| umbrelOS app catalog | `getumbrel/umbrel-apps@3a08738` | — | per app | study only (category counts) |
| Home Assistant frontend | `home-assistant/frontend@9caad65` | 2026-11-12 | Apache-2.0 | patterns |
| StartOS | `Start9Labs/start-os@246876d` | 2026-11-10 | MIT | patterns |
| CasaOS UI / App Store | `IceWhaleTech/CasaOS-UI@400a22c`, `CasaOS-AppStore@07178f6` | 2026-10-12 | Apache-2.0 | patterns |
| ZimaOS | `IceWhaleTech/ZimaOS@8bc1599` (release notes and scripts only; OS source is closed) | 2026-10-15 | **no licence file** | study only |
| Olares | `beclab/Olares@e7fe1c96`; teardown `research-output/02-competitors/olares.md` | 2026-11-10 | AGPL-3.0 + legacy NC | study only |
| Cosmos | `azukaar/Cosmos-Server@69c5303` | 2026-08-30 | Apache-2.0 **+ Commons Clause** | study only |
| Runtipi | `runtipi/runtipi@a8f22ed` | 2026-11-03 | GPL-3.0 | study only |

umbrelOS release notes read: `releases/2.1.0-beta.1-release-notes.md` (Documents in Files; Android and Windows apps; Machines on the home network with USB passthrough and clipboard; SAS HBA support; newer kernel and NVIDIA driver). The in-app changelog is `packages/ui/src/routes/whats-new-modal.tsx` + `whats-new.ts` (shown once after crossing a version cutoff).

Paths below are shortened: **U:** = `getumbrel/umbrel@c43beed:packages/ui/src/`, **D:** = `getumbrel/umbrel@c43beed:packages/umbreld/source/modules/`, **OM:** = this repository.

**Priority:** **P0** = needed for the founder's daily use or the first impression ("looks good, has customizations"); **P1** = parity a daily user will notice within weeks; **P2** = later or out of scope for the core OS. **Effort:** **S** ≤ 2 days, **M** ≤ 1 week, **L** > 1 week (one engineer with an agent).

---

## 2. Categorization (founder ask)

### 2.1 App categories

**What the leaders do:**

| Leader | Vocabulary | Source |
|---|---|---|
| umbrelOS | Fixed list of 10 (`files`, `bitcoin`, `media`, `networking`, `social`, `automation`, `finance`, `ai`, `developer`, `crypto`), a nav order, plus **Discover** and **All apps** rails ahead of them; unknown categories are tolerated and shown dynamically. Catalog spread: files 108, bitcoin 88, networking 47, media 31, developer 30, social 26, ai 25, automation 20, finance 17, crypto 7 | U:`features/app-store/constants.ts`, `components/category-rail.tsx`, `discover.tsx`; `umbrel-apps@3a08738:*/umbrel-app.yml` |
| Runtipi | Enum of 15 (`network`, `media`, `development`, `automation`, `social`, `utilities`, `photography`, `security`, `featured`, `books`, `data`, `music`, `finance`, `gaming`, `ai`); apps carry a **list** of categories; the API filters by one | `runtipi@a8f22ed:packages/common/src/schemas/app-info.ts` |
| CasaOS | 9 categories (Media, Productivity, Home, Networking, AI, Finance, Social, Developer, Others) + a separate `featured-apps.json` | `CasaOS-AppStore@07178f6:category-list.json` |
| HA | No store categories for apps; organizes by *integration domain* and user-defined **areas, labels and categories** for entities | `frontend@9caad65:src/panels/config/{category,labels,areas}` |

**What OneMind has:** `metadata.category` is a **free-text slug** ("Market category slug, e.g. monitoring", `OM:sdk/schema/onemind.app.schema.json`). The three shipped apps use `home-automation`, `monitoring`, `notifications`; the design-system fixtures use `home`, `ai`, `automation`, `security`, `media`, `other` (`OM:ui/demo/src/fixtures.ts`), so the mock and the catalog already disagree. The demo has category chips (`OM:ui/demo/src/screens/Apps.tsx`); the live Market shows the slug as text (`OM:dashboard/src/pages/Market.tsx`).

**Proposal (contract amendment, PD-01):** one controlled list, one primary category per app plus up to two `tags`, validated in the schema and by `sdk/tools/validate-apps`. The list is shaped by what the founder runs (C2/ISR, AI agents, home, media) and kept short enough for a phone rail:

| Slug | Label | Covers | Seed apps |
|---|---|---|---|
| `home` | Home and automation | home automation, cameras, presence, energy | Home Assistant |
| `ai` | AI and agents | local models, agent runtimes, MCP servers | Hermes (wave 2), Ollama |
| `media` | Media | photos, video, music, books | Immich, Jellyfin |
| `files` | Files and sync | file sync, documents, notes | Nextcloud, Syncthing |
| `productivity` | Productivity | calendars, wikis, task tools, bookmarks | |
| `monitoring` | Monitoring | uptime, metrics, logs, dashboards | Uptime Kuma |
| `notifications` | Messaging and alerts | push, chat bridges, email | ntfy |
| `networking` | Networking and security | DNS, VPN, ad blocking, identity, password vaults | AdGuard Home |
| `data` | Databases and data | databases, queues, object storage, time series | |
| `developer` | Developer | Git, CI, code editors, registries | |
| `edge` | Robotics and edge | robot middleware, drones, ROS, sensors, TAK | (founder domain; no competitor has it) |
| `finance` | Finance | budgeting, accounting, wallets | |
| `social` | Social | federated social, forums | |
| `other` | Other | anything else (CI warns, so it stays rare) | |

**Virtual rails in the Market (not categories):** Discover (editorial, see PU-11), All, **Installed**, **Updates** (with count), **Your deployments** (kinds D4–D5 below). Search spans name, tagline, description, category and tags.

### 2.2 Deployment kinds

umbrelOS has three origins with different trust: the official store, **community app stores** added by Git URL (U:`modules/community-app-store/`, D:`apps/app-store.ts` `addRepository`), and **Machines** (full VMs, D:`machines/`). It badges community apps (U:`modules/community-app-store/community-badge.tsx`) but otherwise treats them the same. OneMind should **name every kind of thing that runs**, show the kind as a badge, and let the kind decide the trust gate, the update path, the exposure default and the backup default.

| Kind | What it is | Who may request | Trust gate | Updates | Exposure default | Backup default | Badge |
|---|---|---|---|---|---|---|---|
| **D1 Market · verified** | Catalog app, tier `verified` (contract §9.3) | owner, agent | daily scan, pinned digests, signed catalog | catalog feed; health-gated (APP-B1) | private (gateway login) | volumes on | none (default) |
| **D2 Market · community** | Catalog app, tier `community` | owner, agent | same scan gate; warning in install review | catalog feed; health-gated | private | volumes on | "Community" |
| **D3 Community source** | Another catalog added by Git URL, **pinned to a commit** (umbrelOS follows a mutable branch head, core-alignment §4.3) | owner only adds a source; then as D2 | same scan gate run on the box; source must be added through approval | source commit moves only through approval | private | volumes on | "From <source>" |
| **D4 Custom app** | Compose file or folder imported as a private app (APP-P4) | owner, agent | scan gate; manifest generated and shown in review | manual or watched (DEP-B1) | private | volumes on | "Custom" |
| **D5 Your service** | Kustomize, Helm or Git source deployed by the owner (DEP-P1) | owner, agent (proposal only) | scan gate; diff + digests in the approval | watched Git: each commit is a request (DEP-B1); history and rollback (DEP-P2) | private | volumes on | "Deployment" |
| **D6 System** | Parts of OneMind itself (gateway, bus, k3s add-ons, updater) | system | signed OS release (TUF) | OS update with A/B slot (OSU-*) | n/a | system backup | "System" (cannot be removed from the UI) |
| **D7 Agent** | An app that runs with its own agent principal (contract §11.2), e.g. Hermes | owner | as its source kind, plus a scopes review step | as its source kind | private | volumes on | "Agent" (violet tone, P1) |
| **D8 Machine** | A full VM (umbrelOS Machines) | — | — | — | — | — | **P2, not planned for the core** |

**Exposure categories** (orthogonal to kind, each change is its own request): `private` (LAN through the gateway login; default) → `remote` (owner's overlay network, REM-P1) → `public` (internet; separate approval with a warning, REM-B1). umbrelOS has no public-exposure flow in the OS (remote access is Tailscale or Tor, D:`system/tailscale.ts`, `apps/routes.ts` `setTorEnabled`).

### 2.3 Lifecycle states (honest vocabulary)

umbrelOS maps both `unknown` and `stopped` to the same word, "Offline" (U:`modules/app-store/app-state-strings.ts`). OneMind's P2 rule ("unknown is a state") needs distinct words. Proposed app states, shared by the API, the CLI and every pill:

`available` · `requested` (awaiting approval) · `installing` (with step and %) · `running` · `starting` · `stopping` · `stopped` (by the owner) · `updating` · `reverting` (health gate failed) · `failed` (with reason) · `degraded` (probe failing) · `stale` (no report for 30 s) · `unknown` (no report for 120 s, or never) · `removing`.

---

## 3. UI parity, area by area

Columns: what umbrelOS does (path), what the others do (brief), what OneMind has (path), the gap with ID, priority and effort. "Mock" means a static screen in `OM:ui/demo` on fixtures; "live" means `OM:dashboard/src` on `main`.

### 3.1 Onboarding and first run

| | |
|---|---|
| **umbrelOS** | Browser wizard: create account (name, password with "there is no way to reset it" note), choose storage (internal, external drive, RAID/FailSafe with SSD health), **restore from a backup**, "You're all set"; animated background; recover an existing install after a re-flash. U:`routes/onboarding/{create-account,account-created,external-drive,restore}.tsx`, `routes/onboarding/raid/`, `components/onboarding-background.tsx`; D:`backups/backups-restore-onboarding.vm.test.ts` |
| **Others** | HA: onboarding offers restore. StartOS: setup service with fresh / restore / transfer (`start-core/src/setup.rs`). Olares: requires the LarePass phone app. CasaOS/Runtipi: `curl \| bash`, then a register page. |
| **OneMind** | Live: SignIn asks for a bearer token (`OM:dashboard/src/pages/SignIn.tsx`). No wizard, no mock. ONB-P1/P3/B1/B2 are specified in core-alignment §4.1. |
| **Gap** | **PU-05 · P0 · M** First-run wizard (ONB-P1) with a look as considered as umbrelOS's: name the box, create the owner (passkey first, password fallback), time zone, **pick a wallpaper and accent** (sets the tone of the product in the first minute), emergency kit that cannot be skipped (ONB-B2), optional "restore from a backup" (ONB-P3, P1). Headless twin `onemind init` (ONB-B1). |

### 3.2 Home (wallpaper, widgets, dock, app grid, greeting, search)

| | |
|---|---|
| **umbrelOS** | Full-screen **wallpaper** (28 built-in; each carries a brand colour that re-tints the UI accent: U:`providers/wallpaper.tsx` sets `--color-brand` from the wallpaper; D:`user/wallpapers.ts`); **greeting** by time of day with the person's name (U:`modules/desktop/greeting-message.ts`); **paged app grid** with context menu (U:`modules/desktop/app-grid/`, `desktop-context-menu.tsx`); **dock** with magnification and tuck (U:`modules/desktop/dock.tsx`, `dock-tuck.ts`); **up to 3 widgets** per account from typed templates, chosen in an edit-widgets screen (U:`routes/edit-widgets/`, `modules/widgets/`; limit `MAX_ALLOWED_WIDGETS = 3` in D:`widgets/routes.ts`); **web shortcuts** (bookmark tiles with fetched favicons, D:`shortcuts/`); **command palette** over apps, settings, files, machines (U:`components/cmdk*.tsx`); **floating island** for long jobs (U:`modules/floating-island/`). |
| **Others** | CasaOS: system widgets (CPU, disks, network, clock) on the home page (`CasaOS-UI@400a22c:src/widgets/`). ZimaOS 1.8: spotlight search across features and content (release notes). HA: user-built dashboards. Olares: a web desktop with windows. Cosmos: home page with app tiles and a background (`client/src/pages/home`). |
| **OneMind** | Mock Home: greeting (static "Good afternoon"), four stat tiles, "Needs you" with approval cards, app tiles, recent activity (`OM:ui/demo/src/screens/Home.tsx`); typed widgets specified (`OM:docs/design/PLUGIN-UI.md` §2) but not built; ThemeSwitch System/Light/Dark is the only customization (`OM:ui/src/lib/theme.ts`); custom themes are "phase 2" (`OM:docs/design/TOKENS.md` §6). Live Home: counts and lists (`OM:dashboard/src/pages/Home.tsx`). |
| **Gaps** | **PU-03 · P0 · M Appearance and customization:** a set of **our own generated wallpapers** (SVG/CSS gradients and patterns made for OneMind; no umbrelOS asset), each with a declared accent; or the person picks an accent from 6–8 presets; density (comfortable/compact); "reduce transparency"; all stored **per person on the hub** (an API field, so the phone matches), with `localStorage` only as a cache. Every accent ships only if the token contrast test passes (`OM:ui/src/tokens/tokens.test.ts`). **PU-04 · P0 · M Home as launcher:** greeting with the person's name and time of day; the app grid opens apps (needs PD-02); pin/reorder apps; edit-widgets sheet (choose from apps' typed widgets, limit 4); "Needs you" stays first (P1, P3). A dock is **not** proposed (a sidebar and bottom tabs already exist, IA §1); pinned apps in the sidebar give the same one-click reach. **PU-10 · P0 · S Command palette** (UX-P3): apps, nodes, settings, actions, and "request …" commands that create actions. **PU-12 · P1 · S System widgets** (CPU, memory, disk, temperature per node, with freshness) as built-in typed widgets. **PU-13 · P2 · S Web shortcuts** (bookmark tiles; favicons fetched by the gateway, not the browser). |

### 3.3 App Store (Market)

| | |
|---|---|
| **umbrelOS** | Storefront: **Discover** with editorial sections from a remote feed that falls back to the local registry when offline (U:`features/app-store/data/storefront.ts`, `constants.ts` `APP_STORE_REMOTE_API_BASE`), category rail with small 3D category icons, sort control, virtualized grid, search (U:`features/app-store/components/`, `data/search.ts`); **app page** with gallery of screenshots (preloaded), tagline, developer, release notes, dependencies, website/support (D:`apps/schema.ts` fields `tagline`, `gallery`, `releaseNotes`, `dependencies`, `permissions`, `installSize`, `defaultUsername`, `defaultPassword`); **install review** stepped dialog: required apps (with alternatives), folder access, GPU (U:`modules/app-store/install-review-dialog.tsx`, `select-dependencies-dialog.tsx`, `dependency-alternatives.ts`); install progress on the button and in the island (U:`components/progress-button.tsx`, `install-button.tsx`); **updates** shelf and dialog with per-app release notes, "Update all" (U:`components/updates-shelf.tsx`, `updates-dialog.tsx`, `data/releases.ts`); "OS update required" guard (U:`modules/app-store/os-update-required.tsx`); community stores dialog. |
| **Others** | StartOS: marketplace + **sideload** (`portal/routes/marketplace`, `sideload`). HA: app store with repositories and a security rating (`src/panels/config/apps/ha-config-apps-{available,registries}.ts`). Runtipi: multi-category, per-app form fields typed (`FIELD_TYPES` in `app-info.ts`). CasaOS: featured list + categories. Olares: permissions shown at install. Cosmos: market + "new install" wizard (`client/src/pages/{market,newInstall}`). |
| **OneMind** | Mock: search box, category chips, Installed and Market cards with tier, licence, archs, memory and the reason Install is disabled (`OM:ui/demo/src/screens/Apps.tsx`); app page with TrustCard, placement and Remove dialog (`AppPage.tsx`, `OM:ui/src/components/TrustCard.tsx`). Live: Market list with Request install (`OM:dashboard/src/pages/Market.tsx`). Install review is specified (IA §2.3) but not built. |
| **Gaps** | **PU-02 · P0 · S Categories and rails** from §2.1 (category rail on desktop, chips on phone, Discover/All/Installed/Updates/Your deployments, search over tags). **PU-06 · P0 · M Install flow:** Request install → **install review** (steps that apply only: dependencies, volumes and folders, GPU, ports, exposure, "It will be able to" permissions, agent scopes for D7) → the approval card (or straight to approve when the owner is the requester, still recorded) → **progress** on the card and in a **jobs tray** (pull, create, start, health check; % from the executor) → "Open". **PU-08 · P0 · S Updates rail:** count badge, per-app release notes, "Request all updates" as one batched request. **PU-11 · P1 · M App page richness:** tagline, screenshots gallery (stored in the app folder, source recorded), "What's new in this version", developer and support links, install size; Discover with 3–4 curated rows from a file in the repo (no remote feed needed; works offline). **PU-14 · P1 · S Category icons** drawn for OneMind in the existing icon set (`OM:ui/src/components/Icon.tsx`). |

### 3.4 Installed-app management

| | |
|---|---|
| **umbrelOS** | Per app: open (launch dialog that can show **default credentials before opening**, U:`modules/app-store/app-page/app-launch-dialog.tsx`), **settings** split into credentials, environment variables, storage (move the data root, folder access) and advanced (U:`app-page/app-settings-{credentials,environment,storage,advanced}.tsx`), restart, start, stop, update, **logs** (troubleshoot screen, U:`routes/settings/troubleshoot/app.tsx`), **terminal into the app** (U:`routes/settings/terminal/app.tsx`), uninstall with a dialog that names where data lives and **deletes it** ("The app will be uninstalled and its data will be deleted"; `public/locales/en.json` key `app.uninstall.confirm.description-internal`), "uninstall these first" when others depend on it (U:`modules/apps/uninstall-these-first-dialog.tsx`), share an app with other users (`app-share-users-dialog.tsx`), exclude from backups. API: D:`apps/routes.ts` (`restart`, `start`, `stop`, `update`, `logs`, `setSettings`, `moveDataRoot`, `dependents`, `backupIgnore`). |
| **Others** | HA app view: info, configuration, log, documentation tabs (`src/panels/config/apps/app-view/{info,config,log,documentation}`). StartOS service page: about, actions, instructions, interfaces, logs, outbound traffic (`portal/routes/services/routes/`). Runtipi: snapshot + restore on failed update (teardown). |
| **OneMind** | Mock app page: Open, Update, Restart, Remove (keeps data), Settings/Data/Logs/History sections described (`OM:ui/demo/src/screens/AppPage.tsx`, IA §2.3). API: only `app.install` and `app.remove` (contract §3). |
| **Gaps** | **PU-07 · P0 · M App detail, wired:** status with the §2.3 states, Open, Stop/Start, Restart, Update, Settings (schema form, PLUGIN-UI X4), **Credentials** card (default username, generated password shown on demand with a reveal and copy, never in logs), Logs (tail, follow, download), History (from the audit log), Remove with **keep data default** and a separate "Delete data…" request (APP-P2). Every button is a request (P1) and shows its API/CLI equivalent (UX-B2). **PU-15 · P2 · M Terminal into an app** (only as an owner-approved, time-boxed, audited session; agents never). |

### 3.5 Files

| | |
|---|---|
| **umbrelOS** | A full file manager: list/grid, upload/download with transfers, trash and restore, favorites, recents, search index, thumbnails, archives, network shares (SMB/NFS), cloud drives (rclone/WebDAV), "Rewind" snapshots, document viewer and editor (2.1), sharing with members. U:`features/files/`; D:`files/`. |
| **Others** | CasaOS/ZimaOS: file manager built in. StartOS, HA: none (apps provide it). |
| **OneMind** | None; Files is explicitly not in v0 navigation (IA §1). |
| **Gap** | **PU-16 · P2 · L** Do not build a file manager in the core. Offer a Files app in the Market (D1) and a "Browse volume" read-only view per app for backups and restore (needed by BAK-P*). Revisit when the founder asks. |

### 3.6 Terminal

| | |
|---|---|
| **umbrelOS** | Web terminal to the host and to each app (U:`routes/settings/terminal/{umbrelos,app}.tsx`, `terminal-connection.ts`). |
| **Others** | StartOS: SSH key management (`system/routes/ssh`). Cosmos: container terminal. |
| **OneMind** | None. Headless-first means the CLI already is the terminal path. |
| **Gap** | **PU-15 · P2 · M** (as above). Host terminal stays out of the browser; `onemind` CLI over SSH with keys managed in Settings (P1, S, part of PU-19). |

### 3.7 System widgets and live stats

| | |
|---|---|
| **umbrelOS** | Live usage screen: CPU, memory, storage and GPU per app, temperature (U:`routes/live-usage.tsx`, `routes/settings/_components/{cpu,memory,cpu-temperature}-card-content.tsx`; D:`system/routes.ts` `cpuUsage`, `memoryUsage`, `gpuUsage`, `cpuTemperature`; D:`system/system-widgets.ts`). |
| **Others** | StartOS: metrics page (`portal/routes/metrics`). CasaOS: CPU/disk/network widgets. HA: hardware and system health panels. |
| **OneMind** | NodeCard with memory and disk meters, freshness (`OM:ui/src/components/NodeCard.tsx`); heartbeat has the numbers (contract §2). No per-app usage. |
| **Gap** | **PU-12 · P1 · S** (system widgets) and **PU-17 · P1 · M Live usage**: per node and per app CPU/memory/disk from the metrics already in the cluster, shown with the freshness rule; it is fleet-wide, which umbrelOS (one box) cannot be. |

### 3.8 Settings

| Setting | umbrelOS (U:`routes/settings/…`) | Others | OneMind | Gap |
|---|---|---|---|---|
| Account, name, password, avatar | `change-name.tsx`, `change-password.tsx`, `modules/auth/account-avatar-editor.tsx` | HA profile (`src/panels/profile/`) | Mock Settings: People list (`OM:ui/demo/src/screens/Settings.tsx`) | **PU-09 · P0 · M** real login (SEC-P1) with account page |
| 2FA | `2fa.tsx`, `2fa-enable.tsx`, `2fa-disable.tsx` (TOTP) | HA MFA modules (`ha-mfa-modules-card.ts`); Cosmos OpenID + 2FA | none | part of **PU-09**: **passkeys first** (MOBILE §3.2), TOTP fallback |
| Sessions | `sessions.tsx` (list, revoke others) | HA refresh tokens card; StartOS `system/routes/sessions` | none | **PU-18 · P1 · S** sessions and agent tokens in one list (SEC-B3) |
| Wallpaper and appearance | `routes/settings/mobile/wallpaper.tsx`, wallpaper picker on desktop | HA theme row | ThemeSwitch | **PU-03 · P0** |
| Language | `_components/language-dropdown.tsx`; **29 locales** in `packages/ui/public/locales/` | HA localization section | English only, no i18n layer | **PU-20 · P1 · M** i18n scaffolding (string catalog, `Intl` dates and numbers; ship English, add languages later). Doing it before the dashboard grows is cheap; after, it is L |
| Remote access | `https-access.tsx`, Tailscale (D:`system/tailscale.ts`), Tor (`mobile/tor.tsx`) | StartOS gateways; Cosmos built-in VPN | mock Remote access section (IA §2.10) | **PU-21 · P1 · M** with REM-P1 (exposure tiers §2.2) |
| Wi-Fi | `wifi.tsx`, `modules/wifi/` | StartOS `system/routes/wifi` | none | **PU-22 · P2 · S** (box images on boards with Wi-Fi only) |
| Backups | `features/backups/` (setup wizard, exclusions, restore wizard, network storage) | HA backup panel incl. **backup before app update** (`src/panels/config/backup/ha-config-backup-app-update-backups.ts`); StartOS backups | mock Backups with verified-restore stat (`OM:ui/demo/src/screens/Backups.tsx`) | BAK-P1–P4 (deployment, §4) + **PU-23 · P1 · M** setup and restore wizards |
| Migration assistant | `migration-assistant.tsx`, `modules/migrate/` (move from a Raspberry Pi to Umbrel Home) | StartOS transfer | none | **PU-24 · P1 · M** "Move to new hardware" = restore at onboarding (ONB-P3) + node drain (FAB-P2) |
| OS updates | `software-update-confirm.tsx`, release channel (D:`update/routes.ts` `getReleaseChannel`), signed releases (D:`update/release-signing.ts`), "What's new" | HA, StartOS updates pages | mock Updates (A/B slot, history) (`OM:ui/demo/src/screens/Updates.tsx`) | **PU-25 · P1 · S** wire Updates + "What's new" (UX-P5, OSU-P1) |
| Troubleshoot | `troubleshoot/{umbrelos,app}.tsx` (logs) | StartOS logs page; **diagnostic** route when the core is down | rescue console planned (IA §1) | **PU-19 · P1 · M** Troubleshoot: system and app logs, "download diagnostic bundle" (redacted), rescue console link |
| Factory reset | `routes/factory-reset/` (password confirm, progress) | HA, StartOS | none | **PU-26 · P1 · S** as an approval with a typed confirmation and a forced final backup offer |
| Restart, shutdown | `restart.tsx`, `shutdown.tsx` | all | none | **PU-27 · P1 · S** per node, as requests, with "apps affected" |
| Device info | `device-info.tsx` | HA hardware | NodeCard | covered by Nodes |
| Users | `users.tsx`, `modules/user-sharing/` (members; share apps, files, machines per member) | HA users/persons; Olares per-user apps | mock People (IA §2.10) | **PU-28 · P1 · M** multi-user (§3.10) |
| AI / MCP | `routes/settings/mcp/` (enable, tokens, per-app/file/machine access; agents act with one shared grant set, D:`mcp/mcp.ts`) | HA (read-only assist), StartOS admin tools | Agents and tokens section (IA §2.10); contract §11.3 MCP with agent principals | **OneMind leads** (per-agent principals + approvals); **PU-29 · P1 · S** wire the Agents page (SEC-B3) so the lead is visible |
| Settings search | `cmdk-entries.ts` | ZimaOS spotlight | none | in **PU-10** |

### 3.9 Notifications

| | |
|---|---|
| **umbrelOS** | In-app notifications (U:`routes/notifications.tsx`; D:`notifications/`), raised by the system (for example backups failing, an app update that changed folder settings); no external channels in the OS. |
| **Others** | HA repairs (issue with severity and a fix flow) + mobile push; StartOS notifications page; Coolify six channels (core-alignment §4.9). |
| **OneMind** | Mock Notifications with fix actions, channels and rules (`OM:ui/demo/src/screens/Notifications.tsx`, IA §2.9); no backend (NOT-P1). |
| **Gap** | **PU-30 · P1 · M** wire the inbox, bell badge in the top bar, and Web Push for the PWA (NOT-P1/P2/B3). Beat: a notification tied to a request has Approve/Deny on the phone lock screen (MOBILE §3.3). |

### 3.10 Multi-user

| | |
|---|---|
| **umbrelOS** | Owner + members; apps, files and machines shared per member; account picker in the dock; per-member sessions (U:`routes/settings/users.tsx`, `modules/user-sharing/`, `modules/auth/account-dock.tsx`; D:`user/multi-user.vm.test.ts`). |
| **Others** | Olares: per-user app instances. HA: admin vs user. CasaOS: single user. |
| **OneMind** | Principals with roles owner/adult/guest/agent in a static token file (contract §3); mock People section. |
| **Gap** | **PU-28 · P1 · M** People: invite, role, which apps each person sees on Home (sharing as umbrelOS does, as requests), per-person Home layout and wallpaper (PU-03). |

### 3.11 Mobile and PWA

| | |
|---|---|
| **umbrelOS** | Responsive web with phone-specific settings screens (U:`routes/settings/mobile/`), drawers on phones (`wifi-drawer-or-dialog.tsx`), `site.webmanifest`; native apps for iPhone and Android (2.1 notes: photo backup) and Windows (drive). |
| **Others** | HA: mature companion apps with push and widgets. Olares: LarePass is required. |
| **OneMind** | AppShell with bottom tabs + More on phones (`OM:ui/src/components/AppShell.tsx`); mobile shell in flight (`feat/mobile-shell`, MOBILE.md); no web manifest. |
| **Gap** | **PU-31 · P0 · S PWA:** web manifest, icons drawn for OneMind, theme colour from the accent, installable over HTTPS, offline "last known" cache labelled with its age (MOB-B2). It is the fastest phone presence while the native shell matures. **PU-32 · P1 · S** Sheet component (COMPONENTS "planned") for phone dialogs. |

### 3.12 Accessibility

| | |
|---|---|
| **umbrelOS** | Radix-based dialogs and menus; 29 locales; heavy motion and blur (wallpaper, dock magnification). No published accessibility target found in the sources read. |
| **Others** | HA: long-standing a11y work in the frontend. |
| **OneMind** | WCAG 2.2 AA target; contrast unit-tested on tokens; axe-core on components; reduced motion honoured (`OM:docs/design/PRINCIPLES.md` P5, `OM:ui/src/components/components.test.tsx`). **OneMind leads.** |
| **Gap** | **PU-33 · P1 · S** Playwright + axe over rendered demo and dashboard pages (COMPONENTS "Known gaps"), and contrast checks for every wallpaper/accent pair from PU-03 (text over wallpaper is where umbrel-style UIs fail). |

### 3.13 Performance

| | |
|---|---|
| **umbrelOS** | Route chunk prefetch (U:`modules/desktop/prefetch-route-chunks.ts`, `providers/prefetch.tsx`), virtualized app grid (`features/app-store/data/virtual-grid.ts`), gallery preload, home-fit layout maths. |
| **OneMind** | Small bundle today; no budgets. |
| **Gap** | **PU-34 · P1 · S** Budgets in CI (initial JS ≤ 200 KB gzip for the shell, LCP ≤ 2 s on a Pi 5 over LAN), route code splitting, virtualized Market grid once the catalog passes 100 apps (contract §9). |

### 3.14 Delight details worth matching

| Detail | umbrelOS | OneMind proposal | ID |
|---|---|---|---|
| Progress island for long jobs | U:`modules/floating-island/` (progress ring, lanes) | **Jobs tray**: one bar per running action, linked to its approval and log; survives navigation | in PU-06 (P0) |
| "What's new" after update | U:`routes/whats-new-modal.tsx` | From the signed release notes; once per person | PU-25 |
| Context menu on app tiles | U:`modules/desktop/desktop-context-menu.tsx` | Open / Logs / Restart (request) / Pin | PU-04 |
| Avatar and account picker | U:`modules/auth/account-avatar*.tsx` | Person menu with avatar initials (no upload in v0) | PU-28 |
| Animated onboarding background | U:`components/onboarding-background.tsx` | One generated SVG scene per wallpaper, static under reduced motion | PU-05 |

---

## 4. Deployment parity (install, configure, expose, update, recover)

### 4.1 How umbrelOS deploys an app (study summary)
- **Packaging:** each app is a folder in a Git repository (`umbrel-app.yml` + `docker-compose.yml` + hooks); the box clones the repository atomically and reads the registry (D:`apps/app-repository.ts` `atomicClone`, `update`, `readRegistry`). Community stores are extra repositories (D:`apps/app-store.ts` `addRepository`).
- **Manifest fields** (D:`apps/schema.ts`): `id`, `name`, `tagline`, `icon`, `category`, `version`, `port`, `description`, `website`, `developer`, `submitter`, `repo`, `support`, `gallery`, `releaseNotes`, `dependencies`, `permissions`, `path`, `defaultUsername`, `defaultPassword`, `deterministicPassword`, `torOnly`, `requiresHttps`, `installSize`, `widgets`, `defaultShell`, `implements`, `backupIgnore`, plus user `folderAccess` and `environment` overrides.
- **Lifecycle:** `install` (with selected dependency alternatives and folder access), `start`, `stop`, `restart`, `update`, `uninstall`, `logs`, `setSettings`, `moveDataRoot`, `setAutoStart`; a state machine with `stateProgress` for the UI (D:`apps/app.ts`, `apps/routes.ts`). Images unused after an update are cleaned (D:`apps/image-cleanup.ts`).
- **Exposure:** every app gets a **fixed port** (from the manifest) behind the **app gateway**, an auth proxy that checks the umbrelOS session cookie before proxying, with an error page when the app is down (D:`app-gateway/app-gateway.ts`, `error-page.ts`); LAN ingress with umbrelOS TLS and an opt-in TLS passthrough for apps with their own certificates (D:`lan-ingress/native-tls.md`); remote via Tailscale or Tor.
- **Credentials:** default username/password from the manifest, or a password derived per box (`deriveDeterministicPassword`), shown before first open.
- **Update:** pull the new compose, patch, pull images, start; on failure the state becomes `unknown` and the error is thrown. **No snapshot and no automatic rollback** (D:`apps/app.ts` `#update`).
- **Recovery:** full-box backups (restic-style repositories, scheduled, exclusions, restore at onboarding or into the current box; D:`backups/`), factory reset, signed OS updates with Rugix A/B (D:`update/rugix.ts`, `release-signing.ts`).

### 4.2 What OneMind has
- Catalog from `apps/*/onemind.app.yaml` with id, name, version, description, category (free text), icon, licence, source, archs, requires (GPU, memory), web port, manifests (contract §4); links, tier and scan record (§9.3, §11.1, §11.4).
- Two action types, `app.install` and `app.remove`, owner-approved, idempotent, expiring, audited (contract §3); kubernetes executor `kubectl apply -k` into `app-<id>` (`OM:core/onemind_core/executors.py`).
- Scan gate before install (§10, §11.1); agent principals for apps (§11.2); MCP for agents (§11.3).
- Not present: lifecycle verbs, progress, update, logs, settings, credentials, dependencies, per-app URL, community sources, custom deploys, app backups.

### 4.3 Deployment gaps

| ID | Gap | umbrelOS reference | Others | OneMind today | P | Effort | Backlog |
|---|---|---|---|---|---|---|---|
| **PD-01** | **Categories, tags and deployment kind in the manifest and catalog** (§2.1, §2.2): `category` enum, `tags` (≤ 2), `kind` (derived, not hand-set, for D1–D3; set by the tool for D4–D5), plus `tagline`, `gallery`, `releaseNotes`, `developer`; schema + validator + CI | D:`apps/schema.ts`; U:`features/app-store/constants.ts` | Runtipi enum, CasaOS list | free-text `category` (`OM:sdk/schema/onemind.app.schema.json`) | **P0** | S | new (contract amendment) |
| **PD-02** | **Per-app URL behind the gateway login** (subdomain per app, session check, friendly "app is starting / stopped / unreachable" page with the true state) | D:`app-gateway/` | Cosmos proxy + SSO; StartOS interfaces | none; Open is a planned link | **P0** | M | UX-P2, SEC-P2 |
| **PD-03** | **Lifecycle actions:** `app.start`, `app.stop`, `app.restart`, `app.update`, `app.configure`, `app.delete_data` as action types; executor reports step and % into the action (`progress: {step, pct}`) so the UI can show install progress | D:`apps/routes.ts`, `app.ts` state machine | all leaders | install/remove only | **P0** | M | APP-P3 |
| **PD-04** | **Install plan endpoint** `GET /v1/apps/{id}/plan`: dependencies, volumes, host ports, GPU, permissions, node fit and "why not", what the agent principal may do; feeds the install review (PU-06) and the approval card | U:`install-review-dialog.tsx`; D:`apps/routes.ts` `installReview` | Olares permissions | placement "why not" in mocks only | **P0** | M | APP-B3, FAB-P3 |
| **PD-05** | **App updates with release notes, health-gated:** catalog version feed, "update available", snapshot volumes → update → manifest probes on fresh signals → keep or **revert** (OneMind beats umbrelOS, which has no rollback) | D:`apps/app.ts` `#update` (no rollback) | Runtipi restores files on failure; HA backup before app update; StartOS restores data | none | **P0** | M–L | APP-P1, APP-B1 |
| **PD-06** | **Remove keeps data by default**; `app.delete_data` is a separate, typed-confirmation request (umbrelOS deletes data on uninstall) | `en.json` `app.uninstall.confirm.description-internal` | Runtipi/Cosmos keep volumes | executor deletes the namespace | **P0** | S | APP-P2 |
| **PD-07** | **Credentials:** manifest `credentials: {username?, password: generated\|default, showBeforeOpen}`; generated secrets stored sealed on the box, shown only to the owner on demand, never to agents, never in logs | D:`apps/app.ts` `deriveDeterministicPassword`; U:`app-settings-credentials.tsx` | Runtipi typed password fields | none | **P0** | S | DEP-P3 |
| **PD-08** | **Logs API** per app and node (`GET /v1/apps/{id}/logs?tail=&follow=`), redacted, owner and adult only | D:`apps/routes.ts` `logs`; `system/routes.ts` `logs` | all | none | **P1** | S | UX-P4 |
| **PD-09** | **Settings schema** per app (environment, volumes, ports) rendered as a form; saving is an `app.configure` request with the diff | U:`app-settings-{environment,storage,advanced}.tsx` | Runtipi `FIELD_TYPES`; StartOS config spec | specified (PLUGIN-UI X4) | **P1** | M | APP-P3, PLG |
| **PD-10** | **Dependencies with alternatives** (e.g. "needs a database: Postgres or MariaDB") and "remove these first" for dependents | U:`dependency-alternatives.ts`, `uninstall-these-first-dialog.tsx`; D:`apps/routes.ts` `dependents` | StartOS dependencies | none | **P1** | M | new |
| **PD-11** | **Ports and conflicts:** default is no host port (everything through the gateway); apps that need host ports or host networking (DNS 53, mDNS for HA) declare `hostPorts`/`hostNetwork`; CI rejects catalog collisions and the plan (PD-04) checks the target node's live ports | umbrelOS assigns one fixed `port` per app in the catalog | CasaOS asks at install | `web.port` only | **P1** | S | new |
| **PD-12** | **Community sources** by Git URL **pinned to a commit**, adding or moving a source is an owner request, the scan gate runs on the box | U:`modules/community-app-store/`; D:`apps/app-store.ts` `addRepository` (follows branch head) | HA repositories | none | **P1** | M | new (D3) |
| **PD-13** | **Custom app and your own deployments** (D4, D5): `onemind app import <compose>`, `onemind deploy <dir\|git-url>`, history and one-step rollback, watched Git commits as requests | none (umbrelOS has VMs instead) | Coolify, Dokploy, TrueNAS custom app; StartOS sideload | kustomize executor only | **P1** | L | APP-P4, DEP-P1, DEP-P2, DEP-B1 |
| **PD-14** | **App backups:** volume snapshots per app, exclusions (`backupIgnore`), restore one app, "verified restore" mark | D:`backups/`, `apps/routes.ts` `backupIgnore` | HA, StartOS | none | **P1** | L | BAK-P1–P4, BAK-B1 |
| **PD-15** | **Restore at onboarding / move to new hardware** | U:`routes/onboarding/restore.tsx`; `routes/settings/migration-assistant.tsx` | HA, StartOS transfer | none | **P1** | M | ONB-P3 |
| **PD-16** | **Widget data** from apps through the gateway (typed templates, freshness) | D:`widgets/routes.ts`, `apps/app.ts` `getWidgetData` | — | specified (PLUGIN-UI §2) | **P1** | M | PLG-P1 |
| **PD-17** | **Exposure tiers** private → remote → public as separate requests (§2.2) | Tailscale and Tor only (D:`system/tailscale.ts`) | Cosmos public proxy | none | **P1** | M | REM-P1, REM-B1 |
| **PD-18** | **Recovery for a stuck app:** `failed`/`unknown` states with a "Repair" request (re-apply manifests at the recorded digests), and the host rescue console when k3s is down | umbrelOS leaves `unknown` and expects a retry | StartOS diagnostic route | none | **P1** | M | REC-W11-04 |
| **PD-19** | **OS update channel** (stable/beta) and "app needs a newer OS" guard | D:`update/routes.ts` `setReleaseChannel`; U:`os-update-required.tsx` | HA, StartOS | updater in flight (`OM:internal/update`) | **P1** | S | OSU-P1 |
| PD-20 | Image cleanup after updates and removals | D:`apps/image-cleanup.ts` | — | none | P2 | S | new |
| PD-21 | Move an app's data to another disk | D:`apps/app.ts` `moveDataRoot` | — | none | P2 | M | new |
| PD-22 | Native TLS passthrough for apps with their own certificates | D:`lan-ingress/native-tls.md` | — | none | P2 | M | new |
| PD-23 | VMs ("Machines") | D:`machines/` | Proxmox, TrueNAS | none | P2 | L | not planned for core |

---

## 5. Prioritized gap list

Ordered for "ship fast": each P0 is small enough to land in a week, and the list is ordered so the first items unblock the rest.

### P0 (founder daily use and first impression)
| # | ID | Kind | Gap | Effort | Unblocks |
|---|---|---|---|---|---|
| 1 | PD-01 | Deploy | Category enum, tags, deployment kind, tagline/gallery/releaseNotes in manifest + catalog | S | PU-02, PU-11 |
| 2 | PU-01 | UI | **Wire the dashboard onto `@onemind/ui`** (CORE-DASH): replace the 5-screen MVP with the mocked screens on real endpoints, demo-data flag kept | M | everything below |
| 3 | PU-02 | UI | Market categories and rails (Discover, All, Installed, Updates, Your deployments), search over tags | S | — |
| 4 | PU-03 | UI | **Appearance:** own generated wallpapers with accent, accent presets, density, stored per person on the hub; contrast-tested | M | PU-04, PU-05 |
| 5 | PD-03 | Deploy | Lifecycle actions (start/stop/restart/update/configure/delete_data) with executor progress | M | PU-06, PU-07 |
| 6 | PD-02 | Deploy | Per-app URL behind the gateway login with an honest state page | M | PU-04 |
| 7 | PU-06 + PD-04 | UI + Deploy | Install review from a plan endpoint, approval, **jobs tray** progress, Open | M | — |
| 8 | PU-07 + PD-06 + PD-07 | UI + Deploy | App detail: states, actions as requests, credentials card, keep-data remove | M | — |
| 9 | PU-04 | UI | Home as launcher: personal greeting, app grid that opens apps, pin/reorder, edit widgets (limit 4) | M | — |
| 10 | PU-05 + PU-09 | UI | First-run wizard + real login (passkey, TOTP fallback) | M | — |
| 11 | PD-05 + PU-08 | Deploy + UI | Health-gated app updates with release notes and revert; Updates rail | M–L | — |
| 12 | PU-10, PU-31 | UI | Command palette; PWA manifest and offline "last known" cache | S each | — |

### P1 (parity within weeks)
**UI:** PU-11 app page richness and Discover rows · PU-12 system widgets · PU-14 category icons · PU-17 live usage per node and app · PU-18 sessions and tokens · PU-19 Troubleshoot and diagnostic bundle · PU-20 i18n scaffolding · PU-21 remote access · PU-23 backup and restore wizards · PU-24 move to new hardware · PU-25 Updates + What's new · PU-26 factory reset · PU-27 restart/shutdown per node · PU-28 multi-user and per-person Home · PU-29 Agents page · PU-30 notifications inbox + Web Push · PU-32 Sheet · PU-33 Playwright + axe and wallpaper contrast · PU-34 performance budgets.
**Deployment:** PD-08 logs · PD-09 settings schema · PD-10 dependencies · PD-11 ports and conflicts · PD-12 pinned community sources · PD-13 custom apps and own deployments · PD-14 app backups · PD-15 restore at onboarding · PD-16 widget data · PD-17 exposure tiers · PD-18 stuck-app repair and rescue console · PD-19 OS channel and OS-version guard.

### P2 (later or not core)
PU-13 web shortcuts · PU-15 app terminal (approved, time-boxed) · PU-16 Files (as a Market app) · PU-22 Wi-Fi · PD-20 image cleanup · PD-21 move app data · PD-22 TLS passthrough · PD-23 VMs.

---

## 6. Where OneMind already beats umbrelOS (keep visible in the UI)

| OneMind | umbrelOS | Where |
|---|---|---|
| Every change is a request; only the owner approves; agents have their own principals | MCP agents share one grant set and act with the owner's rights (D:`mcp/mcp.ts` permissions are global, not per agent) | contract §3, §11.2–§11.3; ApprovalCard |
| Hash-chained audit log with a "chain verified" timeline | no audit view | IA §2.5 |
| Stale and offline are distinct, labelled states, with age on the hub's clock | `unknown` and `stopped` both shown as "Offline" | PRINCIPLES P2; §2.3 here |
| Install refused without a recent passing scan; trust card with licence and tier | community stores install without a scan | contract §10, §11; TrustCard |
| Multi-node fabric | one box | Nodes |
| Planned: health-gated app updates with revert | update failure leaves `unknown` | PD-05 |
| Remove keeps data by default (planned) | uninstall deletes data | PD-06 |
| WCAG 2.2 AA, tested | no stated target | P5 |

The UI must make these visible without noise: the "API equivalent" disclosure, the requester pill (Person/Agent/System), the freshness pill and the TrustCard verdict are the signature elements, the way wallpaper and dock are umbrelOS's.

## 7. Licence ledger for this audit
- umbrelOS (PolyForm NC), ZimaOS (no licence), Olares (AGPL + NC), Cosmos (Commons Clause), Runtipi (GPL-3.0): **read for UI and flow patterns only**. No code, asset, icon, wallpaper, string or screenshot was copied. Category names in §2.1 are ordinary English words chosen for OneMind; the list differs from every competitor's.
- Home Assistant frontend (Apache-2.0), StartOS (MIT), CasaOS (Apache-2.0): patterns only here; if a later PR copies code, it adds a `NOTICE` entry with the commit.
- Wallpapers, category icons and the onboarding scene (PU-03, PU-05, PU-14) must be drawn or generated for OneMind (SVG/CSS) or CC0 with the source recorded.

## 8. Limits of this page
- umbrelOS was read at source level, not run; behaviour is inferred from code, tests, locale strings and release notes at `c43beed`. The others were read more briefly (directory structure, schemas and the existing teardowns).
- Efforts are estimates for one engineer with an agent; they assume the contract amendments (PD-01, PD-03, PD-04) are accepted first.
- Priorities follow the founder brief of 2026-11-12 and may differ from the ranking in core-alignment §5, which weighs security and fabric higher; where they conflict, the founder decides.
