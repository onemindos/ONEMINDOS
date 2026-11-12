<!-- SPDX-License-Identifier: Apache-2.0 -->
# umbrelOS 2 study: system and OS (updates, system API, events, network, reset, migration)

**Date:** 2026-11-12 · **Status:** study + proposal · **umbrelOS read at:** tag `2.1.0-beta.1`, commit `6f357e18d0a4` · **Scope:** `packages/umbreld/source/modules/{update,system,system-ng,notifications,event-bus,widgets,migration,server,dbus,startup-migrations}`, `packages/os/**`, `packages/ui/src/routes/{settings,live-usage.tsx,factory-reset,confirm-static-ip}`, `clients/**` · **OneMind specs this feeds:** [UPDATES](../leap/core/UPDATES.md), [NOTIFICATIONS](../leap/core/NOTIFICATIONS.md), [DASHBOARD](../leap/core/DASHBOARD.md), contract [§2, §3, §10](../../sdk/contracts/poc-v0.md), `docs/architecture/NETWORKING.md` (branch `docs/core-architecture`/net worktree), `docs/strategy/umbrel-parity.md` (branch with the UI parity audit).

> **Explain it like I am the founder**
> umbrelOS updates the whole system as one signed image into a spare slot, like we do. Their signing is careful, but they decide "the new system is fine" the moment their main service starts, before any app has come back. We only keep a new system after it passes repeated, fresh health checks, and we fall back on our own if it does not. That is our biggest lead here.
> They are ahead on finished polish: Wi-Fi and fixed-IP settings that undo themselves if you lose the connection, a "move to new hardware" wizard, factory reset, a live CPU/memory/storage screen, and small native apps for Mac and Windows that find the box on your network.
> **"Does umbrel have a desktop?"** Yes, in two senses. (1) The web interface *is* a desktop: wallpaper, dock, app grid and widgets (`packages/ui/src/modules/desktop/`). (2) They ship native companion apps: a macOS menu-bar app and a Windows tray app (`clients/apple/macos`, `clients/windows`) that find the box on the LAN, trust its certificate, connect its file shares as drives and open the web UI. OneMind has the Home design (UI stream) and a phone shell, but no desktop companion yet; epic U2-SYS-11 below adds one.

**Licence rule for this page.** umbrelOS is PolyForm Noncommercial 1.0.0 (checked at the commit above). This page describes its architecture and flows and cites paths. Nothing here is copied code, UI text, assets or a line-by-line paraphrase. Every OneMind design below is our own, built on the components and licences listed in §4.1.

---

## 1. How umbrelOS does it

### 1.1 Shape of the system

One Node.js daemon, `umbreld`, owns everything: apps, files, users, updates, networking, hardware. Each area is a module class with `start()`/`stop()` (`packages/umbreld/source/index.ts`). The OS image is Debian (trixie) built into A/B system partitions with **Rugix** (Rugix Bakery to build, `rugix-ctrl` on the device). The web UI (`packages/ui`, React) and the native clients talk to `umbreld` only through **tRPC** over HTTP and WebSocket.

```
browser / macOS / Windows / iOS / Android ──tRPC (HTTP + WS)──► umbreld (Node, one process)
                                                              ├─ update ─► rugix-ctrl update install ─► inactive slot
                                                              ├─ system ─► nmcli, df, /proc, reboot, rugix-ctrl system commit
                                                              ├─ event-bus (in-process Emittery) ─► tRPC subscriptions
                                                              ├─ notifications (strings in the JSON store)
                                                              └─ system-ng ─► /etc/avahi/services (mDNS)
```

### 1.2 OS updates

