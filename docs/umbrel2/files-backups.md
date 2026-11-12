<!-- SPDX-License-Identifier: Apache-2.0 -->
# Files, Rewind, cloud import and backups: umbrelOS study and OneMind plan

**Date:** 2026-11-12 · **Status:** study and design proposal, not binding. Contract changes it proposes go through the contract owner (WORKSTREAMS §4).
**Studied:** umbrelOS `2.1.0-beta.1`, commit `6f357e18d0a4`. All umbrel paths below are relative to that repository root and line numbers are at that commit.
**Builds on:** [BACKUPS.md](../architecture/BACKUPS.md) (restic design), [CONTRACT-12-DRAFT.md](../architecture/CONTRACT-12-DRAFT.md) §12.5, [leap/core/BACKUPS.md](../leap/core/BACKUPS.md) (CORE-BACKUP-1…8), [WORKSTREAMS.md](../leap/WORKSTREAMS.md), [core-alignment.md](../strategy/core-alignment.md) §4.6, and the umbrel parity audit on `feat/uileap` (`docs/strategy/umbrel-parity.md` §3.5, gap PU-16).

> **Legal rule for this page and everything built from it.** umbrelOS is licensed PolyForm Noncommercial 1.0.0 (checked at the commit above). OneMind is sold commercially. This page **describes** umbrel's architecture and flows and cites file paths so a reader can check them. It contains no umbrel code, strings, UI text, icons or assets, and nothing below is a line-by-line paraphrase. Every OneMind component named in §4 is our own code or a separately shipped program with a permissive or separately distributed licence, recorded with its version in `os/versions.lock.yaml` when adopted.

> **In plain words.** umbrelOS has a real file manager: your files, your apps' folders, USB drives, NAS shares and cloud drives (Google Drive, Dropbox, OneDrive, iCloud, WebDAV) all appear in one place. Every hour it copies the whole box into an encrypted backup on a USB disk or a network share, and a "Rewind" mode in the file manager lets you scroll back in time and copy old files back. To recover a dead box you plug the backup into a new one during setup and it restores everything, then reboots.
> OneMind has the backup design (restic) but no file manager, no NAS mounts and no cloud import yet. This page plans them so that OneMind matches umbrel on the everyday features and beats it where it matters: verified backups, an off-site copy, restores you can undo, per-person spaces for the whole household, and agents that can ask for a folder but never take one.

---

## 1. How umbrelOS does it

### 1.1 Architecture in one picture

```
             Browser UI (React)                          Phones / PCs
  packages/ui/src/features/files, features/backups,     SMB (Samba server), mobile photo backup
  routes/onboarding/restore.tsx, routes/settings/...
                     │ tRPC over HTTP/WebSocket                │
                     ▼                                         ▼
  umbreld (Node/TypeScript, one daemon, root)  packages/umbreld/source/modules/
   ├── files/      virtual filesystem over base folders, ops, trash, uploads, thumbnails,
   │               SQLite file index + FTS, watcher, Samba export, member shares,
   │               external drives, network mounts (CIFS), cloud sync (rclone)
   ├── backups/    Kopia repositories on /External or /Network, hourly snapshot of the
   │               whole data directory, mount snapshots for browsing and restore
   ├── migration/  copy an older umbrel install from a USB SSD (Umbrel Home / Pro only)
   ├── startup-migrations/  swaps an "import" directory into place on boot
   └── apps/       folder-access slots at install, move an app's data root to another drive
                     │
                     ▼
   One data directory on disk: home/, app-data/, trash/, external/, network/, backups/, machines/ …
```

Everything runs inside one root daemon. Separate programs are spawned for the heavy parts: `kopia` (backups), `rclone` (cloud), `mount -t cifs` (NAS), Samba (`smbd`) for sharing, `ffprobe`/`exiftool`/ImageMagick for metadata and previews, `unar`/zip for archives, `parted`/`mkfs` for formatting.

### 1.2 Files (`packages/umbreld/source/modules/files/`)

