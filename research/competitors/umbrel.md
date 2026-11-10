# Umbrel / umbrelOS - Competitor Teardown

Research date: 2026-11-10. Method: `gh api` reads of github.com/getumbrel/umbrel and getumbrel/umbrel-apps (default branch, pushed 2026-11-03 and 2026-11-10 respectively), curl of umbrel.com HTML and headers, WebFetch of umbrel.com pages. Items I could not confirm from a source I opened are marked **UNVERIFIED**.

## Key facts table

| Item | Fact | Source |
|---|---|---|
| Current stable | umbrelOS 2.0.1 (2026-11-01); 2.1.0-beta.1 (2026-11-03) | gh release list getumbrel/umbrel |
| 2.0 date | umbrelOS 2.0.0 released 2026-09-22 (betas: 2.0.0-beta.1 2026-09-02, beta.2 2026-09-17) | gh release list |
| Base OS | Debian 13 "trixie", pinned by snapshot date; kernel + firmware from trixie-backports on amd64 | packages/os/umbrelos.Dockerfile, packages/os/README.md |
| Update mechanism | A/B root partitions, OTA via Rugix (Rugpi); legacy Mender devices still supported; signed release manifests | packages/os/rugix, mender.cfg, modules/update/ |
| Daemon | `umbreld`, TypeScript on Node.js (Node 26.12.1 pinned in image), Express + tRPC | packages/umbreld/package.json, Dockerfile |
| UI | React + Vite + Tailwind + Radix, tRPC client, zustand | packages/ui/package.json |
| App runtime | Docker (Compose spec), apps defined by docker-compose.yml, own network `umbrel_main_network` | umbrel-apps SKILL.md; modules/apps/app.ts |
| Storage | ZFS pools (mirror/raidz/stripe) = "FailSafe"; optional SSD accelerator via L2ARC + special vdev | modules/hardware/raid.ts |
| MCP | Built into umbreld using official `@modelcontextprotocol/server` 2.0.0; bearer tokens, per-agent permissions | modules/mcp/ |
| Machines (VMs) | libvirt + KVM/QEMU, noVNC in browser; Windows/Ubuntu/Debian/Android(Waydroid)/Home Assistant OS | modules/machines/, release notes |
| umbrelOS license | PolyForm Noncommercial 1.0.0 (NOT open source by OSI definition) | LICENSE.md |
| umbrel-apps license | No LICENSE file; GitHub reports none. **Treat as all-rights-reserved / unlicensed** (UNVERIFIED legal position; app upstreams carry their own licenses) | gh api repos/getumbrel/umbrel-apps |
| App count | Official site/repo says "over 300" apps; umbrel-apps has 397 top-level app dirs (count of non-dot dirs, may include non-app dirs) | gh repo view, contents API |
| Hardware | Umbrel Home (Intel N150, 16GB DDR5, 1/2/4TB NVMe); Umbrel Pro (Intel i3-N300, 16GB LPDDR5, 4x NVMe up to 32TB, 2.5GbE) | umbrel.com/umbrel-home, /umbrel-pro |
| Website | Next.js (App Router) on Vercel, PostHog analytics | curl -I umbrel.com |
| Funding | $3M seed (Oct 2021, Slow Ventures per Caplight) | blog.getumbrel.com/seed-...; caplight |

## 1. umbrelOS 2.0 - features, version, date