**Build** (`packages/os/`):
- `build.sh` + `rugix/rugix-bakery.toml` build the images and update bundles per target: `umbrelos-amd64` (GRUB EFI, GPT, fixed 8 GiB system slots), a Raspberry Pi target (`rpi-tryboot` boot flow) and an amd64 "legacy" target for devices first flashed with Mender. File-system UUIDs and hash seeds are fixed so builds are reproducible (`rugix/fix-umbrelos-reproducible.sh`).
- **Mender is legacy.** `mender.cfg` (mender-convert settings, partition UUIDs, data-partition mkfs options) still exists, but 2.1 installs with Rugix. `rugix/recipes/setup-rugix-mender/` and `startup-migrations/index.ts` (`finalizeMenderToRugixStateMigration`) migrate old Mender devices in place, keeping Mender's partition layout under a `mender-grub` boot flow.
- `create-release-manifest.sh` writes a plain-text **release manifest**: version and display name (from `umbreld/package.json`), commit date, commit, the Docker image index digest, and every file with its SHA-256; each update bundle also carries its Rugix bundle hash, boot flow and architecture. Release notes per version live in `release-notes/<version>.md`. CI timestamps the manifest with OpenTimestamps.
- `hash-update-bundle.sh` refuses bundles that would be unsafe with Rugix: bundles without a full system payload (the device would reboot into whatever stale system is in the other slot) and bundles with a script payload (Rugix would run it before checking its hash).

