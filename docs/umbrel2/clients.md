<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native clients: phones, Mac and Windows (umbrelOS 2.1 study and OneMind plan)

**Date:** 2026-11-12 · **Status:** study + proposal · **Stream:** `feat/umbrel2-study` (doc only) · **umbrelOS source read:** tag `2.1.0-beta.1`, commit `6f357e18d0a4`, directory `clients/` plus the server side in `packages/umbreld/source/modules/{auth,photos,system-ng,server/trpc}/`.
**Builds on:** [MOBILE](../leap/core/MOBILE.md), [SECURITY](../leap/core/SECURITY.md), [NOTIFICATIONS](../leap/core/NOTIFICATIONS.md), [BACKUPS](../leap/core/BACKUPS.md), networking design `docs/architecture/NETWORKING.md` (branch `feat/core-net`), contract §3 and §11 (`sdk/contracts/poc-v0.md`), [WORKSTREAMS](../leap/WORKSTREAMS.md).

> **Legal rule for this page.** umbrelOS is licensed PolyForm Noncommercial 1.0.0 (checked at the tag above). OneMind is sold, so this page only *describes* how umbrelOS works and cites file paths. No umbrelOS code, strings, icons, wallpapers or UI text is copied into OneMind, and nothing below is a line-by-line paraphrase. Every OneMind piece is our own, built on permissively licensed components recorded in §4.7.

> **Explain it like I am the founder**
> **"Does Umbrel have a desktop app?"** Yes, two, and both are small. On a Mac it is a **menu-bar icon**; on Windows a **tray icon**. Each one finds the Umbrel on your Wi-Fi, signs you in, puts the Umbrel's shared folders in Finder or File Explorer (as a network drive), and opens the Umbrel web page. It does not back up your computer, does not show alerts beyond "your sign-in expired", and there is no Linux app. The "desktop look" you see in screenshots (wallpaper, dock, app grid) is the umbrelOS **web page**, and their phone apps redraw that same look natively (wallpaper behind app tiles).
> Their phone apps (iPhone, Android) are bigger: find the box, sign in, open apps inside the app, and **back up the camera roll in the background**.
> **What we do:** keep our Expo phone app, add photo backup to it, and build **one desktop app for Mac, Windows and Linux with Tauri** (one codebase, small download, permissive licence). It does what theirs does, and adds: approvals and alerts from the tray, a per-device sign-in that a stolen laptop file cannot reuse, laptop folder backup, and a "safe to delete from phone" mark that only appears once a photo is also in a verified backup.

---

## 1. How umbrelOS does it

### 1.1 Layout (paths at `6f357e18d0a4`)

| Path | What | Stack |
|---|---|---|
| `clients/apple/UmbrelKit/` | Shared Swift package: discovery, pinned HTTPS, native sessions, saved devices, Keychain, the photo-backup engine (`Sources/UmbrelKit/Backup/`) | Swift Package |
| `clients/apple/ios/` | iPhone app (onboarding, Home, Apps, Photos, Profile, in-app browser) plus `BackgroundUploadExtension/` (PhotoKit background upload extension) | SwiftUI, iOS 26.5 target |
| `clients/apple/macos/` | Menu-bar app (`Sources/Umbrel/StatusItemController.swift`, `Mounter.swift`, `UpdateController.swift`) | SwiftUI + AppKit, macOS 14 target, Sparkle 2 updates |
| `clients/android/umbrelkit/` | Kotlin port of UmbrelKit, including its own backup engine (`com/umbrel/kit/backup/`) | Kotlin |
| `clients/android/app/` | Android app (onboarding, Home/Apps/Photos tabs, WebView browser, Tailscale setup helper) | Jetpack Compose, minSdk 30, targetSdk 36 |
| `clients/windows/Umbrel.Core/` | C# port of UmbrelKit (no photo backup) | .NET 10 |
| `clients/windows/Umbrel/` | Notification-area app (`Tray/`, `Services/Mounter.cs`, `Services/UpdateChecker.cs`) | WPF, MSIX packaging |
| `packages/umbreld/source/modules/server/trpc/client-contract.ts` | Type-level ledger that fails umbreld's typecheck if a server change breaks a released client | TypeScript |