| Area | How it works | Key files |
|---|---|---|
| **Virtual paths** | Seven fixed roots (`/Home`, `/Trash`, `/Apps`, `/Machines`, `/External`, `/Backups`, `/Network`) each map to a directory under the data directory. Every API call takes a virtual path; the daemon converts and authorises it before touching disk. Members get their own home and trash under a per-member directory. | `files.ts:186` (root map), `files.ts:328` (member directories) |
| **Operations** | List (paged), copy, move, rename, trash, restore from trash, delete, archive/unarchive, favourites, recents, view preferences; long operations report progress over an event bus. Copies use reflinks when the filesystem supports them. | `files.ts`, `routes.ts`, `archive.ts`, `favorites.ts`, `recents.ts` |
| **Uploads** | Streamed HTTP body written to a hidden temporary file in the target folder, renamed into place on completion; refuses early when the disk is full. Resume is **not** implemented (an explicit TODO). | `api.ts:338`, `api.ts:351` |
| **Previews** | WebP thumbnails at three sizes, cached by content hash; enrichment reads media metadata with `ffprobe` and `exiftool` and renders some formats with ImageMagick. Documents can be viewed (and in 2.1 edited) in the browser. | `thumbnails.ts`, `thumbnail-support.ts:7`, `file-index-enrichment.ts` |
| **Index and search** | A SQLite (better-sqlite3) index with an FTS5 table over names, filled by worker processes and kept fresh by an inotify watcher (with Watchman). Search is fuzzy over names, with a match threshold. | `file-index-engine.ts`, `file-index/queries.ts:142`, `watcher.ts`, `watchman.ts` |
| **Sharing on the LAN** | Samba server; the owner exports folders; members get Samba users created with `useradd`. | `samba.ts` |
| **Members** | Owner can share a path (in `/Home`, `/Apps`, `/External`, `/Network`) with all members or a list; shares are dropped automatically when the folder is deleted or renamed. | `member-shares.ts:22`, `app-directory-monitor.ts` |
| **External drives** | `lsblk` discovery; auto-mount of common filesystems; format to ext4 or exFAT (`parted` + `mkfs`); unmount first blocks any app using the drive. | `external-storage.ts:450` |
| **Network shares (NAS)** | SMB/CIFS only: server discovery by mDNS (`avahi-browse _smb._tcp`) and share listing by `smbclient`; mounted with a 0600 temporary credentials file. Share username and password are kept in umbreld's settings store. A helper checks whether a server is another Umbrel by calling its version endpoint. | `network-storage.ts:154`, `:294`, `:335` |
| **Cloud drives** | rclone, one-way **cloud → box**: modes "one time" and "automatic" (every 30 minutes). Providers: Google Drive, Dropbox, OneDrive (OAuth), WebDAV incl. Nextcloud/ownCloud, iCloud Drive (Apple ID with two-factor). rclone runs as a long-lived `rcd` on a unix socket plus per-sync `rclone sync` with per-provider flags; OS junk files are filtered so they are not deleted remotely. OAuth goes through an **Umbrel-operated OAuth proxy** with PKCE. Each account has its own rclone config. | `cloud-types.ts`, `cloud.ts:53`, `cloud-rclone.ts:754`, `:820`, `cloud-auth.ts:24`, `:406` |
| **Apps on any drive / folder access** | An app manifest declares folder-access slots (id, name, container mounts, default). At install the user picks a source folder for each (any Home, external or network folder). Separately, "move data root" moves an app's whole data folder to an external drive (ext4 only), stopping and restarting dependent apps. | `apps/schema.ts:41`, `apps/app.ts:390-420`, `apps/app.ts:931` |
| **Rewind** | A mode of the file manager (see §1.4). | `files.ts:1122`, `cloud.ts:1052`, UI `packages/ui/src/features/files/components/rewind/` |

### 1.3 Backups (`packages/umbreld/source/modules/backups/backups.ts`)