Release: **umbrelOS 2.0 = tag 2.0.0, published 2026-09-22**, called "the biggest update we've ever shipped" in the release body. 2.0.1 followed 2026-11-01. 2.1 Beta 1 on 2026-11-03. (https://github.com/getumbrel/umbrel/releases/tag/2.0.0)

Feature list taken verbatim-in-substance from the 2.0.0 release notes:
- **Photos app**: auto-indexes photos/videos on the Umbrel; years/months/days, albums, favorites, Live Photos, panoramas, screenshots. Code: `modules/photos/` (own SQLite read-model, `map-tiles.ts` using pmtiles/maplibre for a map view).
- **Umbrel for iPhone**: background camera-roll backup to the Umbrel. **Umbrel for Mac**: auto-discovers the Umbrel, mounts it as a Finder drive, over LAN and over Tailscale. In 2.1 Beta 1: **Android app** (photo backup) and **Windows app** (File Explorer drive). Code in `clients/` (Swift/UmbrelKit, Kotlin, C#/WPF).
- **Machines**: Windows, Ubuntu, Debian, Android and more in the browser; one-click install. Website labels it "beta". 2.1 beta adds LAN-bridged machines (so Home Assistant OS can see smart-home devices), USB passthrough (Zigbee, Coral, drives), clipboard bridge, touch console.
- **Multiple users**: each person gets own account, home screen, private home folder; share chosen apps/folders. Code: `modules/user/`, `files/member-shares.ts`, `samba-multi-user` tests.
- **AI agents / MCP server**: connect Claude Code, Codex, OpenClaw, Cursor or any agent; each agent gets own token with only allowed access, revocable.
- **Storage Manager + FailSafe (RAID)**: combine drives or mirror; drive swap and health in Settings; HDD+SSD NAS devices get "SSD acceleration". 2.1 beta adds SAS HBA support.
- **Download from cloud**: Dropbox, OneDrive, iCloud Drive, Nextcloud, ownCloud, any WebDAV; continuous backup mode; Google Drive "coming soon". Implemented with rclone (`files/cloud-rclone.ts`; rclone 1.75.2 pinned in the Dockerfile).
- **GPU acceleration**: NVIDIA, AMD, Intel, incl. Thunderbolt eGPU, auto-detected and passed to apps like Ollama and Jellyfin; GPU/VRAM in Live Usage. Apps opt in with `permissions: [GPU]`; umbrelOS injects device access (`/dev/dri`, AMD ROCm, NVIDIA). NVIDIA driver 595.91.07 + container toolkit pinned in image.
- **Per-app settings ("point any app at any folder")**: apps can be pointed at folders on Home, external or network drives with read-only option, and whole app data can be moved to an external drive. Driven by manifest `folderAccess:` and `storage: dataRoot: data`.
- New App Store UI (categories, collections, search, update shelf, compatibility checks, release history); redesigned Settings; CMD/Ctrl-K search across apps/files/photos/settings; faster Files (indexing via Watchman, thumbnails, HEIC); **automatic HTTPS**.
- 2.1 Beta 1 also: Documents in Files (view/edit/sign PDFs, Word, PowerPoint, spreadsheets), newer kernel and NVIDIA driver (RTX 50-series). (https://github.com/getumbrel/umbrel/blob/master/releases/2.1.0-beta.1-release-notes.md)

Also present in code but not headline: backups (Kopia 0.23.1 pinned; `modules/backups/`, supports network storage, scheduled, restore during onboarding), Samba sharing, Tor container (`containers/tor`), widgets on home screen, notifications, Tailscale detection (`modules/system/tailscale.ts`; Tailscale is installed as an app and umbreld reads its status; clients carry Tailscale setup UI).

Not verified: "open-from-Mac" is described on umbrel.com as opening your Umbrel from Finder; this matches the macOS client README ("menu bar app", drive in Finder). The umbrel.com 2.0 page also mentions 29 languages (downloads page JSON: "29 languages").

## 2. Architecture (from code)

### Repo layout (getumbrel/umbrel, TypeScript monorepo; GitHub language bytes: TS 13.8M, Kotlin 1.6M, Swift 1.3M, C# 0.4M, Shell 0.26M, Nix 10K)
```
.agents/skills/          agent skills for contributors (AGENTS.md says use git worktrees, PR to staging)
clients/                 native companion apps (apple/UmbrelKit+macos+ios, android Kotlin, windows WPF + Umbrel.Core)
containers/tor/          Tor container image
packages/umbreld/        the daemon (TypeScript, Node, tRPC/Express)
packages/ui/             React dashboard + app-auth frontend (Vite)
packages/os/             OS image build: umbrelos.Dockerfile, build.sh, rugix/ (Rugix Bakery), overlay/ (+overlay-pi), usb-installer/ (Nix flake), mender.cfg, package-versions/
releases/                signed release manifests, notes, signing keys
scripts/                 install, update-script, release-signing, umbrel-dev (dev VM), remote-builder
```
Key umbreld modules (`packages/umbreld/source/modules/`): `apps` (store, lifecycle, compose patching), `app-gateway` + `lan-ingress` (proxy/TLS), `auth`, `user`, `files` (+samba, cloud/rclone, file-index, thumbnails), `photos`, `machines` (libvirt), `mcp`, `hardware` (raid, gpu, thunderbolt, umbrel-pro EC fan/LED control), `backups`, `update`, `system`, `system-ng`, `notifications`, `widgets`, `dbus`, `event-bus`.

### Base OS and image build
- Debian **trixie** via a Docker multi-stage build with all base images pinned by digest and apt pinned by snapshot date for reproducibility (`umbrelos.Dockerfile`). Kernel 6.12 base; amd64/generic arm64 take newer kernel+firmware from trixie-backports; ZFS from trixie (with a documented plan to move to backports); NVIDIA DKMS driver built in. Raspberry Pi image uses the Raspberry Pi kernel/firmware only. (https://github.com/getumbrel/umbrel/blob/master/packages/os/README.md)
- Images produced by **Rugix Bakery** (`rugix-bakery.toml`: amd64 EFI via GRUB, arm64 EFI, Pi) - GPT layout, 512MiB boot, 8GiB system slot(s) plus data. A Nix flake builds the USB installer (`usb-installer/`). Older images used mender-convert (`mender.cfg`: 20GB image, 2x ~10GB OS partitions, data partition grown on first boot).
- Release downloads (2.0.0): `umbrelos-amd64-usb-installer.iso`, `umbrelos-amd64.img.xz`, `umbrelos-amd64.update`, `umbrelos-amd64-legacy.update`, `umbrelos-pi.img.zip`, `umbrelos-pi.update`, SHA256SUMS + OpenTimestamps `.ots`.
- Node 26.12.1, Kopia, rclone, yq, libde265 (HEIC) pinned with SHA256 per arch.

### Update mechanism
A/B system partitions with OTA. `modules/update/` contains `rugix.ts` (calls rugpi/rugix), `install-release.ts`, `release-signing.ts`, `signing-keys.ts`; releases carry a signed manifest (`releases/2.1.0-beta.1-manifest.txt` + `.sig` + `.ots`; keys in `releases/keys/`). A Mender hook script (`rugpi-ctrl update install --stream`, `system commit`) bridges legacy Mender-updated devices to Rugix. So: signed, streamed A/B image updates with rollback (NOTE from README: ZFS pools are created with `compatibility=openzfs-2.3` specifically so a pool still imports after an OTA rollback).

### Daemon
`umbreld`: TypeScript run directly on Node (type-stripping, `./source/cli.ts`), Express + tRPC (`@trpc/server` 11), better-sqlite3, dockerode for Docker Engine API, node-pty (terminal), `@homebridge/dbus-native` (systemd/NetworkManager D-Bus), `isomorphic-git` (clones app store repos), `compose-spec-schema` (validates compose), Watchman (file watching), blake3 (file hashing). Tests: vitest with unit / integration / VM tests (many `.vm.test.ts` run real ZFS RAID scenarios in QEMU).

### UI
React SPA built with Vite, Tailwind, Radix UI, cmdk (Cmd-K), TanStack Query + tRPC, zustand, react-router, i18next, `motion` (animation), CodeMirror (file editing), xterm.js (terminal), noVNC (Machines), pdf.js, maplibre-gl, PhotoSwipe, recharts. UI imports shared types directly from umbreld source (end-to-end typed tRPC).

### How apps run, proxy, auth
- Each app = Docker Compose project in `${UMBREL_ROOT}/app-data/<app-id>`; umbreld patches the compose file before install (container names, storage mounts, GPU, Downloads mount rewrite), then runs docker compose lifecycle, sourcing `exports.sh` of dependencies. Shared network `umbrel_main_network`.
- **In 2.0 there is no per-app `app_proxy` container any more**: `app_proxy` in compose is only config; umbreld's **app-gateway** and **lan-ingress** modules do the proxying. lan-ingress uses **nftables** (`umbrel_lan_ingress` table) to redirect LAN traffic on app ports to hidden Node listeners (23000-65535), terminates TLS (automatic HTTPS), stamps `x-forwarded-*` headers, and can pass TLS through for "native TLS" apps (e.g. Plex `plex.direct`). Public login/auth port: 2000. Source: `modules/lan-ingress/lan-ingress.ts`, `apps/native-tls.ts`, SKILL.md.
- Auth: Umbrel login (with optional 2FA) protects every app route by default via an app-gateway cookie; per-app `PROXY_AUTH_WHITELIST/BLACKLIST`/`PROXY_AUTH_ADD` env in the app_proxy block; in 2.0 owners can switch "Require Umbrel login" off per app. Native clients use a separate auth path (`auth/native-client.ts`).
- Remote access: no hosted relay found in code. Remote access is via **Tailscale** (an app in the store; umbreld reads tailscaled status for hostname; Mac/iOS/Android/Windows clients explicitly support "over Tailscale") plus Tor (container) - "no hosted relay" is UNVERIFIED but nothing in the tree I searched indicated one.
- Manifest ports 40000-49999 are reserved for Machines (VMs) per SKILL.md.

### FailSafe / RAID
`modules/hardware/raid.ts` shells to `zpool`/`zfs` (parses `zpool status --json`); topologies `stripe | raidz | mirror`; supports replace, scrub scheduler (+error notifications), size rounding, foreign pool detection, recovery mode, onboarding recovery after reflash or factory reset. HDD+SSD "accelerator" = SSD split into an L2ARC partition + a ZFS *special* vdev. Heavily tested via VM tests. So FailSafe = ZFS, not mdadm. Internal-storage slot detection is hardware-specific (`internal-storage.ts`, `umbrel-pro.ts`, `is-umbrel-home.ts`).

### MCP server
`modules/mcp/`: Express router at `/mcp`, uses `createMcpHandler`/`McpServer` from `@modelcontextprotocol/server` 2.0.0 (+ `@modelcontextprotocol/node`). Auth = bearer tokens `umbrelmcp_<32hex id>_<64hex secret>`, secret stored hashed, max 20 tokens, each labelled with agent type; client self-identity tracked in memory for the dashboard. Permissions model (`McpPermissions`): `apps` (all|list), `appStore` (bool), `files` (all|list), `manageSystem` (bool), `machines` (all|list), `createMachines` (bool). Tools are **only registered if granted**; server `instructions` string tells the agent what is/isn't granted and to tell the user it can be enabled in Settings.
Tools (from `registerTool` calls):
- System info (always): `get_system_info`, `get_system_resources`, `check_os_update`, `get_notifications`
- Apps: `list_apps`, `get_app_status`, `get_app_details`, `get_app_logs`, start/stop style tools, `uninstall_app`, `set_app_settings`, `move_app_data`, `reset_app_data`; App Store: `search_app_store`, `get_app_store_details`, `install_app`
- Files: `list_directory`, `create_directory`, `copy`, `move`, `rename`, `trash`, `search_files` (Home only). Content transfer is plain HTTP `/mcp/files/download|upload` with the bearer token, never inside tool results. Deletion = Trash only; MCP never overwrites existing files.
- Machines: `list_machines`, `get_machine_details`, `stop_machine`, `force_stop_machine`, `retry_machine_install`, `eject_machine_install_media`, `update_machine_settings`, `delete_machine`, `get_machine_screenshot`, `control_machine` (keyboard/mouse, returns screenshot), `list_os_images`, `create_machine`
- **System management (the "agent manages the OS itself" part, gated by `manageSystem`)**: `install_os_update`, `get_os_update_status`, `restart_device`, `set_hostname`, `set_release_channel` (beta program), `get_network_settings`, `get_system_logs`.
So yes: an agent with `manageSystem` can install OS updates, reboot, rename the device and read logs; with `appStore` it can search and install apps (respecting dependency order).

## 3. App store format

### Repo and review process
- Official store repo: github.com/getumbrel/umbrel-apps (default branch `master`), ~397 app directories; browse at apps.umbrel.com (Next.js/Vercel per headers). Each app = one top-level directory named by app id.
- Submission: PR to umbrel-apps; PR template asks type (new/update/metadata), app id, upstream, version, tested on Umbrel device / local umbrelOS, architecture tested (amd64/arm64), lint caveats; new apps need screenshots + logo (**Umbrel creates the final gallery assets and hosts icons separately**). CI: `.github/workflows/lint-apps.yml` runs a linter via `pull_request_target`. README now says to point your coding agent at `AGENTS.md`, which routes to four skills: `umbrel-package-app`, `umbrel-update-app`, `umbrel-test-app`, `umbrel-develop-app`.
- App Store gates (SKILL.md): must open to a useful web UI (even a status page for headless apps); images must be public, maintained, **multi-arch amd64+arm64**, pinned as `repo:tag@sha256:digest`; no `build:`; no Docker socket mounts; privileged/host-net/device mounts need justification; data must persist under `${APP_DATA_DIR}`.
- Community app stores: template repo github.com/getumbrel/umbrel-community-app-store with `umbrel-app-store.yml` (`id`, `name`) and app dirs; user adds the git URL in the UI. Community stores may use `icon` in the manifest. (Template has no license.)

### Real manifest (immich, https://github.com/getumbrel/umbrel-apps/blob/master/immich/umbrel-app.yml, description trimmed)
```yaml
manifestVersion: 1.1
id: immich
storage:
  dataRoot: data
folderAccess:
  - id: external-library
    name: External Library
    note: Select a folder containing photos or videos, then configure /mnt/external-library ...
    mounts:
      - service: server
        targetPath: /mnt/external-library
        readOnly: true
category: files
name: Immich
version: "v3.3.6"
tagline: High-performance photo and video backup solution
description: >-
  An open-source and high-performance self-hosted backup solution ...
releaseNotes: >-
  This update keeps the new umbrelOS storage-management options ...
developer: Alex Tran
website: https://www.immich.app
dependencies: []
repo: https://github.com/immich-app/immich
support: https://github.com/immich-app/immich/discussions
port: 2283
gallery:
  - 1.jpg
  - 2.jpg
  - 3.jpg
path: ""
defaultUsername: ""
defaultPassword: ""
permissions:
  - GPU
submitter: levma
submission: https://github.com/getumbrel/umbrel-apps/pull/239
```

### Manifest field reference (from umbrel-package-app SKILL.md)
`manifestVersion` (framework compatibility, e.g. 1, 1.1, 1.3, 2.0 - older OS refuse), `id` (== dir name, kebab-case), `implements` (drop-in provider of another app's dependency contract, e.g. bitcoin, electrs), `storage.dataRoot: data` (lets user relocate data in 2.0), `folderAccess[]` (id,name,note,mounts[service,targetPath,readOnly]), `environment[]` (name, services, default, options, note - user-overridable env), `category`, `name`, `version`, `tagline`, `description`, `releaseNotes`, `developer`, `website`, `dependencies[]` (other app ids), `repo`, `support`, `port` (host-facing unique port, served over HTTP and HTTPS), `gallery`, `path`, `defaultUsername`, `defaultPassword`, `deterministicPassword`, `requiresHttps`, `nativeTlsHostnameSuffixes`, `permissions[]` (`GPU`, `STORAGE_DOWNLOADS`), `widgets[]` (types text-with-buttons, text-with-progress, two-stats-with-guage, three-stats, four-stats, list, list-emoji; fetched server-side from `service:port/path` JSON), `backupIgnore[]`, `submitter`, `submission`.

### Compose conventions
- Compose file (the real immich one uses `version: "3.7"`): an `app_proxy` service with only `environment: APP_HOST: <app-id>_<service>_1, APP_PORT: <internal port>, PROXY_AUTH_ADD/WHITELIST/BLACKLIST`.
- Umbrel injects `container_name`, the `default` network (`umbrel_main_network`), and rewrites `${APP_DATA_DIR}/data/...` mounts. Env vars: `APP_ID, APP_VERSION, APP_DATA_DIR, APP_DATA_ROOT, APP_SEED` (stable per-install secret; immich uses it as JWT_SECRET), `APP_PASSWORD`, `DEVICE_DOMAIN_NAME`, `APP_PROXY_PORT`, `UMBREL_ROOT`, `derive_entropy` helper.
- Optional `exports.sh` (exports vars for dependents, e.g. `APP_BITCOIN_*`) and `hooks/` (pre-start etc.), `.gitkeep` for empty bind-mount dirs.
- Containers run as UID/GID 1000:1000 where possible; `restart: on-failure`; images pinned by tag+digest. Note immich's own compose has a hard-coded DB password in the sample (`moneyprintergobrrr`) - the shared Docker network is treated as untrusted per SKILL.md yet this pattern persists in older packages.

## 4. Licenses

- **umbrelOS (getumbrel/umbrel): PolyForm Noncommercial License 1.0.0** (`LICENSE.md`; `package.json` of umbreld also says so). Permits any *noncommercial* purpose: personal use, hobby, research, charities/educational/government orgs; you may modify and redistribute under the same terms, but must keep the license notice. Does **not** permit commercial use. Umbrel's License FAQ says: forking OK if noncommercial; "Can I sell Umbrel? No" - explicitly including selling cloud-hosted instances, home server hardware shipped with Umbrel or derivatives, and support services; contact partner@getumbrel.com for commercial licensing. (https://github.com/getumbrel/umbrel/wiki/License-FAQ via raw wiki; https://polyformproject.org/licenses/noncommercial/1.0.0)
- **umbrel-apps:** no LICENSE file and GitHub reports no license (`licenseInfo: null`). The packages are manifests/compose files wrapping upstream apps, each with its own upstream license. Reusing the manifests commercially is a legal grey area - **UNVERIFIED / needs counsel; do not assume it is permissive.** Same for the community-app-store template (no license).
- Implication for OneMind OS: **you cannot ship umbrelOS code, or a fork, on paid OneMind hardware or as a paid service without a commercial deal with Umbrel.** Studying the architecture is fine; copying code is not.

## 5. Hardware

| | Umbrel Home | Umbrel Pro |
|---|---|---|
| CPU | Intel N150, quad-core, 3.6 GHz, 6W TDP | Intel Core i3-N300, 8 cores, 3.8 GHz, 7W TDP |
| RAM | 16GB DDR5 | 16GB LPDDR5 |
| Storage | 1TB / 2TB / 4TB NVMe | 4x M.2 2280 NVMe (PCIe Gen 3/4/5, up to 8TB each, no heatsinks) = up to 32TB; 64GB onboard for umbrelOS |
| Network | 1GbE, Wi-Fi 5, BT 5.0 | 2.5GbE (RJ45; USB 5/10GbE adapters supported), Wi-Fi 6, BT 5.2 |
| Ports | 3x USB-A 3.0 (5Gbps) | 2x USB-C 3.2 Gen2 (10Gbps), HDMI 2.1, LED status light |
| Other | Active cooling, 1-year limited warranty | FailSafe (survives 1 SSD failure), 65W adapter, CNC aluminum + American walnut, magnetic lid = SSD heatsink |
| Price | Launch Feb 13 2024: $399 / EUR 369 / GBP 319 (N100, 16GB, 2TB) (community post). Current price: **UNVERIFIED** - umbrel.com page shows only "From" with no amount in fetched HTML; third-party snippets mention $429 (2024) and a 2TB/4TB $699/$949 listing of unknown date | Search snippets (not opened as primary page) quote launch "$699 / 599 EUR / 529 GBP, ships Feb 9 [2026]"; current price **UNVERIFIED** |

Sources: https://umbrel.com/umbrel-home, https://umbrel.com/umbrel-pro, https://community.umbrel.com/t/introducing-the-new-upgraded-umbrel-home-now-more-affordable-than-ever/15197. Free US shipping; 10% off promo banner until Sep 29 (stale). Manufacturer: **not stated on either page (UNVERIFIED)**. umbreld contains Pro/Home-specific code: embedded-controller fan/LED control via x86 I/O ports 0x62/0x66 (`hardware/umbrel-pro.ts`), slot detection, and a USB-installer auto-flash test for Umbrel Home. Earlier Umbrel Home gen was historically sold by "The Bitcoin Machines" (community post title) - details UNVERIFIED.

**Own-hardware installs (DIY):** officially supported. umbrel.com/downloads: "NAS, mini PCs, VMs, Raspberry Pi 5" ("one file for any 64-bit Intel or AMD machine"; "one download for Raspberry Pi 5 and Pi 4", Pi 5 recommended, Pi 4 can crash with USB drives); USB installer needs a 4GB+ stick; amd64 img is ~1.5GB; community support only for DIY, priority support for Umbrel hardware. Release has `amd64`, `amd64-legacy` and `pi` update files; generic arm64 exists as a dev-VM image.

## 6. Business model, pricing, company

- Revenue: **hardware sales** (Home, Pro) with a free software OS and free app installs; affiliate program and a "Partner" contact for commercial licensing (site footer, FAQ). No subscription found; site marketing explicitly contrasts one-time purchase vs iCloud 2TB at $9.99/mo ("Do the math" section on umbrel-home page). No paid cloud/relay tier found (UNVERIFIED that none exists).
- Marketing positions Umbrel Home against iCloud ($120/yr, $600/5 yr, $1,200/10 yr comparison shown on the page).
- Company: Umbrel, co-founded by Mayank Chhabra (CEO) and Luke Childs (CTO) (search results, not primary; UNVERIFIED on the primary site). Origin: Bitcoin node software ("Umbrel" started Oct 2019 on Raspberry Pi). **$3M seed announced Oct 2021** (https://blog.getumbrel.com/seed-6d09aa08f8ac); Caplight lists $3.4M total, Slow Ventures as seed investor. A Caplight snippet mentions a "$16M Series A" headline but it appeared in a "NEW" banner for a different company (Caplight itself) - ignore. umbrelOS 1.0 + Umbrel Home launched Feb 13 2024 (community post). Umbrel Pro launched Feb 2026 (search snippets). Has Careers page (hiring). GitHub: umbrel 12.5k stars, umbrel-apps 793 stars (gh repo view, 2026-11-10).

## 7. Website

- **umbrel.com is Next.js (App Router, `_next/static`, `x-nextjs-prerender`, `NEXT_LOCALE` cookie, RSC `vary` headers) hosted on Vercel** (`server: Vercel`, `x-vercel-id`). Analytics: PostHog (CSP allows `us.i.posthog.com`, also X/Twitter ads). Strict CSP report-only. Marketing copy lives in i18n JSON in the page payload (29 languages). A Framer staging site exists at framer.umbrel.com (search results show `framer.umbrel.com/umbrel-home`, "wip" pages) - suggests marketing pages were/are designed in Framer and then ported (UNVERIFIED mechanism).
- apps.umbrel.com (App Store web) is also Vercel (`server: Vercel`, `x-matched-path: /`).
- Structure: `/umbrel-home`, `/umbrel-pro`, `/umbrelos`, `/downloads`, `/support` (docs-like help centre, e.g. `/support/getting-started/what-is-umbrel`), `/umbrelos-1-0`; external App Store (apps.umbrel.com); community forum (community.umbrel.com), Discord, Reddit, X, Telegram, YouTube; Careers, Affiliates, Legal/ToS, Partner mailto; GitHub. Old blog at blog.getumbrel.com (Medium-hosted style URL).
- `link.umbrel.com/*` short links used for the client apps (ios-app, macos-app, android-app, windows-app).

## 8. Strengths, weaknesses, limits

Strengths
- Extremely polished consumer UX (Photos, Files, Cmd-K, native phone/desktop clients, HTTPS automatically) and clear "iCloud replacement" positioning with real hardware.
- Real engineering depth: reproducible Debian image, A/B signed OTA, ZFS-based FailSafe with large VM test suite, GPU passthrough, hardware EC control.
- Huge existing app catalog (300-400 packages) and a packaging contract that is now agent-friendly (AGENTS.md + skills, lint CI).
- First-class **agent access**: MCP built into the OS with per-agent tokens and per-capability grants incl. self-management of the OS. This is the closest thing to OneMind's AI-native pitch and is already shipping.
- Multi-arch (amd64 + Pi) and DIY path grows the user base.

Weaknesses / limits
- **License is noncommercial** - nobody can build a business on it; Umbrel controls the commercial upside. Not truly open source.
- **Single node by design**: one Docker host, one ZFS pool; no clustering, no Kubernetes, no HA; app isolation = Docker only (shared network treated as "untrusted" but not segmented per app; apps run as root in many images).
- Security model: owner-centric login + optional 2FA and a gateway; multi-user is new in 2.0; MCP guarded by bearer tokens (good) but MCP `manageSystem` and `control_machine` are powerful. Docker socket banned for store apps (good). Community store apps are unreviewed.
- Remote access depends on a user-installed Tailscale app (no first-party relay found); no built-in public ingress/identity story (Authentik-style SSO, Cloudflare tunnel, etc. are third-party apps).
- No robotics/IoT/TAK/XR story in the OS itself (Machines can host Home Assistant OS; USB passthrough added in 2.1 beta). No fleet management of many devices.
- Pricing page opacity (no visible amounts), manufacturer undisclosed.

## Lessons for OneMind OS

1. **Do not fork umbrelOS.** PolyForm Noncommercial blocks selling hardware or services with it. If OneMind wants to be an "Umbrel competitor", build on permissive/GPL pieces (Debian, Rugix [MIT/Apache], ZFS, libvirt, Docker/k3s) and treat Umbrel as a UX reference only.
2. **Steal the architecture patterns, not code**: Debian image built in a pinned, reproducible Docker build; Rugix A/B OTA with signed manifests and a rollback-safe ZFS feature set (`compatibility=openzfs-2.3`); one daemon with typed tRPC end-to-end; vm tests that exercise real RAID in QEMU.
3. **App contract**: a compose-based manifest with `manifestVersion`, `storage.dataRoot`, `folderAccess`, `permissions`, `dependencies/implements`, `widgets`, `backupIgnore` is a well-validated design. OneMind can adopt Umbrel-compatible manifests so the 300+ umbrel-apps are portable (check licensing first - none declared) while adding fields for **NATS subjects, agent tools (MCP), TAK/CoT feeds, device classes (ROS/IoT)**.
4. **MCP-native OS is already table stakes for Umbrel.** Differentiate by going deeper: OneMind agents as first-class roles (the agent roster), policy-scoped capabilities per agent (Umbrel's `apps/files/machines/manageSystem` grant model is a good starting schema), audit log of agent actions, human-in-the-loop for destructive ops (Umbrel limits deletion to Trash and never overwrites - copy that safety posture), and an MCP surface that also covers robotics, IoT, TAK and XR.
5. **Gateway/auth**: move proxying into the daemon (Umbrel dropped per-app proxy containers in 2.0) and put identity in front of everything (OneMind already runs Authentik - an advantage over Umbrel's single-owner login model). Keep a clean per-app auth whitelist mechanism for mobile/webhook clients.
6. **Native clients matter**: Umbrel ships iOS, macOS, Android and Windows apps that do background photo backup and mount the box as a drive, and discover over LAN and Tailscale. A OneMind OS equivalent should include a TAK/ATAK-friendly mobile path.
7. **Hardware**: Umbrel's two SKUs (N150 16GB palm box; i3-N300 4-NVMe 2.5GbE box with FailSafe) set the price/spec bar; undercutting requires either a better CPU/ram/10GbE story (AI inference, GPU/eGPU) or an edge/robotics-specific SKU. Their DIY path (USB installer, Pi 5) proves free software + paid hardware works - but under a commercial-friendly license.
8. **Storage**: ZFS mirror + SSD special/L2ARC accelerator is a pragmatic single-node design; OneMind may need a multi-node/k8s story (Umbrel has none) as the true differentiator for "sovereign cloud OS" at team/edge scale.
9. **Site**: Next.js on Vercel with i18n in 29 languages and PostHog; heavy marketing around a "do the math vs iCloud" TCO story.

## Sources
- https://github.com/getumbrel/umbrel (README, LICENSE.md, AGENTS.md, packages/os/{README.md,umbrelos.Dockerfile,mender.cfg,rugix/rugix-bakery.toml,rugpi-image}, packages/umbreld/package.json, source/modules/{mcp,update,machines,hardware,lan-ingress,apps,files,photos,system/tailscale.ts}, packages/ui/package.json, clients/README.md, releases/)
- https://github.com/getumbrel/umbrel/releases/tag/2.0.0 (and `gh release list`; 2.0.1, 2.1.0-beta.1)
- https://github.com/getumbrel/umbrel/blob/master/releases/2.1.0-beta.1-release-notes.md
- https://github.com/getumbrel/umbrel/wiki/License-FAQ (raw wiki) and https://polyformproject.org/licenses/noncommercial/1.0.0
- https://github.com/getumbrel/umbrel-apps (README.md, AGENTS.md, .agents/skills/umbrel-package-app/SKILL.md, immich/umbrel-app.yml, immich/docker-compose.yml, .github/PULL_REQUEST_TEMPLATE.md, .github/workflows/lint-apps.yml)
- https://github.com/getumbrel/umbrel-community-app-store (umbrel-app-store.yml)
- https://umbrel.com , /umbrel-home , /umbrel-pro , /downloads , /support/getting-started/what-is-umbrel (HTML + headers via curl/WebFetch)
- https://community.umbrel.com/t/introducing-the-new-upgraded-umbrel-home-now-more-affordable-than-ever/15197
- https://blog.getumbrel.com/seed-6d09aa08f8ac and Caplight (search results, secondary)
- Search-result snippets only (not opened): Umbrel Pro launch price/date, founders/CTO, framer.umbrel.com staging pages