The "kit" is one design implemented **three times** (Swift, Kotlin, C#), kept in step by README rules and by the server-side compatibility ledger. Only the Apple and Android kits carry photo backup.

### 1.2 Discovery and pairing

```
box: avahi advertises _umbrel._tcp, TXT id=<device id hint>         (system-ng/advertisement.ts)
                │
client: DNS-SD browse ──► resolve host + IPv4 ──► GET http://<host>/trpc/system.localHttpsIdentity
                                                      → {id, caCertificate}   (plaintext, no credentials)
                │
client: keeps the candidate CA in memory only ──► opens HTTPS to the same host trusting ONLY that CA
        and checks the device id again (proves the box holds the CA's key)  (UmbrelKit/LocalHTTPS.swift)
                │
client: writes the CA pin to Keychain / Keystore / DPAPI, write-once per device id (Keychain.swift)
```

- **Fallbacks:** older boxes without the advertisement, and networks that filter service browsing, are probed by a short fixed list of default `.local` hostnames, never a subnet scan (`Umbreld.swift`, fallback discovery). "Connect by address" covers emulators and custom names.
- **Identity change:** if the box's certificate is reset, the kit never adopts the new CA on its own; the user must remove and re-add the box (`clients/apple/README.md`, `LocalHTTPS.swift`).
- **Hostname is not checked** against the certificate, because the address often is not in it (new DHCP lease, Tailscale userspace mode). The pinned per-box CA alone proves identity.
- **Privacy:** TXT carries only the id hint, not user names (`advertisement.ts` header comment).

### 1.3 Authentication

- **Native session** (`modules/auth/auth.ts`, `createNativeSession`, `refreshNativeAccess`): sign-in with password (+ TOTP if enabled) via `user.loginNative` returns a **1-hour access credential** and a long-lived **device credential**; the device credential refreshes access via `user.refreshNativeAccess` and lives until revoked. The client describes itself with `{id, platform, deviceClass, appVersion, appBuild, osVersion}` (`modules/auth/native-client.ts`), shown in the account's session list.
- **Storage:** Keychain (Data Protection keychain, this-device-only), Android Keystore AES-GCM sealing, Windows DPAPI current-user. The Windows README states the limit plainly: any program running as the same Windows user can read the sealed items.
- **Web session for the in-app browser** (`UmbrelKit/BrowserSession.swift`): the native sign-in also obtains a browser token and cookies, which are replayed into the web view for whichever box address is reachable, so umbrelOS apps open already signed in. Each account gets its own web-view data store, cleared at sign-out.
- **Multi-account:** `user.listAccounts` feeds an account picker; saved devices remember the last account and a per-account profile (name, wallpaper) (`SavedDevice.swift`).

### 1.4 Remote access

- Route selection (`EndpointResolver.swift`, `EndpointResolver.kt`, `EndpointResolver.cs`): every candidate address (LAN IPv4, `.local`, Tailscale) is raced through the **same identity check**; Tailscale is preferred for a short window because it stays stable across networks, then the first verified route wins. A network-path change clears the cached winner.
- Tailscale itself is the user's own Tailscale account and app; the Android app has a helper screen (`main/TailscaleSetup.kt`) that checks the box reported a Tailscale address and links to the Play listing. umbrelOS does not run its own coordinator.

### 1.5 Photo backup (phones)

Server contract: `modules/photos/CONTRACT.md`, `photos/routes.ts`, `photos/api.ts`.

| Step | umbrelOS behaviour |
|---|---|
| Source | Each phone is a *source* (`photos.backupSources`); files land as ordinary files in the account's Home Photos folder under a per-device folder, sharded by resource key |
| Grant | `photos.createBackupGrant` issues a **source-scoped upload grant** (used where the native session cannot be, e.g. the iOS extension); `revokeBackupGrant` ends it |
| Identity | Client computes a stable **resource key** per PhotoKit / MediaStore resource (Live Photo still and motion get separate keys); `UmbrelKit/Backup/PhotoBackupPlanner.swift` is shared by app and extension so both send identical keys and headers |
| Upload | `POST /api/photos/upload` with backup headers; streaming from file, never buffered |
| Receipt | `photos.confirmedBackupResources` answers which keys the box holds; the server **re-opens the indexed file** before confirming. Copies only in Trash do not count, so an emptied Trash cannot make a phone think a photo is safe |
| Ledger (iOS) | SQLite in an App Group, WAL, shared by app and extension; careful interrupt-on-suspend handling (`PhotoBackupLedger.swift`) |
| Background (iOS) | `PHBackgroundResourceUploadExtension` (`ios/BackgroundUploadExtension/`): PhotoKit itself uploads while the app is closed, **only over Tailscale and plain HTTP** because the system uploader cannot use the app's pinned trust. The app also runs its own passes while open, briefly after leaving, and overnight while charging (`ios/Sources/PhotoBackupAppRunner.swift`) |
| Background (Android) | SQLite ledger fed by MediaStore's generation counter; user-initiated data-transfer job (Android 14+) or a `dataSync` foreground service (11–13), then WorkManager passes on library change and hourly (`umbrelkit/.../backup/PhotoBackupWork.kt`, README) |
| Policy | Wi-Fi only unless mobile data is allowed; folder exclusions on Android; losing photo permission pauses, not disables |
| Silence guard | A local reminder pushed a week ahead on every run; it fires only if nothing backed up for a week (`PhotoBackupReminder.swift`) |

### 1.6 Finder and File Explorer

There is **no File Provider (macOS) or Cloud Files (Windows) integration**. Both desktop apps **mount SMB shares**:

- macOS: `NetFSMountURLSync` in-process, macOS chooses the `/Volumes` path; background health checks mount silently; mounts deliberately outlive the app (`macos/Sources/Umbrel/Mounter.swift`).
- Windows: `WNetUseConnection` with `CONNECT_REDIRECT`, Windows assigns the drive letter; session-scoped mappings that outlive the app until logoff; re-adopted on launch only after the box proves its pinned identity (`windows/Umbrel/Services/Mounter.cs`).
- Share list and the account's SMB password come from `files.shares` / `files.sharePassword`; the password stays in memory only.

### 1.7 Notifications

No push on any platform. Local notifications only: macOS "session expired" (`AppState.swift`), the iOS backup-silence reminder, Android's foreground-service progress notification. Box events are not delivered to closed apps.

### 1.8 Updates and distribution

macOS: Developer ID + notarized DMG, Sparkle 2 appcast with EdDSA signatures, checked every 6 h. Windows: MSIX signed with a cloud signing service, App Installer feed with automatic updates off, the app checks every 6 h and installs on user consent. iOS: TestFlight/App Store. Android: Play bundle. Clients update independently of the OS; `client-contract.ts` keeps old clients working.

### 1.9 User-visible flow (summary)

Phone: welcome → local-network permission → radar-style search → "found your box" → account picker → password (+2FA) → Home (wallpaper + app tiles) → Photos tab offers backup → background backup with status line in Profile. Desktop: tray icon → list of boxes found → sign in → per-box detail with "connect" (mount shares) and "open" (web UI) → mounts appear in Finder/Explorer.

---

## 2. What OneMind has today

| Area | State | Path |
|---|---|---|
| Phone app | Expo SDK 58 / React Native 0.88 shell: Connect (URL + static token), Home, Nodes, Apps, Approvals, Activity, Settings; local notifications while open; demo mode | `mobile/` (merged as #21), spec [MOBILE](../leap/core/MOBILE.md) |
| Phone auth | Static bearer token in Keychain / Keystore (`expo-secure-store`, this-device-only) | `mobile/src/storage.ts`, `session.tsx` |
| Pairing plan | QR with URL + CA fingerprint, CA pinning, passkey sign-in, passkey-signed approvals (planned) | MOBILE §3.1–3.2, SECURITY CORE-SEC-1/-2 |
| Push plan | Android UnifiedPush to the box's ntfy; iOS APNs ping-then-fetch through a stateless relay | MOBILE §3.3, NOTIFICATIONS CORE-NOTIFY-3/-4, `apps/ntfy` |
| LAN names, box CA | avahi names `onemind.local`, `<app>.onemind.local`; name-constrained per-box CA; `onemind tls trust` for desktops (planned) | `docs/architecture/NETWORKING.md` §9 (branch `feat/core-net`) |
| Remote access | Headscale coordinator on the hub; phones and laptops use the **official Tailscale apps** against it; adding a device is the action `mesh.device.add` (planned) | NETWORKING §5.5, §10 |
| Gateway API | Contract §3 REST, §11.3 MCP for agents (request only, never approve) | `core/`, `sdk/contracts/poc-v0.md` |
| Backups | restic agent, destinations, verified-restore badge (planned) | [BACKUPS](../leap/core/BACKUPS.md) |
| Desktop client | **None.** Worktree `feat/desktop-client` exists with no commits | – |
| Phone photo backup | **None.** MOBILE lists it as a v1 non-goal; worktree `feat/mobile-photos` exists with no commits | – |
| File shares (SMB/WebDAV) | **None** in core or apps | – |
| Device registry | **None** (tokens map to people/agents, not devices) | – |

---

## 3. Match and beat

| # | Capability | umbrelOS 2.1 | OneMind | Verdict |
|---|---|---|---|---|
| C1 | Find the box on the LAN | `_umbrel._tcp` + hostname fallback | `_onemind._tcp` + `onemind.local` fallback + QR | **Match** |
| C2 | Trust the box | Per-box CA pinned write-once after proof of key | Same principle, plus the CA is **name-constrained** (NETWORKING §9.4) and the QR carries its fingerprint, so first use is not trust-on-first-sight when a QR is used | **Beat** (first-use MITM closed by QR) |
| C3 | Sign in | Password + TOTP | **Passkey** (SECURITY CORE-SEC-2); password only as fallback | **Beat** |
| C4 | Device credential at rest | Keychain / Keystore / **DPAPI (readable by any same-user process)** | Device key generated **non-exportable** in Secure Enclave / Android Keystore (StrongBox if present) / TPM via CNG; refresh requires a proof-of-possession signature (DPoP, RFC 9449) | **Beat**: a copied credential file is useless |
| C5 | Who can add a device | Anyone with the password | A new device is a **request**; owner approves (from phone, tray or dashboard). Children and guests' devices need an adult's approval | **Beat** (fits "agents and people request, owner approves") |
| C6 | Remote access | User's own Tailscale account | Owner's own Headscale on the hub, official Tailscale apps, no vendor coordinator (NETWORKING) | **Beat** (no third-party control plane) |
| C7 | Phone photo backup | Excellent: receipts, Live Photos, iCloud identity, background on both OSes | Same receipt model, plus **client-sent content digest checked before the receipt**, plus a second level: "in a verified off-box backup" before "safe to free up space" | **Match**, **beat** on storage safety |
| C8 | iOS background transport | Plain HTTP over Tailscale only | HTTPS only; extension enabled only when the name-constrained box CA is trusted on the phone (spike), else app-run passes | **Beat** (if the spike passes; otherwise **match**) |
| C9 | Desktop: shares in Finder / Explorer | SMB mount (macOS, Windows) | SMB mount on macOS, Windows **and Linux** (gio/`mount.cifs`), **per-device revocable** SMB credentials | **Beat** |
| C10 | Desktop: back up the computer | None | Folder backup (Documents, Desktop, Pictures) with restic to the box, verified restores | **Beat** |
| C11 | Notifications | Local only, no push | Phone push (UnifiedPush / APNs ping-then-fetch), desktop live alerts over the event stream | **Beat** |
| C12 | Approvals | n/a | Approve from phone (passkey) and from desktop (Touch ID / Windows Hello passkey) with the exact plan | **Beat** |
| C13 | AI agents | MCP settings with a shared grant set | Agents may read device and backup health over MCP; they can **never** add devices, read credentials or mount shares | **Beat** (narrower, audited) |
| C14 | Code sharing | Three kits (Swift, Kotlin, C#) | One TS client kit (logic) + one Rust kit (desktop privileged ops) + shared test vectors | **Beat** on maintenance |
| C15 | Linux desktop | None | Tauri builds `.deb` and AppImage | **Beat** |
| C16 | In-app browser with pinned trust | Yes, both phones, apps open signed in | Phone: later (MOBILE non-goal v1). Desktop v1 opens the system browser after `onemind tls trust` | **Gap, accepted for v1** |
| C17 | Native Home with wallpaper and tiles | Yes (phones) | Phone Home stays a status screen; customization lives in the dashboard (uileap) | **Not matched by choice** (status first) |
| C18 | Old-client compatibility | Type-level ledger `client-contract.ts` | OpenAPI compat check (`sdk/openapi/compat/`, DEV-SDK) + per-client "minimum gateway" table in §4.4 | **Match** |

---

## 4. OneMind design

### 4.1 Components

```
                     ┌────────────────────────── box (hub) ──────────────────────────┐
 phone (Expo)        │ avahi: _onemind._tcp, onemind.local      onemind-edge :443     │
  ├ client kit (TS) ─┼─► GET /v1/discovery (public, cheap)  ─►  gateway (core/)      │
  ├ pin module       │   /v1/auth/* passkeys, device sessions     ├ devices.py        │
  │ (Swift/Kotlin)   │   /v1/devices/*                            ├ photo_ingest.py   │
  ├ photo backup     │   /v1/photos/sources/*  (upload, receipts) ├ shares.py         │
  │ (Expo modules)   │   /v1/shares/*         (SMB creds)         └ events, alerts    │
  └ push (MOBILE)    │                                                              │
                     │ samba app (separate container, GPL-3.0, not linked)          │
 desktop (Tauri)     │ restic REST target for laptop backups (BACKUPS)              │
  ├ UI (TS, shared)  │ person datasets on the Retain StorageClass (CORE-BACKUP-1)   │
  ├ Rust core:       └──────────────────────────────────────────────────────────────┘
  │  mDNS, pinned TLS (rustls), device key (Secure Enclave / TPM), mounts (NetFS / WNet / gio),
  │  restic runner, tray, notifications, updater
  └ official Tailscale app (separate install) for away-from-home
```

**Client kit.** One behaviour spec, two implementations, shared test vectors:

| Piece | Where | Used by |
|---|---|---|
| `@onemind/clientkit` (TS): QR parse, discovery result merge, route race policy, session state machine, backup planner (resource keys, scope rules), receipt reconciliation | `sdk/clientkit/ts/` | mobile, desktop UI |
| `onemind-clientkit` (Rust): mDNS browse, pinned TLS client, device key + DPoP signer, endpoint race, mounts | `sdk/clientkit/rust/` | desktop |
| Native pin + key modules (Swift, Kotlin) as Expo modules | `mobile/modules/onemind-pin/` | mobile |
| Test vectors: QR payloads, discovery replies, CA-mismatch cases, resource-key derivation, receipt diffs | `sdk/clientkit/testdata/` | all three, in CI |

### 4.2 Desktop stack choice

| Option | Licence | Size and footprint | Effort for Mac + Windows (+ Linux) | OS integration | Verdict |
|---|---|---|---|---|---|
| **Tauri 2** (Rust core, system web view) | Apache-2.0 OR MIT | ~10–20 MB installer; uses WKWebView / WebView2 / WebKitGTK | **One codebase, ~1 engineer-quarter to v1**; Linux nearly free | Rust crates reach NetFS (`objc2`), WNet and CNG/TPM (`windows`), Keychain (`security-framework`); tray, autostart, single-instance, deep-link, notification and signed updater are official plugins | **Chosen** |
| Electron | MIT | 100+ MB, bundles Chromium; Chromium security patch cadence becomes ours | One codebase, similar UI effort; native calls via Node add-ons (C++) | Easy cert pinning (`setCertificateVerifyProc`), mature tray | Rejected: size, memory on a 8 GB laptop, patch burden |
| Native per OS (Swift + C#/WinUI, like umbrelOS) | OS SDKs | Smallest | **Two or three codebases, ~2× effort**, two languages to staff; umbrelOS needed a full C# port of its kit | Best (File Provider, Cloud Files, Secure Enclave directly) | Rejected for v1; used only for the optional File Provider extension later (§5 CLIENT-15) |

Why Tauri fits OneMind specifically: the dashboard, mobile app and design tokens are already TypeScript (`ui/`, `dashboard/`, `mobile/`), so the tray UI reuses `@onemind/sdk`, `@onemind/clientkit` and `@onemind/ui` tokens; all trust-sensitive work (TLS pinning, keys, mounts) sits in Rust, outside the web view, so a web-view bug cannot read the device key. Tauri's updater verifies an Ed25519 signature on every update, independent of OS code signing.

**Known limit (UNVERIFIED, spike DESK-S1):** Tauri does not expose a per-navigation server-trust hook for its web views on all three platforms. v1 therefore never loads box pages in the desktop web view. The tray UI is local (bundled assets) and calls Rust commands; "Open dashboard" and app links open the **system browser** after the owner ran `onemind tls trust` (name-constrained CA), or after accepting the browser warning, which the desktop app explains.

### 4.3 Data model (gateway, new tables via one ledger migration per epic)

```jsonc
// client_device
{"id": "dev_7k2m", "person_id": "person:ana", "kind": "phone|desktop",
 "platform": "ios|android|macos|windows|linux", "name": "Ana's laptop",
 "app_version": "1.2.0", "os_version": "15.1",
 "key_thumbprint": "sha256:…",          // JWK thumbprint of the non-exportable device key (RFC 7638)
 "key_storage": "secure_enclave|strongbox|keystore|tpm|software",
 "state": "pending|active|revoked", "approved_by": "person:owner",
 "created_at": "RFC3339", "last_seen_at": "RFC3339",
 "capabilities": ["photo_backup", "shares", "folder_backup", "push"]}

// photo_source (one per phone and library)
{"id": "src_31fa", "device_id": "dev_7k2m", "person_id": "person:ana",
 "folder": "Photos/Ana's iPhone",        // inside the person's dataset; presentation only
 "scope": {"mode": "all|except|only", "albums": []},
 "network": {"cellular": false}, "state": "active|paused|stopped",
 "counts": {"known": 41230, "on_box": 41102, "in_verified_backup": 40877},
 "last_upload_at": "RFC3339"}

// photo_receipt (identity = source + resource key; content = sha256)
{"source_id": "src_31fa", "key": "<64 hex>", "size": 3481122,
 "sha256": "<64 hex>", "stored_at": "RFC3339", "verified_backup_at": "RFC3339|null"}

// share_credential (SMB, one per device and person; password never stored in clear)
{"device_id": "dev_7k2m", "smb_user": "d-7k2m", "created_at": "RFC3339", "rotated_at": "RFC3339"}
```

### 4.4 API surface (contract style of §3; adopted through one contract PR, CLIENT-0)

| Method and path | Who | Returns / does |
|---|---|---|
| `GET /v1/discovery` | anyone (LAN, mesh) | `{"instance_id", "name", "version", "ca_sha256", "min_client": {"mobile": "1.0.0", "desktop": "1.0.0"}}`. No user names. Cheap; rate-limited |
| `POST /v1/devices/requests` | signed-in person (passkey or password) | Body `{name, kind, platform, app_version, os_version, jwk}`. Creates `client_device` `pending` **and an action `device.add`**; owner's own device on first pairing is auto-approved and recorded `approval: self` |
| `GET /v1/devices/requests/{id}` | the requesting client (polls with a one-time poll code) | `pending` → `active` with a device credential, or `denied` |
| `POST /v1/devices/token` | device | DPoP-signed refresh (RFC 9449 header `DPoP`) → 15-minute access token bound to the key thumbprint |
| `GET /v1/devices` · `GET /v1/devices/{id}` | owner: all; person: own | device records |
| `DELETE /v1/devices/{id}` | owner, or the device's person | Revokes at once (reduces power, so **not** an action, audited): access and refresh die, photo grants and SMB user disabled |
| `POST /v1/photos/sources` | device with `photo_backup` | Creates a source in the person's own dataset (no approval: own data, own quota) and returns a **source-scoped upload token** (`om_` prefix, scope `photos:upload:<src>`, usable on nothing else) |
| `POST /v1/photos/sources/{id}/receipts` | device or source token | Body `{keys: [{key, size, sha256?}]}` → `{on_box: [...], in_verified_backup: [...], missing: [...]}` |
| `PUT /v1/photos/sources/{id}/objects/{key}` | source token | Upload. `Content-Digest: sha-256=:…:` (RFC 9530) **required**; resumable per the IETF "Resumable Uploads for HTTP" draft (`Upload-Offset`, `Upload-Complete`); receipt only after fsync and digest match; 409 `conflict` if the key exists with different bytes (keep both, never overwrite) |
| `PATCH /v1/photos/sources/{id}` | device's person | pause, resume, scope, cellular |
| `DELETE /v1/photos/sources/{id}` | device's person or owner | Stops backup. **Files stay.** Deleting the files is the action `photos.source.delete_data` (risk high, owner approval, plan lists file count and size) |
| `GET /v1/shares` | person | shares this person may mount: `[{id, name, smb_path, access: "read|write"}]` |
| `POST /v1/shares/credential` | device with `shares` | Creates or rotates the device's SMB user; returns the password **once** (desktop keeps it in the OS keychain) |
| `GET /v1/events?topics=alerts,actions,devices` | device | Server-sent events for the tray and the open phone app (topic names follow the NOTIFICATIONS spec) |

**Errors:** contract set, plus `device_pending`, `device_revoked`, `key_mismatch` (DPoP proof does not match the bound key), `quota_exceeded`.
**Compatibility:** each client reads `/openapi.json` (MOBILE §5) and `min_client`; the api-compat workflow (DEV-SDK) fails a PR that removes a field a shipped client uses, listed in `sdk/clientkit/testdata/compat/`.

**NATS** (grammar of the OneMind fabric spec, no new pattern): device state changes publish on the gateway's existing event subjects owned by NOTIFICATIONS; no client connects to NATS directly.

### 4.5 CLI and MCP

```console
$ onemind devices list
ID        PERSON   KIND     PLATFORM  KEY             STATE    LAST SEEN
dev_7k2m  ana      desktop  macos     secure_enclave  active   2 min ago
dev_c91q  ben      phone    android   strongbox       pending  –
$ onemind devices approve dev_c91q        # same as approving action device.add (passkey step-up)
$ onemind devices revoke dev_7k2m
$ onemind photos sources --person ana
SOURCE    DEVICE    ON BOX          IN VERIFIED BACKUP   LAST UPLOAD
src_31fa  dev_44ab  41102 / 41230   40877                09:12
$ onemind shares list
```

MCP tools (added to the catalog in one PR with the MCP owner, §5 CLIENT-13):

| Tool | Returns | Notes |
|---|---|---|
| `list_devices` | id, person, kind, platform, state, last_seen | no key material, no SMB users |
| `photo_backup_status` | per source counts and last upload | lets an agent say "Ben's phone has not backed up for 9 days" |
| `request_action` (existing) | unchanged: **no** device, share or photo action types are added for agents in v1 | a prompt-injected agent has no path to add a device, mount a share or delete photos |

### 4.6 Screens

| Surface | Screen | Content |
|---|---|---|
| Desktop tray (popup) | **Boxes** | Found and saved boxes, live status (honesty rule: "not live, from 3 min ago"), Open dashboard |
| | **Pair** | Discovered box → shows its CA fingerprint as 6 words and a 6-digit check code; "Ask the owner" sends `device.add`; waits with a live state; owner approves on phone/dashboard |
| | **Approvals** | Pending actions with exact params, requester (person or agent), expiry; Approve uses the platform passkey (Touch ID / Windows Hello) via the system WebAuthn API (UNVERIFIED in Tauri on all three OSes, spike DESK-S2; fallback opens the dashboard card in the browser) |
| | **Files** | Shares with Connect/Disconnect; mounted path; "Show in Finder/Explorer" |
| | **Backup** | This computer's folders, last verified restore, Back up now |
| | **Settings** | Start at login, updates channel, devices on this box (own), sign out (revokes this device) |
| Phone (Expo) | **Photos backup** (new tab section in Settings → Backup) | Toggle, scope, cellular, counts "on box / in verified backup", what is blocking (no Wi-Fi, box unreachable, permission lost) |
| | **Free up space** | Offered only for items with `in_verified_backup`; opens the system delete sheet (iOS/Android confirm themselves) |
| Dashboard | **Settings → Devices** | Every person's devices, key storage badge, pending device requests as approval cards, Revoke |

All copy is written fresh for OneMind (`docs/design/` voice), never taken from umbrelOS.

### 4.7 Components and licences (versions read from the registries on 2026-11-12; pin a version at least two weeks old when each epic starts and record it in `os/versions.lock.yaml` or the package lock)

| Component | Version seen | Licence | Ships how |
|---|---|---|---|
| Tauri (`tauri`, `@tauri-apps/api`, `@tauri-apps/cli`) | 2.12.5 / 2.12.4 / 2.12.4 | Apache-2.0 OR MIT | linked into the desktop app |
| `tauri-plugin-updater` | 2.14.1 | Apache-2.0 OR MIT | linked |
| `tauri-plugin-autostart`, `-single-instance`, `-deep-link`, `-notification` | 2.7.0, 2.5.5, 2.6.3, 2.8.1 | Apache-2.0 OR MIT | linked |
| `rustls` | 0.23.46 | Apache-2.0 OR ISC OR MIT | linked (pinned-CA verifier is our code) |
| `reqwest` | 0.13.5 | MIT OR Apache-2.0 | linked |
| `mdns-sd` | 0.21.7 (newer than two weeks on the read date; pin the previous release) | Apache-2.0 OR MIT | linked |
| `keyring` | 4.2.0 | MIT OR Apache-2.0 | linked (SMB password, refresh token) |
| `security-framework` (macOS Keychain, Secure Enclave keys) | 3.7.0 | MIT OR Apache-2.0 | linked |
| `objc2` (NetFS call) | 0.6.5 | MIT | linked |
| `windows` (WNet, CNG/TPM) | 0.62.2 | MIT OR Apache-2.0 | linked |
| `webpki-roots` | not used: box trust is the pinned CA only; Mozilla roots (CDLA-Permissive-2.0) only if a public update host needs them, else the OS store | – | – |
| WebView2 Runtime | OS component | Microsoft redistributable terms | separately shipped (Windows 11 has it) |
| WKWebView, WebKitGTK | OS / distro | Apple OS; LGPL-2.1 (dynamically linked system library) | separately shipped |
| restic (laptop folder backup) | pin with BACKUPS | BSD-2-Clause | separate binary, bundled as a sidecar |
| Samba (box SMB server) | Debian package in an app image | GPL-3.0-or-later | **separate app container**, never linked into OneMind code |
| Expo modules: `expo-media-library`, `expo-background-task`, `expo-file-system`, `expo-camera` (QR) | 58.0.14, 58.0.13, 58.0.13, 58.0.14 | MIT | linked into the phone app |
| `@bacons/apple-targets` (adds the iOS extension target from config) | 5.0.0 | MIT | build-time only |
| `uniffi` | **not used** (MPL-2.0); TS and Rust kits share vectors, not generated bindings | – | – |
| Electron | 45.3.1, MIT | rejected (§4.2) | – |

### 4.8 Security

- **Trust:** box CA pinned per instance id, write-once; changing it needs Remove and re-pair, approved by the owner. QR pairing (phone) and fingerprint words + check code (desktop) remove blind first-use trust. Plain HTTP only for `GET /v1/discovery`, which carries no secrets and creates no trust.
- **Keys:** device key non-exportable where hardware allows; `key_storage` is shown in Devices so the owner sees a `software` key (Linux without TPM). Access tokens 15 min, sender-constrained; refresh requires a fresh DPoP proof with a server nonce.
- **Scope:** source tokens upload to one source only; SMB users are per device and see only shares the person may use; agent tokens are refused on all `/v1/devices`, `/v1/photos/sources` write and `/v1/shares` routes.
- **Household:** device requests from a child or guest go to an adult or owner; a child's photo source lands in the child's dataset; nobody can mount another person's private share.
- **Storage safety:** uploads write to a temp file in the same dataset, fsync, digest check, rename; receipts only after that. "Free up space" requires `in_verified_backup` (BACKUPS CORE-BACKUP-7), not just "on box". Stopping backup never deletes files.
- **Lost device:** revoke in Devices or `onemind devices revoke`; takes effect within one token lifetime (≤ 15 min) for in-flight access and immediately for refresh, uploads and SMB (the Samba user is disabled synchronously).
- **Updates:** desktop updates signed twice (OS code signing + Tauri Ed25519 key held in a GitHub environment with a required reviewer, as SECURITY CORE-SEC-8 does for release keys); downgrade refused.
- **Logs:** clients log error kinds and codes, never hosts, share paths or user names (umbrelOS's Windows README states the same goal).

---

## 5. Epics

Stream proposal for [WORKSTREAMS.md](../leap/WORKSTREAMS.md) §2 (a separate small PR adds this row; this doc does not edit WORKSTREAMS):

| Stream | Branches | Owns (paths) |
|---|---|---|
| Clients | `feat/client-devices`, `feat/photo-ingest`, `feat/shares`, `feat/clientkit`, `feat/desktop-client` (exists, empty), `feat/mobile-photos` (exists, empty; works inside `mobile/**` under the Mobile stream's review) | `core/onemind_core/{devices,photo_ingest,shares,discovery}.py`, `sdk/clientkit/**`, `desktop/**`, `apps/samba/**`, `cmd/onemind/cli/{devices,photos,shares}.go`, `.github/workflows/{ci-desktop,desktop-release}.yml`, `mobile/modules/{onemind-pin,photo-backup}/**` |

Hotspots touched only through their owners: `sdk/contracts/poc-v0.md` (CLIENT-0), `core/onemind_core/routes.py` (one line per route module), `ledger.py` (one migration per epic), `cmd/onemind/cli/root.go` (one line per group), `mobile/app.json` (plugins, one at a time), `core/onemind_core/mcp/catalog.py` (MCP owner), `os/**` avahi service file (image stream).

| ID | Title | Size | Owner paths | Depends on | Acceptance |
|---|---|---|---|---|---|
| CLIENT-0 | Contract §12-clients: discovery, devices, photo sources, shares, events topics | S | `sdk/contracts/poc-v0.md` (contract PR only) | CORE-SEC-1, CORE-SEC-2 drafts | Contract PR merged alone; schemas for §4.3 and routes of §4.4; OpenAPI export diff reviewed |
| CLIENT-1 | Discovery: `_onemind._tcp` advert + `GET /v1/discovery` | S | `core/onemind_core/discovery.py`; avahi service file via image stream | CLIENT-0, CORE-SEC-1 | `avahi-browse` shows the service with only `id` and `v` TXT keys; route answers < 50 ms, no auth, no person names (test greps the body); rate limit returns 429 |
| CLIENT-2 | Device registry, `device.add` action, DPoP tokens, revoke | M | `core/onemind_core/devices.py`, ledger migration, `cmd/onemind/cli/devices.go` | CLIENT-0, CORE-SEC-2, CORE-SEC-3 | A device request creates a pending action; agent token gets 403 on every `/v1/devices` route; refresh with a proof from another key returns 401 `key_mismatch`; revoke stops refresh at once and access within 15 min (clock-mocked test); audit has add/approve/revoke |
| CLIENT-3 | Client kit (TS + Rust) and shared vectors | M | `sdk/clientkit/**` | CLIENT-0 | ≥ 30 vectors (QR, discovery, CA mismatch, route race, resource key, receipt diff) pass identically in TS and Rust CI; CA mismatch always ends in "refused", never in a new pin |
| CLIENT-4 | Photo ingest on the box | M | `core/onemind_core/photo_ingest.py`, ledger migration, `cmd/onemind/cli/photos.go` | CLIENT-2, CORE-BACKUP-1 | Upload without `Content-Digest` → 400; wrong digest → 422 and no file; kill the gateway mid-upload, resume from `Upload-Offset` → one file, correct sha256; same key different bytes → both kept; source stop leaves files; `photos.source.delete_data` needs owner approval; files land in the person's dataset on the Retain class |
| CLIENT-5 | Receipts with backup level | S | `photo_ingest.py` | CLIENT-4, CORE-BACKUP-7 | `in_verified_backup` set only after a verified-restore run covers the file; deleting the box copy moves the key back to `missing` |
| CLIENT-6 | Android photo backup | M | `mobile/modules/photo-backup/android/**`, `mobile/src/backup/**` (branch `feat/mobile-photos`) | CLIENT-3, CLIENT-4, CORE-MOBILE-2 | Real phone, 5 000 items: all receipts match server sha256; airplane mode mid-run resumes without duplicates; Wi-Fi-only respected on a metered hotspot; revoke on the box stops uploads within one pass; permission loss shows "paused" |
| CLIENT-7 | iOS photo backup: app passes, then PhotoKit extension spike (HTTPS with user-trusted name-constrained CA) | L | `mobile/modules/photo-backup/ios/**`, iOS extension target via `@bacons/apple-targets` | CLIENT-6, NETWORKING NT-14 | App passes: same tests as CLIENT-6 on iPhone. Spike result recorded: if PhotoKit uploads succeed over HTTPS to the box with the profile-trusted CA, ship the extension; if not, document and keep app-run passes plus overnight runs; never plain HTTP |
| CLIENT-8 | Desktop shell v1 (Tauri): tray, discovery, pair, status, open in browser | M | `desktop/**`, `.github/workflows/ci-desktop.yml` | CLIENT-2, CLIENT-3 | macOS 14+, Windows 11, Ubuntu 24.04 builds in CI; pairing ends `active` only after owner approval; wrong CA at the same address → refused with a clear message; installer < 25 MB; idle RAM < 120 MB (measured) |
| CLIENT-9 | Shares: Samba app + per-device SMB users + desktop mounts | M | `apps/samba/**`, `core/onemind_core/shares.py`, `desktop/src-tauri/src/mount/**` | CLIENT-8, app pipeline gate | Mount on macOS (NetFS), Windows (drive letter chosen by Windows), Linux (gio); revoke device → next SMB operation fails; a child device cannot list the owner's private share; mounts re-adopted after relaunch only after identity proof |
| CLIENT-10 | Desktop approvals, alerts and events | S | `desktop/src/approvals/**`, `desktop/src-tauri/src/events.rs` | CLIENT-8, CORE-NOTIFY-1, CORE-SEC-2 | New pending action shows in < 5 s via `/v1/events`; approve with platform passkey works or falls back to the browser card (spike DESK-S2 recorded); notification click opens the card, never approves |
| CLIENT-11 | Laptop folder backup (restic to the box) | M | `desktop/src-tauri/src/backup/**` | CLIENT-8, CORE-BACKUP-4 | Back up 10 GB of mixed files; restore a deleted file from the tray; verified-restore check passes; backup pauses on battery below 20 % and on metered networks |
| CLIENT-12 | Desktop release: signing, notarization, MSIX/DMG/AppImage, signed updater | S | `.github/workflows/desktop-release.yml`, `desktop/release/**` | CLIENT-8; founder: Apple Developer ID, Windows signing account | Notarized DMG staples; MSIX installs on a clean Windows 11 VM; tampered update rejected; downgrade rejected; keys only in a GitHub environment |
| CLIENT-13 | MCP read tools `list_devices`, `photo_backup_status` | S | `core/onemind_core/mcp/**` (one PR with the MCP owner) | CLIENT-2, CLIENT-4, DEV-MCP | Tools return no key material or SMB user names (schema test); agents still get 403 on all device/share writes |
| CLIENT-14 | Dashboard Devices page | S | `dashboard/src/pages/SettingsDevices.tsx` (Dashboard stream review; route line in `App.tsx` hotspot) | CLIENT-2 | Pending device appears as an approval card; key-storage badge shown; revoke works and is audited |
| CLIENT-15 | Later: macOS File Provider and Windows Cloud Files (on-demand files instead of SMB) | L | `desktop/native/{macos-fileprovider,windows-cloudfiles}/**` | CLIENT-9, founder go | Decision record first: only if SMB proves unreliable over the mesh in the field (measured) |

**Spikes before the dependent epic starts:** DESK-S1 (pinned trust in Tauri web views, decides whether box pages ever render in-app), DESK-S2 (platform passkeys from a Tauri app on macOS, Windows, Linux), NT-14 (name constraints honoured on iOS/Android, shared with NETWORKING), PhotoKit-over-HTTPS (CLIENT-7).

**Founder decisions this adds:** (1) Tauri as the desktop stack (§4.2). (2) Samba as a separately shipped app for shares, versus a WebDAV server of our own (smaller, but Finder/Explorer WebDAV clients are weaker). (3) Lifting "photo backup" from MOBILE's v1 non-goals into v1, given the founder focus on photos and storage safety.