| Aspect | umbrel's choice | Where |
|---|---|---|
| Engine | **Kopia** (filesystem repository), one kopia process at a time through a queue | `backups.ts` (`kopia()` wrapper) |
| What | **The whole data directory as one snapshot**: homes, app data, VMs, settings. Not per app. | `backups.ts:680` |
| Consistency | The umbreld SQLite database is copied with an online backup and checked with `quick_check` before the snapshot; running VMs are pivoted onto overlays during the snapshot. **Apps are not paused and have no hooks**: app data is crash-consistent. | `backups.ts:552`, `machines` module |
| Exclusions | Fixed list (app-store caches, thumbnails, file index, kopia's own cache, live DB files, VM install images), per-app ignore paths from the app manifest, user exclusions (only inside `/Home`), mounted network shares. | `backups.ts:772` |
| Schedule | Every hour, loop in the daemon; notification when a destination has had no success for 24 h. | `backups.ts:156`, `:190` |
| Retention | Latest 10, hourly 24, daily 7, weekly 4, monthly 12, yearly 0; zstd-fastest compression; never cross filesystems; one parallel file read (throttling). | `backups.ts:624` |
| Encryption | Kopia's own encryption. The user's password is reduced to the first 16 hex characters of its SHA-256 (so 64 bits) before kopia sees it; kopia applies scrypt. That derived value is stored in umbreld's settings store, which is enough to open the repository. | `backups.ts:292` |
| Destinations | Only a folder under `/External` (USB) or `/Network` (SMB share, including another Umbrel's share). **No cloud or S3 destination.** The repository id is derived from the path, not the disk's identity (an explicit TODO). | `backups.ts:275` |
| Browse | `kopia mount` (FUSE) of a snapshot, then bind-mounts its `home` and `app-data` into `/Backups/<snapshot>/Home` and `/Apps`. | `backups.ts:937` |
| Restore (whole box) | Requires free space = backup size + 5 GB. Mount the snapshot, copy it all with rsync into a temporary folder, promote the database copy, write a "first start after restore" marker (cloud syncs start paused so they do not overwrite restored files), move it to `import/`, **reboot**; on boot the import folder replaces the data directory. No per-app restore, no undo. | `backups.ts:372`, `startup-migrations/index.ts:90` |
| Restore at setup | The same restore is reachable before any user exists: connect a USB or network repository, type the password, pick a snapshot. Those routes are open while no user exists. | `backups/routes.ts:80`, `:85`; `files/routes.ts:433`, `:478`; UI `packages/ui/src/routes/onboarding/restore.tsx` |
| Verification | None beyond kopia's own checks. No test restore. | – |

### 1.4 Rewind (user-visible flow)

1. In Files, the user opens Rewind on a folder. A pre-flight dialog picks the backup repository (`prerewind-dialog.tsx`).
2. A timeline bar and a snapshot carousel show the snapshots from oldest to "now" (`timeline-bar.tsx`, `snapshot-carousel.tsx`, hook `features/files/hooks/use-rewind.ts`).
3. Moving to a point mounts that snapshot (§1.3 "Browse") and shows the same folder as it was.
4. The user selects items and restores them. The daemon copies them from `/Backups/<snapshot>/Home|Apps/...` back to the chosen folder with a collision rule. If a cloud sync mirrors that folder, the user must confirm, and the restore is fenced so a running sync cannot interleave (`files.ts:1122`, `cloud.ts:1052`).
5. Progress shows in a dialog (`restore-progress-dialog.tsx`).

So Rewind is a time-travel view over hourly whole-box snapshots, restoring by copy. It does not snapshot the files it overwrites, so a mistaken Rewind restore is undone only by the next hourly backup.

### 1.5 Migration (`packages/umbreld/source/modules/migration/migration.ts`)

Only on Umbrel Home / Pro hardware: find an external USB drive holding an older umbrel install (e.g. from a Raspberry Pi), refuse downgrades, check free space, `rsync` it into a temporary folder, move it to `import/`, reboot (`migration.ts:131`, `:190`). Settings → Migration Assistant in the UI. Separate from backups.

### 1.6 Backup set-up flow (UI, `packages/ui/src/features/backups/`)

Wizard: destination (USB or network) → folder → exclusions (first repository only) → encryption password → review (`components/setup-wizard.tsx`). Progress shows in a floating island; Settings lists repositories, size, last backup and exclusions; restore has its own wizard (`components/restore-wizard.tsx`).

### 1.7 What to learn and what to avoid

**Learn:** one place for every kind of storage; Rewind as a mode of the file manager rather than a separate screen; restore offered during setup; pausing cloud syncs after a restore; per-provider rclone tuning; fencing restores against syncs; shares that disappear with their folder.
**Avoid:** whole-box snapshots with no app consistency hooks; no verified restore; no off-site or cloud destination; repository identified by path; a short derived password stored on the box; restore by reboot with no undo; setup-mode routes that accept network credentials from anyone on the LAN while no user exists; a vendor-hosted OAuth proxy in the login path; uploads that cannot resume.

---

## 2. What OneMind has today

| Area | State on `main` (2026-11-12) | Path |
|---|---|---|
| Backup design | Full design: restic v0.19.1, units `system`/`k3s`/`nats`/`app:<id>`/`node:<id>`, hourly + GFS retention, USB / OneMind node (append-only) / S3 targets, three keys + emergency kit, pre-update and pre-restore snapshots, restore file/app/box, verified-restore badge. **Not built.** | `docs/architecture/BACKUPS.md`, `docs/leap/core/BACKUPS.md` (CORE-BACKUP-1…8) |
| Backup API | Draft §12.5: status, targets, runs, snapshots, snapshot tree and file download, verifications, onboarding restore candidates; writes are actions. | `docs/architecture/CONTRACT-12-DRAFT.md` §12.5 |
| restic in code | Only the updater's pre-update snapshot of `/data` (config keys `restic_binary`, `restic_repository`, `restic_password_file`). | `internal/update/config.go`, `internal/update/engine.go` |
| Storage | Disk size and free space in the heartbeat; `/data` is ext4 and not yet encrypted (LUKS2 planned, H-11). No disk inventory, mounts, formatting. | `internal/detect/disk_unix.go`, `docs/security/THREAT-MODEL.md` |
| Files | **None.** IA lists Files as "not in v0 navigation"; the parity audit's PU-16 proposes a Market app instead of a core file manager. | `docs/design/IA.md`, `feat/uileap:docs/strategy/umbrel-parity.md` §3.5 |
| NAS mounts, SMB server, WebDAV | None. | – |
| Cloud import | None. No rclone pin. | – |
| Household accounts | Owner + agent principals with static tokens; passkeys and household identity planned (SEC-P1, Kanidm later). | `core/onemind_core/auth.py`, `docs/leap/core/SECURITY.md` |
| Agents | MCP endpoint with read tools and `request_action`; never approve (§11.3). | `sdk/contracts/poc-v0.md` §11, `feat/gateway-agent-mcp` |
| Branches already cut, empty | `feat/onemindd-storage`, `feat/onemindd-backup`, `feat/mobile-photos`, `feat/desktop-client` (no commits beyond `main`). | worktrees of the same names |

---

## 3. Match and beat

| Topic | umbrelOS | OneMind will match | OneMind will beat |
|---|---|---|---|
| File manager | Full, in the core | Browse, upload, download, trash, search, previews, favourites, recents, archives | **Resumable uploads** (tus) from browser, phone and desktop; per-person spaces by default; every share, grant and restore in the audit log |
| Household | Owner + members, owner shares paths | Per-person Home, a household Shared folder, shares | Shares are **actions** (approved, audited, expiring); child roles when household identity lands; quotas per person |
| Previews | WebP thumbnails, media metadata | Same sizes class (small, medium, large) | Thumbnailers run **sandboxed with no network**, because image and video parsers are the riskiest code on the box |
| NAS in | SMB only | SMB mounts with discovery | **NFS too**; credentials in the secret store (sealed input), never in a settings file |
| LAN share out | Samba | Samba per-person users | WebDAV endpoint for clients over the box CA; SMB signing required by default |
| Cloud import | rclone, Google / Dropbox / OneDrive / WebDAV / iCloud, cloud → box, vendor OAuth proxy | Same providers (iCloud marked experimental), one-time and scheduled | **No vendor proxy in the token path**: the OneMind phone or desktop app completes OAuth and hands the code to the box; tokens live only in the box's secret store. Upstream deletions go to OneMind **Trash** instead of being lost. Cloud folders can also be a **backup target** (encrypted by restic before upload) |
| Apps on any drive | Folder slots at install; move data root to external ext4 | Folder grants at install from the manifest | Grants are scoped (read-only or read-write), shown on the approval card, revocable, and **agents use the same mechanism**: an agent asks for a folder, the owner approves |
| Backup engine | Kopia, whole box, no app hooks | restic, hourly, GFS | Per-unit snapshots (system, k3s, each app, each person's files) with **app hooks** for consistent databases |
| Destinations | USB, SMB share, another Umbrel's share | USB, another OneMind box | **Append-only** box target (a stolen or compromised box cannot delete its history), **S3 and cloud drives** for an off-site copy, "1 copy only" warning until there are two |
| Keys | Password, reduced to 64 bits, stored on the box | Encrypted repository | 256-bit random keys, three per repository, owner key only in the **emergency kit** that setup cannot skip |
| Verification | None | – | **Verified-restore badge**: weekly scratch restore of each app with fresh health probes; never green without it |
| Rewind | Timeline over hourly snapshots, copy back | Timeline in Files over restore points | Restores are approved actions with a **pre-restore snapshot, so every Rewind restore can be undone**; no FUSE mount (restic `ls`/`dump`), so it works without extra kernel modules and never leaves stale mounts |
| Whole-box restore | During setup, by reboot, no undo, routes open while no user exists | During onboarding | **Portable** restore across hardware and CPU architecture (revisions + images by digest), **fencing** so the old box stops writing, setup session bound to the console/QR pairing instead of "anyone on the LAN" |
| Migration | Older umbrel on USB SSD, Umbrel hardware only | Copy from another box | **Import from any NAS, old server or another self-hosted OS over SMB/NFS/WebDAV** with rclone, as a resumable job with a dry-run plan |
| Agents | MCP exists in 2.1 (separate study) | – | File access only through approved, scoped grants; agents can search granted folders and request restores, never read backups or approve |

---

## 4. OneMind design

### 4.1 Where things run

```
 Dashboard "Files" page / mobile / desktop / WebDAV clients
              │ HTTPS (box CA)                    │ bytes (signed, short-lived URL)
              ▼                                   ▼
 Gateway (core/, Python)                     onemindd file server (internal/files, Go)
  authz, roots, shares, grants,                confined file ops on its node, tus uploads,
  actions (restore, import, shares),           downloads, thumbnails, index, trash
  audit, file tokens, cloud-import records          │
              │ NATS jobs (§12.4)                   ├── internal/storage: disks, USB, NFS/SMB mounts
              └────────────────────────────────────►├── internal/backup:  restic units incl. home:<person>
                                                    └── internal/cloudimport: rclone runner
```

- **The gateway decides, the node does.** The gateway authorises every request and issues a file token (`ftk_…`, 5 minutes, bound to principal, root, path prefix and verb). The node's file server checks the token and serves bytes directly, so large transfers never pass through the Python gateway.
- **Data plane vs control plane.** A person reading or changing files inside a space they already hold is data-plane and is not an action (an app writing its own volume is not an action either). Everything that **changes who can reach what, or replaces data from elsewhere** is an action: shares, folder grants, mounts, formats, cloud accounts and imports, restores, emptying trash past retention. The owner can create and approve their own in one step (`approve: true`, §12.2). This needs a contract decision (D-F1, §6).
- **Files UI:** a dashboard page (`dashboard/src/pages/Files.tsx`) built on the design system, not a Market app. This reverses PU-16 because Rewind, restores, grants and imports are core actions and the founder focus names storage, backups and photos. Decision D-F2 (§6).

### 4.2 Components and licences

Pin each in `os/versions.lock.yaml` (hotspot, add-only, one commit per stream) with version, licence and sha256 when the epic that needs it starts. Versions marked "at adoption" must be the then-current stable release and are not chosen here.

| Component | Use | Licence | Version | How shipped |
|---|---|---|---|---|
| restic | backups, Rewind browse (`ls --json`, `dump`, `restore`) | BSD-2-Clause | 0.19.1 (already chosen, BACKUPS.md) | binary in image |
| rest-server | append-only box target | BSD-2-Clause | at adoption | binary in image |
| rclone | cloud import, NAS migration, restic `rclone:` backend | MIT | at adoption | binary in image, run as a separate process |
| tusd (Go library `github.com/tus/tusd/v2`) | resumable uploads | MIT | at adoption | linked into `onemindd` |
| `golang.org/x/net/webdav` | WebDAV endpoint | BSD-3-Clause | at adoption | linked |
| `golang.org/x/sys/unix` (`openat2`, `RESOLVE_BENEATH`) | path confinement | BSD-3-Clause | per `go.mod` | linked |
| fsnotify | index updates | BSD-3-Clause | at adoption | linked |
| SQLite with FTS5 (via `modernc.org/sqlite`, BSD-3-Clause, pure Go) | per-node file index | SQLite: public domain | at adoption | linked |
| libvips `vipsthumbnail` | image thumbnails | LGPL-2.1-or-later | at adoption | separate binary, sandboxed |
| FFmpeg (LGPL build, no `--enable-gpl`/`nonfree`) | video posters, media probe | LGPL-2.1-or-later | at adoption | separate binary, sandboxed |
| poppler `pdftoppm` | PDF first page | GPL-2.0-or-later | at adoption | separate binary, executed only (aggregation); image source offer covers it |
| Samba `smbd` | SMB share out | GPL-3.0-or-later | distro package at adoption | separate service in the image |
| cifs-utils, nfs-common | NAS mounts | GPL-3.0 / GPL-2.0 | distro package | separate binaries |

Rules: nothing GPL or AGPL is linked into OneMind code; GPL programs are separate executables shipped in the image with the source offer the image stream already maintains. ImageMagick is not used (large parser surface; vips covers images). MuPDF is not used (AGPL).

### 4.3 Roots and data model

**Roots** (a path is always `<root>:/<relative path>`; ids, not host paths, so a renamed or re-plugged disk keeps its identity, fixing umbrel's path-derived id):

| Root | Contents | Default access |
|---|---|---|
| `home:<person_id>` | a person's files (`Photos/` is where phone backup lands) | that person |
| `shared` | household shared folder | every person, read-write |
| `app:<app_id>/<volume>` | an app's `onemind-local` volume | owner, read-only (write needs an action, because writing under a running app can corrupt it) |
| `usb:<fs_uuid>` | an external disk | owner; shareable |
| `net:<mount_id>` | an SMB or NFS mount | owner; shareable |
| `rewind:<snapshot_id>` | a backup snapshot, read-only | owner only, audited (BACKUPS.md §11) |
| `trash:<person_id>` | that person's trash, 30-day default | that person |

On disk (box layout, already used by BACKUPS.md): `/data/onemind/files/home/<person_id>`, `/data/onemind/files/shared`, mounts under `/run/onemind/mnt/<kind>/<id>`.

**Ledger tables** (one migration file in `core/onemind_core/ledger.py`, numbered at merge):

```
storage_devices(id, node_id, fs_uuid, label, model, size_bytes, fs_type, kind[internal|usb],
                role[data|files|backup|none], state[attached|mounted|missing], smart_json, seen_at)
network_mounts(id, node_id, proto[smb|nfs], host, share, secret_ref, options_json,
               state[mounted|failing|disabled], last_ok_at)
file_shares(id, root, path, grantee_kind[person|household|link], grantee_id, access[r|rw],
            via_json[web,smb,webdav], expires_at, action_id, created_at, revoked_at)
folder_grants(id, subject_kind[app|agent], subject_id, slot, root, path, access[r|rw],
              action_id, created_at, revoked_at)
cloud_accounts(id, person_id, provider[gdrive|dropbox|onedrive|webdav|icloud], identity,
               secret_ref, state[ok|reauth|quota], created_at)
cloud_imports(id, account_id, remote_json, root, path, mode[once|mirror], deletions[trash|keep],
              interval_s, paused_reason, last_ok_at, last_error, action_id)
file_tokens   -- not stored: stateless, signed (HMAC with a per-box key in the custodian dir)
```

The **file index** is per node and outside the ledger: SQLite at `/data/onemind/cache/files-index.db` (`entries(root, path, name, size, mtime, mime, sha256?)`, FTS5 on `name`), rebuildable, never backed up. Thumbnails: `/data/onemind/cache/thumbs/<sha256>-<size>.webp`, never backed up.

**Backup units added to BACKUPS.md §2** (backup stream owns the change):

| Unit | Contents | Consistency |
|---|---|---|
| `home:<person_id>` | that person's Home | plain files; one snapshot per person so Rewind and retention are per person |
| `shared` | household shared folder | plain files |
| `usb:<fs_uuid>` / `net:<mount_id>` | only when the owner opts a mounted folder in | plain files; skipped with a warning when absent |

Tags as §12.5 plus `person=<id>` or `root=<root>`. Trash is excluded (configurable). Owner path exclusions (`backup.exclude`) apply to `home:` and `shared` only, like umbrel's Home-only rule.

### 4.4 API (contract §12 style; proposed as one contract PR, "12-files")

Lists use `?limit=&cursor=` → `{items, next_cursor}`; ids are prefixed ULIDs (`shr_`, `grt_`, `mnt_`, `dev_`, `cla_`, `imp_`); times RFC 3339 UTC; errors per §12.1.

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/files/roots` | person, agent (granted only) | `[{root, name, kind, node_id, free_bytes?, writable}]` |
| `GET /v1/files/list?root=&path=` | person; agent within a grant | `{items: [{name, type, size, mtime, mime, thumb?}], next_cursor}` |
| `GET /v1/files/stat?root=&path=` | same | one entry plus `versions_available: bool` |
| `GET /v1/files/search?q=&root=` | same | name search over the index (FTS5), scoped to what the principal can see |
| `POST /v1/files/tokens` | person; agent read-only within a grant | `{url, expires_at}` for download, upload (tus endpoint) or thumbnail on the node holding the data |
| `POST /v1/files/ops` | person within own spaces | `{op: mkdir|move|copy|rename|trash|restore_trash, …}` → `{op_id}`; progress on `GET /v1/stream` as `onemind.files.op` events. Data-plane (§4.1) |
| `GET /v1/files/rewind?root=&path=` | owner; a person for their own `home:` | restore points that contain this path: `[{snapshot_id, run_id, taken_at, size, verified}]` |
| `GET /v1/files/rewind/{snapshot_id}/list?path=` | same | listing inside a snapshot (restic `ls --json`), audited |
| `GET /v1/storage/devices`, `/v1/storage/mounts` | owner | §4.3 rows, no secrets |
| `GET /v1/files/shares`, `/v1/files/grants` | owner; a person sees their own | rows |
| `GET /v1/cloud/accounts`, `/v1/cloud/imports` | owner; a person sees their own | rows plus live status |
| `POST /v1/cloud/oauth/start` | person | `{provider}` → `{authorize_url, session}`; PKCE verifier kept on the box (§4.6) |
| `POST /v1/cloud/oauth/complete` | person | `{session, code}` → stores the token, returns `cla_…` |

**Action types** (added to the §12.2 registry; O owner, P person for their own spaces, A agent requests only):

| Type | Who may request | Risk | Policy may approve | Notes |
|---|---|---|---|---|
| `files.restore` `{items:[{snapshot_id, path, to_root, to_path, collision: rename|replace}]}` | O, P, A | medium | yes | takes a `reason=pre-restore` snapshot of every path it would replace first; plan lists them |
| `files.share.create` / `.revoke` | O, P (own spaces) | low / low | yes | `via` smb/webdav/web; `link` shares need `expires_at` |
| `files.grant.create` / `.revoke` | O, A (for itself) | medium (rw) / low (r) | rw: never | plan names the subject, folder and access |
| `files.trash.empty` | O, P | medium | no | |
| `storage.mount.create` / `.remove` | O | low | yes | credentials as sealed input (§12.1) |
| `storage.device.format` | O | critical | never | plan shows model, serial, size, current mounts and apps using it |
| `storage.device.role` | O | medium | yes | `files`, `backup`, `none` |
| `cloud.import.create` / `.update` / `.remove` | O, P, A | low | yes | |
| `cloud.account.remove` | O, P | low | yes | deletes the token from the secret store |
| `files.migrate` `{source: {kind: smb|nfs|webdav|rclone_remote, …}, to_root, to_path, dry_run}` | O | medium | no | resumable job; plan comes from a dry run |

**MCP tools** (agent, extending §12.12; still no approve tool): `files_list`, `files_search`, `files_read` (returns a token URL, text files ≤ 1 MiB inline), all limited to the agent's `folder_grants`; `files_request_access` (creates `files.grant.create`); `files_request_restore` (creates `files.restore`, only for paths inside its grants); `storage_status`. **Never**: browsing `rewind:` roots, reading backups, mounts or cloud tokens.

**CLI** (`cmd/onemind/cli/files.go`, `storage.go`, `cloud.go`): `onemind files ls|get|put|search|share|grant`, `onemind files rewind <root:path> [--at <time>] [--restore]`, `onemind storage devices|mount|format`, `onemind cloud accounts|import add|list|run|pause`, `onemind migrate files <source>` (joins the existing `migrate` group). Every write verb creates the same action as the dashboard; `--json` prints the API response.

**Manifest** (`spec.folders`, ships with the contract PR in `sdk/schema/onemind.app.schema.json`):
```yaml
spec:
  folders:
    - id: media              # stable slot id
      title: Media library   # shown on the approval card (our text, set by the app author)
      mount: {container: server, path: /media}
      access: r               # r | rw
      suggest: shared:/Media  # default proposal, the owner can change it
      required: false
```
The executor turns an approved grant into a hostPath (or bind-backed PV) mount for that container only, through the install sandbox owner (one hook in `executors.py`, WORKSTREAMS §3).

### 4.5 UI screens (design system components, our own copy and icons)

1. **Files** — sidebar: My files, Shared, Shared with me, Drives (USB), Network, Cloud imports, Apps (owner), Trash. List and grid, preview pane, upload queue with resume, search field, breadcrumbs. Phone layout first (16 px gutter, no horizontal scroll).
2. **Rewind** — a time strip at the bottom of Files over restore points (labels by day; each point marked verified or not from the backup badge). Choosing a point shows the folder as it was, read-only; "Restore" opens the action plan: what will be replaced, the pre-restore snapshot, and "Undo" afterwards on the result card.
3. **Storage** (Settings) — disks with health, role (files / backup / none), mount and unmount, format as a critical action with model and serial; network mounts with state.
4. **Cloud import** — choose provider → sign in (hand-off to phone or desktop app, or browser fallback) → choose remote folder → choose destination → once or mirror, deletions to Trash or keep → plan → approve. Status cards with progress and "needs sign-in again".
5. **Folder access** — on the Market install plan: one row per `spec.folders` slot with the proposed folder and access; same sheet for agent requests in Approvals.
6. **Backups** — owned by CORE-BACKUP-8 (`Backups.tsx`); adds `home:` and `shared` units and the exclusions list. Rewind links into it ("Restore points").
7. **Onboarding restore** — owned by ONB-P3 / CORE-BACKUP-6; this page only adds `home:` units to what it restores.

### 4.6 Security

- **Path confinement.** Every node file op resolves with `openat2(…, RESOLVE_BENEATH | RESOLVE_NO_MAGICLINKS)` under the root directory; no string prefix checks. Symlinks out of a root are refused. Fuzz test on path handling.
- **Least privilege.** The file server runs as a dedicated user with group access to file roots, not as root; mount and format go through a small privileged helper in `onemindd` with a fixed argv allow-list.
- **Sandboxed parsers.** Thumbnailers and media probes run under systemd-run transient units (or a seccomp'd child) with no network, read-only input, write-only output dir, memory and time limits.
- **Secrets.** NAS passwords and cloud tokens enter as sealed input (§12.1) and live only in the secret store. rclone gets them through environment variables for one process (`RCLONE_CONFIG_<REMOTE>_…`), never a config file on disk; CIFS gets a credentials file on tmpfs, removed after mount.
- **OAuth without a vendor proxy in the token path.** Primary flow: the OneMind phone or desktop app opens the provider's authorize URL with PKCE (S256, verifier generated and kept by the box), receives the code on its registered redirect (loopback or app link), and sends the code to the box over the authenticated session; the box exchanges it. Fallback for browser-only users: a static OneMind redirect page that only forwards the code to the box in the browser; without the box's verifier the code cannot be exchanged. UNVERIFIED: which redirect types each provider allows for an installed-app client, and whether a provider requires a client secret; check per provider before FILES-9 starts.
- **Cloud mirror cannot destroy local data silently.** Mirror mode uses rclone `--backup-dir` into the person's Trash, so files deleted upstream land in Trash for 30 days, and Rewind still has them.
- **Setup-mode restore.** Restore before an owner exists is accepted only from the onboarding session started at the box (console or pairing QR), not from any LAN client, and expires after 30 minutes.
- **Agents.** Only `folder_grants`; read-only unless the owner approved `rw`; never `rewind:`, backups, mounts or tokens; all agent file reads audited with path and size.
- **SMB out.** SMB3 only, signing required, per-person Samba users mapped from OneMind persons; guest access off.
- **Audit.** Shares, grants, mounts, formats, imports, restores, Rewind listings and every agent file read go to the audit log.
- **Quotas and space.** Uploads, imports and restores check free space first (restores: 2× the restore size, BACKUPS.md §3); per-person quotas optional.

### 4.7 Mapping umbrel features to BACKUPS.md

| umbrel behaviour | BACKUPS.md today | Change proposed here |
|---|---|---|
| Whole data directory, hourly | §2 units, §3 hourly | add `home:<person>` and `shared` units (§4.3) |
| Retention 10 latest / 24 h / 7 d / 4 w / 12 m | §3 GFS 24/7/4/12 | keep ours; add `--keep-last 10` only if Rewind needs denser recent points (measure first) |
| User exclusions in Home | not covered | `backup.exclude` setting for `home:`/`shared` |
| Per-app ignore paths | §12.13 `backup.exclude` | none |
| DB snapshot + `quick_check` | §2 `system` (SQLite online backup) | none |
| VMs pivoted to overlays | not covered (no VMs yet) | later, with PD-23 |
| USB / SMB / other Umbrel | §4 `usb`, `node` (append-only), `s3` | add `cloud` target kind: restic `rclone:` backend to a connected cloud account; SMB folder as a target only through a mount (§4.3) |
| Browse by FUSE mount | §7.1 tree/file endpoints | Rewind uses the same endpoints; no FUSE |
| Rewind restore by copy, no undo | §7.1 `scope: path` | `files.restore` with pre-restore snapshot (undo) |
| Whole-box restore + reboot | §7.3 portable/exact + fencing | none |
| Pause cloud syncs after restore | not covered | after any restore, `cloud_imports` touching restored paths start paused with `paused_reason: restore` |
| Failing for 24 h → notification | badges (§8), alerts | none |
| Migration from old install on USB | `onemind migrate` (DEPLOYMENTS) | `files.migrate` from any SMB/NFS/WebDAV/rclone source |

---

## 5. Epics

Owner paths follow WORKSTREAMS.md. New streams: **Storage** (`feat/onemindd-storage`, already cut) and **Files** (`feat/files-*`). Hotspot edits (contract, schema, `ledger.py`, `App.tsx`, `root.go`, `main.go`, `versions.lock.yaml`, `executors.py`, `mcp/catalog.py`) go in their own small PRs through their owners.

| ID | Title | Size | Owner paths | Acceptance tests | Depends on |
|---|---|---|---|---|---|
| FILES-0 | Contract 12-files: roots, file API, action types, MCP tools, `spec.folders` | S | `sdk/contracts/poc-v0.md`, `sdk/schema/onemind.app.schema.json` (contract owner) | Contract PR merged; schema validates a manifest with `spec.folders` and rejects one with an unknown `access` | C12-A (§12.1–12.2), decisions D-F1, D-F2 |
| STOR-1 | Disk inventory, USB auto-mount by fs UUID, roles, format as critical action, SMART | M | `internal/storage/**`, `core/onemind_core/storage.py`, `cmd/onemind/cli/storage.go` | VM: plug a virtual USB disk → appears with fs UUID; re-plug in another port keeps the same `usb:<uuid>` root; `storage.device.format` refused by policy and needs owner approval; unmount refused while an app grant uses it unless the plan stops the app | FILES-0, FABRIC jobs (F4) |
| STOR-2 | NAS mounts: SMB (discovery by mDNS) and NFS, credentials sealed | M | `internal/storage/netmount/**`, `core/onemind_core/storage.py` | VM with a Samba and an NFS server: mount both; password never appears in ledger, logs, process list or `/proc/*/cmdline`; server down → mount `failing` and an alert, recovered automatically | STOR-1, secret store (SEC-P1) |
| FILES-1 | Node file server: confined ops, trash, tus uploads, signed tokens, downloads, archives | L | `internal/files/**`, `cmd/onemindd/main.go` (one line) | Symlink-escape and `..` fuzz suite: zero escapes; 5 GiB upload interrupted at 50 % resumes and the sha256 matches; expired or wrong-prefix token → 403; trash then restore keeps mtime | FILES-0 |
| FILES-2 | Gateway file API, roots, shares, data-plane vs action split | M | `core/onemind_core/files.py`, `core/onemind_core/file_shares.py`, `routes.py` (one line), ledger migration | Person A cannot list `home:B` (403); share `rw` to B as an action → B can write; revoke → next token refused; all share changes in the audit log | FILES-1, SEC-P1 (persons) |
| FILES-3 | Index, search, thumbnails, previews (sandboxed) | M | `internal/files/index/**`, `internal/files/thumbs/**` | 100 k files indexed on the reference box within the time budget set in the PR; rename seen by search within 5 s; a malformed image crashes only its sandbox (no network, killed at the memory limit), Files still lists the folder | FILES-1, image pins (vips, ffmpeg, poppler) |
| FILES-4 | Files page in the dashboard (list, grid, upload queue, preview, search, trash) | L | `dashboard/src/pages/Files.tsx`, `dashboard/src/files/**`; `App.tsx` route line; new components through `ui/**` PRs | Playwright: upload, rename, move, trash, restore at 390 px and 1440 px widths, no horizontal scroll; upload resumes after a network drop; axe accessibility check clean | FILES-2, FILES-3, DASH-1 |
| FILES-5 | SMB and WebDAV out, per-person users | M | `internal/files/smb/**`, `internal/files/webdav/**`; Samba package via image stream (`os/**`) | macOS and Windows clients mount `home:<person>` with that person's credentials only; guest refused; SMB1/2 refused; WebDAV over the box CA works from the desktop client | FILES-2, image stream |
| FILES-6 | Folder grants for apps and agents | M | `core/onemind_core/grants.py` (shared with MCP: agree with its owner), executor hook via sandbox owner, MCP tools via MCP owner | Install an app with a `media` slot → plan shows folder and access; container sees only that folder, read-only when `r`; agent `files_request_access` creates an action; agent `files_list` outside grants → 403; revoke removes the mount on next reconcile | FILES-0, FILES-2, CORE-SANDBOX-2, DEV-MCP-3 |
| FILES-7 | Rewind: `home:`/`shared` units, restore points per path, `files.restore` with undo | M | `internal/backup/**` units (backup stream), `core/onemind_core/files.py` Rewind routes, `dashboard/src/files/rewind/**` | Delete a file, Rewind to the previous point, restore → content and mtime match; the replaced version is in a `pre-restore` snapshot and "Undo" brings it back; a person cannot Rewind another person's Home; agent cannot list `rewind:` (403) | CORE-BACKUP-2, CORE-BACKUP-6, FILES-2 |
| FILES-8 | Cloud import with rclone: Google Drive, Dropbox, OneDrive, WebDAV; iCloud experimental | L | `internal/cloudimport/**`, `core/onemind_core/cloud_imports.py`, `cmd/onemind/cli/cloud.go`; OAuth hand-off in `mobile/**` and the desktop client (their streams) | One-time import of a test account completes and is resumable after a reboot; mirror mode: a file deleted upstream lands in Trash, not gone; no token on disk outside the secret store (grep of `/data`, `/run`, `/tmp`); expired token → `reauth` state and one alert; after any box restore, imports start paused | FILES-2, secret store, mobile shell; provider redirect check (§4.6) |
| FILES-9 | Cloud account as a backup target (restic `rclone:` backend) | S | `internal/backup/**` (backup stream) | BT-1 run to a WebDAV test target succeeds; repository opens with plain restic + rclone and the owner key alone (BT-3 analogue); a cloud target counts as the off-site copy for the badge | CORE-BACKUP-4, FILES-8 |
| FILES-10 | Migrate files in from a NAS, old server or another self-hosted OS | M | `internal/cloudimport/migrate/**`, `cmd/onemind/cli/migrate.go` (core-owned group, coordinate with `feat/migrate-kit`) | Dry run lists counts and bytes; real run over SMB copies 50 k files, survives a reboot mid-way and resumes; checksums sampled 1 % match | STOR-2, FILES-8 |
| FILES-11 | Phone photo backup into `home:<person>/Photos` | M | `mobile/**` (`feat/mobile-photos`) | 1 000 photos uploaded with resume across app restarts; duplicates skipped by hash; works over remote access; photos appear in Files and in the next `home:` snapshot | FILES-1, FILES-2, mobile shell |

**Sequence:** FILES-0 → STOR-1, FILES-1 → FILES-2 → FILES-3, FILES-4 (parallel) → FILES-5, FILES-6, FILES-7 (after CORE-BACKUP-6) → FILES-8 → FILES-9, FILES-10. FILES-11 can start once FILES-2 is merged.

## 6. Decisions needed

| ID | Question | Recommendation |
|---|---|---|
| D-F1 | May data-plane file writes by a person inside their own spaces skip the action flow (contract rule "every state-changing request is an action")? | Yes, as in §4.1; control-plane changes stay actions. Write it into contract 12-files |
| D-F2 | Files in the core dashboard (reverse PU-16 and IA "not in v0") or as a Market app? | Core page; Rewind, restore, grants and imports are core actions and the founder focus names storage, backups and photos |
| D-F3 | Who runs the OAuth client registrations with Google, Dropbox and Microsoft (verification, quotas)? | OneMind registers installed-app clients; owners can override with their own client id in Settings |
| D-F4 | iCloud Drive at launch? | Experimental flag only; Apple's two-factor trust tokens expire and need re-sign-in |
| D-F5 | Encrypted per-person spaces beyond LUKS2 on `/data`? | Not in v1; revisit after H-11 |