**Trust model** (`modules/update/release-signing.ts`, `signing-keys.ts`, `umbrelos-signing-keys.txt`):
- One hard-coded **root key** (secp256k1, Bitcoin signed-message format). The root signs a dated **approved signing keys list**: signer keys (P-256), a required signature count (m-of-n), **revoked releases** by manifest hash, and a chain of root-key handovers.
- A release is valid if its manifest carries m valid signer signatures (or one root signature). Release notes are signed separately; a release installs even if its notes fail, they are just not shown.
- The device keeps the newest keys list it has seen (bundled, saved copy, fetched daily from several URLs, or carried inside a release's signature file) and never goes back to an older one (`SigningKeys.#keepNewest`). That is their rollback/revocation defence for keys.
- Download sizes are capped (`readBody`, 1 MiB for text), and the manifest must be exactly its signed text.

**Device flow** (`modules/update/update.ts`, `install-release.ts`, `rugix.ts`, `routes.ts`):
1. `check`: ask the update server for the latest release URL, sending version, device id, platform, channel (`stable`/`beta`), boot flow and architecture; download manifest + signatures + notes; verify; return `available`, version, name, notes filtered to versions newer than installed, and a **manifest hash**.
2. `install` takes that manifest hash back and refuses if the server now points at a different release (protects the "what I saw is what I install" gap). The latest release must be newer than installed (no rollback through the server). Installing an arbitrary release URL, or skipping verification, is root-only via the `umbreld` CLI (`update/cli.ts`), never through the API.
3. If the manifest pins an **update script** for this device, it is downloaded, hash-checked and run as root with a documented environment; it reports progress and can declare the release installed itself. Otherwise `rugix-ctrl update install --reboot set --bundle-hash <h>` streams the bundle, verifying as it goes, into the inactive slot.
4. Progress goes to the in-process event bus (`system:update-status`), the UI also polls `update.status`. On success the API sets the system status to `updating`, stops `umbreld`, and reboots.
5. **Commit:** on every start, `umbreld` calls `rugix-ctrl system commit` early in `start()` (`index.ts` ~line 241, `system/system.ts` `commitOsPartition`). The new slot is made permanent as soon as the daemon process runs, before apps, Docker workloads or the UI are checked. The only automatic fallback is the boot loader's try-once if the kernel or `umbreld` never starts.

**User flow:** Settings shows the current version and a "check for update" row; the confirm dialog (`routes/settings/software-update-confirm.tsx`) shows the signed notes; a full-screen progress view follows; after reboot a "What's new" modal (`routes/whats-new-modal.tsx`, `whats-new.ts`). Release channel switch lives under Advanced settings.

### 1.3 System API (`modules/system`, `system-ng`)

- `system/routes.ts` is one large tRPC router: online/version/status (public), uptime, CPU temperature, disk/memory/CPU/GPU usage **per app** (they map PIDs to apps, `getAppPids`), IP addresses, hostname, network interfaces, static IP, Tor hidden service, external DNS toggle, shutdown/restart, logs, factory reset. Three access levels: `publicProcedure`, `publicProcedureWhenNoUserExists` (onboarding/recovery), `privateProcedure` (owner), `privateProcedureWithMembers`.
- `system-ng/` is the in-progress rewrite: `device.ts` (identity and specs from `lscpu`, `/proc/meminfo`, `dmidecode`, `df`, `lsblk`) and `advertisement.ts` (mDNS). The comment in `system-ng.ts` says it replaces `system` module by module.
- `dbus/dbus.ts` listens to systemd unit events over D-Bus to raise a throttled `system:disk:change` event when disks appear or vanish.
- `startup-migrations/index.ts` runs idempotent fix-ups at every start (Mender→Rugix state, legacy data layout, port moves).

### 1.4 Events, notifications, widgets, live usage

- **Event bus** (`event-bus/event-bus.ts`): an in-process typed emitter (Emittery) with a fixed event list (app progress, backup/restore progress, update status, RAID progress, machines, notifications change, photos, file watcher batches). It yields to the event loop every ~16 ms during bursts. `event-bus/routes.ts` exposes one `listen` subscription; members get only an allow-listed, per-account-filtered subset; progress events are seeded with a snapshot so a late subscriber does not miss state. `server/trpc/coalesce-writes.ts` corks the WebSocket per tick to batch frames.
- **Notifications** (`notifications/notifications.ts`): a list of **plain id strings** in the JSON store, newest first, deduped by value; account-scoped ones are prefixed with the account id; the bus only says "changed" and clients refetch. No severity, no channels, no push, no fix action.
- **Widgets** (`widgets/routes.ts`, `system/system-widgets.ts`): an account enables up to three widgets; each widget is a server function returning a typed card (`text-with-progress`, stats, ...) with a refresh interval and a deep link (for example into Live Usage). App widgets come from the app's manifest and are filtered by app sharing for members.
- **Live usage** (`ui/src/routes/live-usage.tsx`): a dialog with storage, memory, CPU (and GPU) tabs, charts, per-app rows and app actions.

### 1.5 Network and discovery

- **Wi-Fi** (`system/wifi-routes.ts`, `system.ts`): `nmcli` scans, connects, saves the credentials in the store, and on failure tries to restore the previous network; `restoreWiFi` re-applies at boot.
- **Static IP** (`system.ts` `setStaticIp`, `routes.ts` `confirmStaticIp`, `ui/src/routes/confirm-static-ip`): apply with `nmcli`, then wait up to 30 s for the browser to call a public `confirmStaticIp` from the **new** address; no confirmation → revert to the previous config. Only then is the setting persisted.
- **LAN discovery** (`system-ng/advertisement.ts`): writes an Avahi service file advertising a private service type on port 80 with one TXT record, a random discovery id (regenerated on factory reset; no username, no version, by design). `system.discoveryInfo` and `system.localHttpsIdentity` (public) let a client confirm identity and bootstrap trust in the box's local CA before signup (tests in `system-ng/advertisement.integration.test.ts`).
- **Avahi patch** (`packages/os/avahi-patches/iface-Check-for-IFA_F_TENTATIVE.patch`): an **upstream avahi** fix (LGPL, by its upstream author) that skips IPv6 addresses still in duplicate-address detection, which otherwise break mDNS sends. umbrel carries it because Debian's package lacks it.

### 1.6 Factory reset and migration

- **Factory reset** (`system/factory-reset.ts`): `rugix-ctrl state reset --backup` renames the state directory (instant), reboots, and `umbreld` deletes the renamed copy in the background. RAID-backed or failed-mount devices use a hook script instead. Public when no user exists (recovery), otherwise password-confirmed in the UI.
- **Migration assistant** (`migration/`, `ui/src/routes/settings/migration-assistant.tsx`): plug the old device's drive in by USB; `umbreld` finds an external drive holding an install, checks space and version, then copies the data directory over and reboots. Status is a polled global (the code itself marks it as to-be-refactored).

### 1.7 Clients and API contract

- tRPC routers are merged in `server/trpc/index.ts`; in-process callers use the same procedures (`createInternalTrpcCaller`). `server/trpc/client-contract.ts` is a **type-level compatibility ledger** for released native clients: if a server change breaks a field an installed iOS/macOS/Windows app sends or decodes, the typecheck fails.
- Native clients (`clients/README.md`): `apple/UmbrelKit` (Swift package: discovery, pinned local HTTPS, sessions, Keychain), macOS menu-bar app, iOS app, Windows WPF tray app with a C# port of the kit (DNS-SD discovery, CA pinned per device without touching the OS trust store, DPAPI secrets, SMB shares mapped as drives), Android.

---

## 2. What OneMind has today

| Area | OneMind piece | Path | State |
|---|---|---|---|
| Image + A/B | RAUC bundle build, slot config | `os/rauc/`, `os/rootfs/`, `os/assemble/` | `main`, emulation only |
| Health gate | Fresh-signal gate: trial / fell-back / committed, `STABLE` passes in a row, G7 version match, verdicts `image-bad` vs `environment-bad`, per-device bad-release list | `os/gate/onemind-health-gate`, `onemind-k3s-check` | `main` |
| Release pipeline | Nightly Debian security rebuild, snapshot pick, SBOM, Trivy + VEX, ClamAV, QEMU battery, signed RAUC + TUF | `os/update/*`, `.github/workflows/security-nightly.yml` | PR #14 |
| Box updater | `onemindd update`: go-tuf v2 client, channels `security`/`stable`, window, postpone, reboot inhibit, pre-update restic snapshot, state machine read back from gate files | `internal/update/`, `deploy/systemd/onemind-update.service` | `main` (#15) |
| CLI | `onemind update status\|check\|apply` | `cmd/onemind/update.go` | `main` |
| Node facts | Heartbeat JSON (board, slot, k3s, memory, disk, GPU; no serials/MAC/IP by contract) on NATS `onemind.node.<id>.status` and `GET :7480/api/v1/node` | `cmd/onemindd`, `internal/{agent,detect,heartbeat}` | `main` |
| Gateway | FastAPI REST + OpenAPI, bearer principals (person/agent), actions with owner approval, hash-chained audit to NATS `onemind.audit` | `core/onemind_core/{app,actions,auth,audit,bus}.py`, contract §3 | `main` |
| MCP | Agent principals, MCP endpoint, scan gate | `core/onemind_core/{scan,mcp}.py` | `feat/gateway-agent-mcp` |
| Updates spec | `/v1/os/*`, `os.update.apply`/`os.rollback` actions, rescue console, fleet staging | `docs/leap/core/UPDATES.md` | proposal |
| Alerts spec | Alert record, NATS `onemind.alert.<source>.<kind>`, content-free push | `docs/leap/core/NOTIFICATIONS.md` | proposal |
| Networking | Mesh (Headscale/tailscaled), `onemind.local` + `<app>.onemind.local` via avahi, per-box CA, `onemind tls trust` | `docs/architecture/NETWORKING.md` (net worktree) | proposal |
| UI | Home/dock/widgets/Updates/Settings designs, mock Updates screen with slots and history | `ui/`, `docs/design/IA.md`, `ui/demo/src/screens/Updates.tsx` | `main` (mock) |
| Not present | Wi-Fi, static IP, factory reset, migration assistant, live usage per app, event stream to clients, desktop companion | – | – |

---

## 3. Match and beat

### 3.1 Where OneMind already beats umbrelOS

| Topic | umbrelOS 2.1 | OneMind |
|---|---|---|
| **When a new OS is kept** | Committed as soon as `umbreld` starts (`index.ts` → `commitOsPartition`); a release that boots but breaks apps, Docker or the UI is permanent | Kept only after `STABLE` consecutive fresh passes of core health within a deadline; otherwise marked bad and rolled back automatically (`os/gate/onemind-health-gate`) |
| **Why it rolled back** | No verdict; failure is a status string | Named check (G1–G8) and verdict `image-bad` (final) or `environment-bad` (bounded re-offer) |
| **Freeze / replay defence** | Newest-keys-list rule and "must be newer" check; no expiry on release metadata, so a frozen mirror can hide a new release indefinitely | TUF: signed expiries on timestamp/snapshot/targets stop freeze and rollback attacks, plus threshold roles |
| **Who may update** | Any owner session; MCP agents act with the owner's rights | Updates are actions: agents may **request** `os.update.apply`, only the owner approves; rollback needs step-up; policy changes never by agents (UPDATES §3.2) |
| **Security cadence** | Releases when umbrel cuts them | Nightly rebuild when Debian ships a security fix, scanned (Trivy + VEX, ClamAV) and QEMU-tested before signing |
| **Backup before update** | None for OS updates | restic snapshot before install (`internal/update`) |
| **Fleet** | One box | Canary node first, then one by one (CORE-UPDATE-9) |
| **Bus** | In-process emitter, dies with the daemon, not reachable by other processes | NATS: durable, multi-node, per-subject permissions; the same events feed audit, alerts and clients |
| **Audit** | Logs only | Hash-chained audit of every decision |

### 3.2 Where we must match (gaps)

| Gap | umbrelOS reference | OneMind epic |
|---|---|---|
| "What I saw is what I install" binding between check and install | `update.ts` manifest hash | U2-SYS-1 |
| Signed release notes and a "What's new" after reboot | `release-signing.ts`, `whats-new-modal.tsx` | U2-SYS-2 |
| Live event stream to UI and native clients with per-account filtering and snapshot seeding | `event-bus/routes.ts` | U2-SYS-3 |
| System-raised notifications (update failed, disk low) | `notifications/` | U2-SYS-4 (feeds CORE-NOTIFY) |
| Live usage per app and system widgets | `system.ts` usage fns, `system-widgets.ts`, `live-usage.tsx` | U2-SYS-5 |
| Wi-Fi and static IP with automatic revert | `wifi-routes.ts`, `setStaticIp` | U2-SYS-6 |
| LAN discovery with a random id and pre-signup CA bootstrap | `system-ng/advertisement.ts` | U2-SYS-7 |
| Factory reset | `factory-reset.ts` | U2-SYS-8 |
| Move to new hardware | `migration/` | U2-SYS-9 |
| Restart/shutdown from the UI | `system/routes.ts` | U2-SYS-10 |
| Native desktop companion | `clients/apple/macos`, `clients/windows` | U2-SYS-11 |
| Installing from a file or mirror (offline) | `update/cli.ts` (root, by URL) | U2-SYS-12 (= CORE-UPDATE-7) |
| Signed revocation of an already-published release | keys list `revokedReleases` | U2-SYS-13 |
| Client compatibility ledger | `client-contract.ts` | U2-SYS-3 acceptance (OpenAPI compat check, `sdk/openapi/compat/`) |

### 3.3 Where we will beat them once built

- **Static IP / Wi-Fi as a reversible, audited action:** same confirm-or-revert idea, but enforced by `onemindd` on the host (survives a gateway restart), recorded in audit, and refused while an OS trial is running.
- **Factory reset that cannot destroy backups by accident:** it is a `critical` action with passkey step-up, typed confirmation, a forced "take a final backup?" step, and it never touches off-box backup repositories.
- **Migration = restore:** "move to new hardware" reuses the verified backup/restore path (any old box, any medium, partial node moves) instead of a USB-only disk copy between two device models.
- **Events once, everywhere:** the same NATS subjects drive the dashboard, phone, desktop companion, MCP agents (read scope) and alerts; umbrel's bus is reachable only through one daemon's WebSocket.
- **Live usage across nodes**, with the freshness rule (stale vs offline) from contract §2.

---

## 4. OneMind design for this area

### 4.1 Components and licences

| Component | Use | Licence | Pin |
|---|---|---|---|
| RAUC | A/B install, slot status, mark-good/bad | LGPL-2.1 (separate binary) | v1.15.2, commit `4fb7c798…` (`os/versions.lock.yaml`) |
| go-tuf | Box-side TUF client | Apache-2.0 | v2.4.2 (`go.mod`) |
| python-tuf | Repository signing in CI | Apache-2.0 OR MIT | 7.0.1 (`os/versions.lock.yaml`) |
| nats-server / nats.go | Bus, event fan-out | Apache-2.0 | v2.15.3 / v1.55.0 (`go.mod`) |
| restic | Pre-update and pre-reset snapshots | BSD-2-Clause | pin at adoption in `os/versions.lock.yaml` |
| NetworkManager | Wi-Fi and static IP on the host, driven over D-Bus | GPL-2.0+ daemon (separate process; we do not link `libnm`, we speak D-Bus) | Debian 13 package, snapshot-pinned by the image stream |
| godbus/dbus (Go) | D-Bus client for NetworkManager and systemd | BSD-2-Clause | pin at adoption in `go.mod` |
| avahi-daemon | mDNS publishing | LGPL-2.1+ (separate process) | Debian 13 package; if it lacks the upstream IPv6-tentative fix, the image stream carries that **upstream avahi** commit, never umbrel's copy |
| Tauri (desktop companion) | Tray app shell for macOS/Windows/Linux | MIT OR Apache-2.0 | pin at adoption |

Nothing from umbrelOS is reused. Rugix (Apache-2.0/MIT) was evaluated in the lab already (`C-LAB-debian-rugix-*`); RAUC stays the choice.

### 4.2 Data model

```json
// GET /v1/os/status → per node (extends UPDATES §3.2)
{"node_id": "3f9c2a1b7d4e", "version": "0.1.20261116025704", "booted_slot": "B",
 "channel": "security", "policy": "auto", "window": "02:00-05:00",
 "state": "committed", "progress": null,
 "available": {"version": "0.1.20261118021133", "target_digest": "sha256:…",
               "notes": "…signed markdown…", "security": true, "cves_fixed": 2},
 "last_result": {"version": "…", "result": "rolled_back", "verdict": "image-bad",
                 "check": "G4", "detail": "core pod not Ready since boot"}}
```

```json
// Event envelope on NATS and on the client stream (U2-SYS-3)
{"schema": "onemind.event/v1", "subject": "onemind.os.<node_id>.update",
 "seq": 4182, "at": "2026-11-16T03:12:00Z", "audience": {"roles": ["owner"]},
 "data": {"state": "installing", "progress": 41.2}}
```

```json
// Network intent kept by onemindd (U2-SYS-6); never in the heartbeat
{"iface_key": "eth:1", "mode": "static", "address": "<cidr>", "gateway": "<ip>",
 "dns": ["<ip>"], "pending_confirm_until": "2026-11-16T03:13:00Z", "previous": {"mode": "dhcp"}}
```

New NATS subjects (all under `onemind.`, contract §1 style): `onemind.os.<node>.update`, `onemind.os.<node>.usage` (every 10 s, optional, from `onemindd`), `onemind.net.<node>.change`, `onemind.alert.os.<kind>`, `onemind.alert.net.<kind>`.

### 4.3 API, CLI and MCP surface

All writes are actions (`POST /v1/actions`, contract §3). Risk levels follow CONTRACT-12-DRAFT §12.2.

| Gateway | Action type | Risk | CLI | MCP |
|---|---|---|---|---|
| `GET /v1/os/status` | – | read | `onemind update status` | `os_status` (read) |
| `POST /v1/os/apply {node_id, target_digest}` | `os.update.apply` | high | `onemind update apply` | `request_action` |
| `POST /v1/actions os.rollback` | `os.rollback` | destructive, step-up | `onemind update rollback` | never |
| `PUT /v1/os/settings` | `os.update.settings` | high | `onemind update set` | never |
| `GET /v1/events?subjects=…` (SSE; `Last-Event-ID` resumes) | – | read, filtered per principal | `onemind events --follow` | resource subscription (read scope) |
| `GET /v1/nodes/{id}/usage`, `GET /v1/apps/{id}/usage` | – | read | `onemind top` | `node_usage` (read) |
| `GET /v1/widgets`, `GET /v1/widgets/{id}` | – | read | – | – |
| `GET /v1/net/{node}`; `POST …/wifi`, `…/ip` | `net.wifi.set`, `net.ip.set` | high, auto-revert | `onemind net wifi\|ip` | never (owner only) |
| `POST /v1/net/{node}/confirm` | – | public, only valid while a change is pending, single-use nonce | – | – |
| `POST /v1/actions node.restart\|node.shutdown` | `node.power` | high | `onemind node restart` | `request_action` |
| `POST /v1/actions system.factory_reset` | `system.factory_reset` | critical, owner-only, passkey + typed name, never policy-approved | `onemind reset` | never |
| `GET /v1/discovery` | – | public, no session | – | – |

`onemindd` exposes these on a local Unix socket (CORE-UPDATE-2, `internal/update/api.go`); the gateway proxies and turns writes into actions. The `:7480` HTTP API stays read-only until the rescue console replaces it.

### 4.4 UI screens (UI stream; designs in `docs/design/`)

- **Updates** (`/updates`): per node card with booted slot, channel, state, last result with verdict in plain words; "What's new" sheet after a committed update; signed notes in the confirm sheet; "Request update" for non-owners.
- **Live usage** (dialog from Home widgets and Nodes): CPU, memory, storage, temperature, GPU; per node and per app; stale data greyed with age.
- **Network** (Settings → Network per node): interfaces, Wi-Fi list, DHCP/static; applying shows a countdown and the new address to open; it reverts on its own if not confirmed.
- **Power and reset** (Settings → System): restart/shutdown per node with "apps affected"; factory reset as a three-step flow (backup offer, typed name, passkey).
- **Move to new hardware** (onboarding + Settings): "restore from a backup" at first run; on the old box, "prepare move" takes a final verified backup.
- **Desktop companion**: tray icon listing boxes found on the LAN, open dashboard, mount shares, show alert count; first contact pins the box CA after showing its fingerprint.

### 4.5 Security

- Update trust stays TUF root in the image + RAUC signature; the gateway may only ask `onemindd` to install a target the box itself selected and verified, identified by `target_digest` (stale → `stale_precondition`).
- Event stream: subjects are allow-listed per role; agents get read scopes only for subjects named in their grant; payloads never carry secrets (contract §2 rules apply).
- Network confirm endpoint is unauthenticated by necessity (new origin), so it accepts only a single-use nonce issued with the change, and only while the change is pending.
- Discovery advertises a random id only (no version, no username, no hardware ids), regenerated on reset; trust in the box CA is pinned per box by clients, never added to the OS store silently.
- Factory reset and rollback are never available to agents or standing approvals.

---

## 5. Epics

Owner paths follow [WORKSTREAMS.md](../leap/WORKSTREAMS.md). Where an epic overlaps an existing one, it **extends** that epic's spec rather than creating a parallel stream.

| ID | Title | Size | Owner paths (stream) | Acceptance | Depends on |
|---|---|---|---|---|---|
| U2-SYS-1 | Bind apply to the checked target | S | `internal/update/**`, `core/onemind_core/os_updates.py` (Updates, `feat/os-api`) | Apply with a `target_digest` that no longer matches the selected TUF target returns 409 `stale_precondition` and installs nothing; unit test in `internal/update/engine_test.go` | CORE-UPDATE-2 |
| U2-SYS-2 | Signed release notes + What's new | S | `os/update/build-release.sh` (pipeline), `dashboard/src/pages/Updates.tsx` (Updates) | Notes are a TUF target; tampered notes are hidden but the update still installs; after a committed update the UI shows the notes once per user | CORE-UPDATE-3 |
| U2-SYS-3 | Client event stream (SSE) from NATS | M | `core/onemind_core/events.py` (Gateway core, `feat/api-<n>-events`), `sdk/openapi/compat/` | Owner sees `onemind.os.*` events within 1 s of publish; an agent without the scope gets 403 at subscribe time; `Last-Event-ID` resume loses no event in a 1000-event burst; OpenAPI compat check fails on a removed field | DEV-API-1 |
| U2-SYS-4 | OS and network alert sources | S | `internal/update/**` (Updates), `core/onemind_core/alerts.py` consumer (Notifications) | A forced rollback raises one `onemind.alert.os.rolled_back` alert naming the check; update check failing 48 h raises `os.check_failing`; dedupe key prevents repeats | CORE-NOTIFY-1, U2-SYS-3 |
| U2-SYS-5 | Live usage and system widgets | M | `internal/detect/**` usage collector (Fabric owner hook), `core/onemind_core/metrics.py` (Dogfood), `dashboard/src/components/**` (Dashboard) | Per-node CPU/memory/disk/temperature and per-app CPU/memory shown; values older than 30 s are marked stale; collector costs ≤ 1 % of one Pi 5 core | DASH-1 |
| U2-SYS-6 | Wi-Fi and static IP with auto-revert | M | new `internal/netcfg/**`, `cmd/onemind/cli/net.go` (core branch writes the group), image stream for NetworkManager in `os/rootfs/` | QEMU test: set a wrong gateway, do not confirm, the box reverts within 60 s and raises `onemind.alert.net.reverted`; confirmed change persists across reboot; refused while an OS trial is running | CORE-UPDATE-2, SEC-2 |
| U2-SYS-7 | LAN discovery and pre-signup CA bootstrap | S | net stream (`docs/architecture/NETWORKING.md` §9 owner), `os/rootfs/` avahi config | `avahi-browse` shows the OneMind service with only a random id; `GET /v1/discovery` returns the same id and the CA; id changes after factory reset; image check confirms the IPv6-tentative avahi fix is present | FABRIC-1 |
| U2-SYS-8 | Factory reset as a critical action | M | `internal/rescue/**` (Updates, `feat/rescue`), `core/onemind_core/os_updates.py` | Reset requires passkey + typed name; offers and verifies a final backup; off-box repositories untouched; box returns to onboarding; an agent request is refused with 403 | CORE-UPDATE-8, CORE-SEC-2, BACKUP-2 |
| U2-SYS-9 | Move to new hardware | M | `internal/backup/**`, `core/onemind_core/backups.py` (Backups) | Restore onto a blank box at onboarding brings back apps, users and hub identity; nodes re-find the hub by mDNS + pinned CA | BACKUPS restore epic, U2-SYS-7 |
| U2-SYS-10 | Restart and shutdown per node | S | `core/onemind_core/os_updates.py` (Updates), `dashboard/src/pages/Settings*.tsx` (Dashboard) | Request lists affected apps; refused during an OS trial; audit records requester and approver | CORE-UPDATE-2 |
| U2-SYS-11 | Desktop companion (tray app) | L | new `desktop/**` stream (add a row to WORKSTREAMS §2 first) | macOS and Windows builds find a box on the LAN, pin its CA after fingerprint confirmation, open the dashboard, show alert count; no secrets outside the OS keychain/DPAPI | U2-SYS-3, U2-SYS-7, MOBILE auth |
| U2-SYS-12 | Offline and mirror installs | M | `internal/update/**` (Updates) | `onemind update apply --from <file>` verifies TUF metadata bundled with the file; expired timestamp within the offline grace is accepted only for a target newer than installed | CORE-UPDATE-7 |
| U2-SYS-13 | Yank a published release | S | `os/update/**` (pipeline), `internal/update/**` | Yanking removes the target and adds a signed `yanked` entry; boxes in `pending_reboot` for it cancel the trial marker before reboot; boxes already committed get an alert | CORE-UPDATE-1 |

---

## 6. Limits of this page

- umbrelOS was read at source level, not run. The commit timing claim is from `index.ts` and `system.ts` at the pinned commit; a VM run should confirm that no later service re-checks health.
- Rugix's own boot-loader fallback (try-once) protects against a kernel or `umbreld` that never starts; that part is equivalent to RAUC + GRUB in OneMind.
- Effort sizes assume the contract §12 PRs land first, as in [BACKLOG.md](../leap/BACKLOG.md).
