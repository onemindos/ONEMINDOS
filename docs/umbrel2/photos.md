<!-- SPDX-License-Identifier: Apache-2.0 -->
# Photos: how umbrelOS does it, and what OneMind builds

**Date:** 2026-11-12 · **Status:** proposal · **Area:** photos (phone backup, library, albums, search, map, faces) · **Source studied:** umbrelOS tag `2.1.0-beta.1`, commit `6f357e18d0a4` (read-only) · **Builds on:** contract `sdk/contracts/poc-v0.md` §3, §9, §11; `docs/architecture/CONTRACT-12-DRAFT.md` §12.1, §12.2, §12.10, §12.12, §12.13; `docs/leap/core/BACKUPS.md`; `docs/leap/core/MOBILE.md`; `docs/leap/dev/MCP.md`; `docs/security/THREAT-MODEL.md`; `research-output/13-apps-market-plugins.md`; `research-output/evidence/license-matrix.csv`.

> **Explain it like I am the founder**
> umbrelOS 2.1 has its own Photos app. Your iPhone or Android phone backs up to the box, the box spots duplicates, and you get a timeline, albums, favourites, a trash and a world map. It has no faces, no "search for dog", no place names and no sharing between people in the house.
> OneMind will have its own Photos service too, written by us. It matches umbrel on backup and browsing, then beats it where a family cares: shared albums between people in the house, a phone that only frees space once the photo is also in a **verified** off-box backup, uploads that resume after a dropped connection, a map that works with no internet, and AI agents that can search and suggest albums but can never delete or share without your OK.
> Immich (the popular open-source photo app) stays available in the Market for people who want it. It can read the same photos without a second copy and without a second phone app.

**Legal note.** umbrelOS is PolyForm Noncommercial 1.0.0 (checked at the tag above). This page describes umbrel's design and cites its file paths. Nothing from umbrel (code, strings, assets, UI text) is copied into OneMind, and the OneMind design below is our own, built on components whose licences are listed in §4.2.

---

## 1. How umbrelOS does it (at `6f357e18d0a4`)

Paths below are relative to the umbrel repository root. `P/` = `packages/umbreld/source/modules/photos/`, `F/` = `packages/umbreld/source/modules/files/`, `UI/` = `packages/ui/src/features/photos/`.

### 1.1 Architecture in one picture

```
 iPhone (PhotoKit + background upload extension)      Android (MediaStore + WorkManager)
           │  grant-bound uploads, claim, receipts            │
           ▼                                                  ▼
 umbreld ── Photos module (P/) ───────────────► Files module (F/)
           │  durable state: umbrel.db (photos_* tables)      │  bytes = ordinary files in the account's Home
           │  sources, receipts, favourites, albums           │  disposable index.db: paths, BLAKE3 hashes,
           │                                                  │  ExifTool/ffprobe metadata, full-text, thumbnails
           ▼                                                  ▼
       read model (stored projection in index.db, rebuilt from journals) ──► tRPC + HTTP ──► Photos UI (UI/)
```

- **Photos is a view over Files, not a separate store.** Photos and videos are plain files in the account's Home (or a member's own home folder). The Photos module projects every media file it is allowed to see into a library. Moving or renaming a file in Files does not lose its Photos state.
- **Two databases, two lifetimes.** Durable per-account state (sources, phone receipts, favourites, albums, covers, schema markers) lives in `photos_*` tables in the shared `umbrel.db` (`P/migrations.ts`). Everything derivable (paths, hashes, metadata, full-text, thumbnails, the stored library projection) lives in the disposable file index `index.db` and artifact folders (`P/read-model-schema.ts`, `P/indexing-schema.ts`, `F/file-index/migrations.ts`). The backup engine leaves the file index out of backups (`packages/umbreld/source/modules/backups/backups.ts`, the ignore list near line 779).
- **Identity is content.** A logical photo is its 32-byte BLAKE3 hash (`F/blake3.ts`, `blake3-wasm-rs` 0.6.6 in `packages/umbreld/package.json`). Favourites, album membership and covers are keyed by account plus hash, so they survive moves, Trash round trips and an index rebuild. An in-place edit is a new hash and starts fresh.
- **Read model.** `P/library-sql.ts` defines authorization, canonical location, Live Photo pairing and presentation fields; `P/read-model.ts` stores the result and keeps it fresh from change journals written by triggers in both databases. Every read first drains pending journals. Two SQLite reader threads (one reserved for quick requests) serve Files and Photos; writes stay on the file-index worker (`P/README.md`). A large first upgrade rebuilds the projection synchronously and delays Photos start-up on big libraries.
- **Metadata.** ExifTool is the single metadata reader for stills and videos (dates with offsets, camera, lens, exposure, GPS, projection, Apple Live Photo identifiers); ffprobe only answers playability, duration and display size; ImageMagick makes thumbnails and the average-colour tint (`F/file-index-enrichment.ts`, `P/CONTRACT.md` "Media metadata readers"). Camera RAW containers (ARW, CR2, CR3, DNG, NEF, ORF, RAF, RW2) are handled with explicit coders.
- **Sub-kinds.** Spherical, Live, screenshot and panorama are derived from the one metadata pass, in that priority order. Live pairs (still + short motion clip) are derived at query time and the motion file is hidden from lists and counts; delete and restore cascade to it.
- **Thumbnails.** Three WebP renditions by short edge (small, medium, large) generated in the background and on demand; originals and motion clips are served with HTTP range support.
- **Deletion.** Files' Trash is the only deletion truth: there is no Photos-specific deletion flag, no retention period and no automatic purge. Permanent delete goes through Files with a revision check.
- **Built-in source scope.** The permanent "this box" source can import everything in Home, everything except some folders, or only some folders.

Key files: `P/photos.ts` (module, 1315 lines), `P/repository.ts` (queries, 2114), `P/routes.ts` (tRPC), `P/api.ts` (HTTP), `P/types.ts`, `P/map-tiles.ts`, `P/CONTRACT.md` and `P/README.md` (the backend contract and its read-model notes, both worth reading in full).

### 1.2 API surface (described, not reproduced)

- **tRPC, per account** (`P/routes.ts`, all `privateProcedureWithMembers`): library summary (counts, size, per-month calendar) and indexing status; item list with one filter object (text, kind, sub-kind, favourite, deleted, sources, albums, date ranges, map bounds) and keyset paging; item detail, neighbours, favourite, delete to Trash, restore, delete permanently; albums (list, create, rename, set cover, delete, add and remove items); sources (list, update scope, remove a phone with or without its items, count what removal would move); download tickets; phone backup grants, backup-source listing and receipt confirmation.
- **HTTP** (`P/api.ts`): thumbnails, originals, Live Photo motion clips, ticketed single or zip download, browser upload (one file per request, deduplicated by hash before it becomes visible), a phone "claim" endpoint, packed binary map points, and map tiles.
- **Events:** one payload-less "photos changed" event on the event bus; the UI debounces and refetches.

### 1.3 Phone backup protocol and dedupe

1. **Pairing and grant.** A phone registers through the umbrel mobile app; there is no "add source" call in the web UI (`UI/components/sources/add-source-dialog.tsx` hands over to the app). The app asks for a **source-bound backup grant** (`P/photos.ts` `createBackupGrant`, issued by the auth module). Source ids are random, not derived from Apple device data (`clients/apple/UmbrelKit/Sources/UmbrelKit/Backup/PhotoBackup.swift`).
2. **Resource keys.** Each PhotoKit or MediaStore resource gets a stable 64-hex key computed on the phone; Live Photo still and motion get separate keys (`clients/apple/UmbrelKit/Sources/UmbrelKit/Backup/PhotoBackupPlanner.swift`). The phone sends the key, file extension, original file name and, as a fallback date, the platform's creation date in request headers. Newer apps also send the asset's iCloud identity and resource role.
3. **Storage layout.** Uploaded bytes become ordinary files under the person's Photos folder in a per-device subfolder, sharded by the first byte of the key. The layout is presentation, not identity.
4. **Receipts.** `umbrel.db` records `(account, source, resource key, content hash)`. Before answering, the server reopens the indexed file and checks that it is still the exact revision; an index row alone is never proof. A receipt is satisfied by **any visible Home copy** of those bytes, wherever the user moved it. **Trash never satisfies a receipt**, so a photo deleted on the box is sent again while it still exists on the phone (no two-way delete sync).
5. **Dedupe.** Exact retries reuse the receipt. A new upload whose hash matches bytes **this source already has a receipt for** is recorded against that file and the staged bytes are discarded. Bytes only another source (or another account) holds are never matched, which avoids revealing other people's content. Two simultaneous uploads of the same new bytes can still store two copies (documented in `P/CONTRACT.md`).
6. **Restored phones.** A phone restored from an old one can continue the old backup (capability `continue-source`); before each batch it "claims" up to 256 resources by key or by iCloud identity plus role, and the server confirms what it already holds without any upload. Edited assets are never claimed by identity.
7. **Removal.** Unpairing can keep the items or move the phone's unique items to Trash; bytes another phone's receipt names are kept. Removal is a durable intent replayed after a restart.
8. **iOS client.** Shared code in `clients/apple/UmbrelKit/Sources/UmbrelKit/Backup/` (planner, ledger in an App Group SQLite database, receipt cache, identity pass, reminder, preferences). PhotoKit's system-owned background upload extension uploads while the app is closed, but **it cannot check the box's certificate, so it may only send plain HTTP to a Tailscale address**; the app itself uses a pinned connection while open (comments in `PhotoBackup.swift`). The server answers the resumable-upload probe with 501 (`P/api.ts`, the upload OPTIONS handler), so a dropped upload restarts from zero.
9. **Android client.** `clients/android/umbrelkit/src/main/kotlin/com/umbrel/kit/backup/` (engine, ledger, MediaStore generation cursor, WorkManager scheduling with network qualifiers for Wi-Fi, metered and roaming, foreground transfer service).

### 1.4 Albums, search, map, faces

- **Albums:** per account, manual, with a chosen or newest-member cover. No shared albums between accounts, no smart albums, no public links.
- **Search:** SQLite FTS5 over file names, camera make and model, and the EXIF user comment (`F/file-index/migrations.ts`). Suggestions are assembled in the browser from summary, sources and albums (`UI/components/search/suggest.ts`). No semantic ("dog on a beach") search, no place-name search, no OCR.
- **Map:** MapLibre GL 6.11.2 with `@protomaps/basemaps` 5.7.2 (`packages/ui/package.json`). The server returns every located item as packed 52-byte binary records for client-side clustering, and a bounds filter feeds the side list. Tiles are fetched by the box, as the map asks, from one planet build Umbrel hosts on Cloudflare R2, located through a signed URL from `api.umbrel.com`; browsers cache tiles under the build name. Offline, the UI draws a bundled Natural Earth atlas (`P/map-tiles.ts`, `UI/components/map/`). Cloudflare sees the box address and which areas are viewed.
- **Faces, people, place names, semantic search, Android motion photos, drives and network shares as sources:** explicitly **not in v1** (`P/CONTRACT.md`, "Not in v1"). The indexer already stores GPS so places can come later without a rescan.

### 1.5 User-visible flow

1. Open Photos: the timeline appears grouped by month with a date scrubber; a WebGL tile renderer draws large grids (`UI/components/listing/gpu/`, `UI/components/listing/time-rail/`).
2. Pinch or slider to zoom the grid; marquee and swipe selection; hover plays Live Photos.
3. Open an item: a lightbox with filmstrip, zoom, Live Photo playback and an info panel (camera, lens, exposure, coordinates, albums, "show in Files") (`UI/components/viewer/`).
4. Sidebar presets: library, favourites, videos, Live Photos, panoramas, screenshots, 360°, map, albums, sources, recently deleted (`UI/components/sidebar/`).
5. Drag and drop or pick files to upload; an island reports added versus already present (`UI/components/upload-island.tsx`).
6. Sources page: this box with its folder scope, plus each paired phone with stats and remove (`UI/components/sources/`).
7. On the phone app: choose library access and network rules, then backup runs in the background; a reminder nudges when it falls behind.

### 1.6 Accounts, backups, upgrades, AI

- **Accounts:** owner plus members; each has their own Home and their own library. Nothing is shared between accounts in Photos (`P/routes.ts`, per-account procedures only).
- **Backups:** `umbrel.db` (favourites, albums, receipts) is backed up; the file index is not and is rebuilt. Photos bytes are backed up as Home files.
- **Upgrades:** the durable Photos schema reached 11 in this release. An OS fallback to an older build **cannot serve Photos** because older code refuses a newer schema; recovery is to go forward again or restore a pre-upgrade data backup (`P/README.md`, "Upgrade and rollback").
- **AI and MCP:** umbrel's MCP server exposes apps, files, machines and system tools (`packages/umbreld/source/modules/mcp/tools/`); there are **no Photos tools**.

### 1.7 How umbrel relates to Immich

There is no relationship in code. Immich is an ordinary App Store app (it appears in the welcome screen's fallback "most installed" deck in `packages/ui/src/modules/desktop/welcome-desktop.tsx` and in App Store tests). Built-in Photos shares no code, data or login with it. A user who runs both gets two libraries, two phone apps and, unless they point Immich at the same folder by hand, two copies of every photo. umbrel built its own Photos because Immich is heavy (Postgres, Redis, a machine-learning container) and separate from umbrel's Files, accounts and phone app.

---

## 2. What OneMind has today

Nothing photo-specific is built. The pieces a Photos service will stand on:

| Piece | Where | State |
|---|---|---|
| Gateway principals `{id, kind, role}`, actions with owner approval, hash-chained audit | `core/onemind_core/{auth,actions,audit,ledger}.py` | `main` |
| App catalog and Market page; manifest schema | `core/onemind_core/catalog.py`, `dashboard/src/pages/Market.tsx`, `sdk/schema/onemind.app.schema.json` | `main` |
| MCP endpoint (`list_nodes`, `list_apps`, `request_action`; no approve tool) | `core/onemind_core/mcp.py` | branch `feat/gateway-agent-mcp` (`gwmcp` worktree); spec `docs/leap/dev/MCP.md` |
| Roles `owner|adult|guest` (+ `child` later); `person:<id>` ids | `docs/architecture/CONTRACT-12-DRAFT.md` §12.10 | draft |
| Action registry with risk and "policy never" types | same, §12.2 | draft |
| Manifest `backup:` hooks (`sqlite`, `exclude`, `verify`), `migrations: reversible` | same, §12.13 | draft |
| restic backups, Retain StorageClass `onemind-local`, verified-restore badge | `docs/leap/core/BACKUPS.md` (CORE-BACKUP-1…8) | proposal; branches `feat/onemindd-backup`, `feat/onemindd-storage` cut, empty |
| Edge with forward-auth per person and app, box CA | `docs/architecture/NETWORKING.md` §9.3 (branch `net`) | proposal |
| Phone shell (Expo): Connect, Home, Nodes, Apps, Approvals, Activity, Settings | `mobile/src/screens/` | `main`; photo backup is a stated v1 non-goal in `docs/leap/core/MOBILE.md` §1 |
| Mobile photos branch | `feat/mobile-photos` (`mphotos` worktree) | cut from `main`, empty |
| Design system components | `ui/src/components/` | `main` |
| Immich as a Market candidate: AGPL-3.0, class L2, queue rank 1 | `apps/_intake/CANDIDATES.md`, `apps/_intake/candidates.csv` | facts only |
| Immich licence row: v3.4.0, AGPL-3.0, separate program only, never copied into the core | `research-output/evidence/license-matrix.csv` (C-LIC-028) | recorded |
| Immich in the Pro tier list, 2000Mi | `research-output/13-apps-market-plugins.md` §3 | research |
| Immich app-page mock | `docs/design/IA.md` §2.3 (`screens/app-immich.png`) | design |
| `/data` on ext4, not encrypted yet (LUKS2 planned) | `docs/security/THREAT-MODEL.md` | known gap |

---

## 3. Where OneMind matches umbrel, and where it beats it

### 3.1 Match (table stakes)

| umbrel 2.1 has | OneMind equivalent |
|---|---|
| iPhone and Android background backup with per-device sources | Same, in the OneMind phone app (PH-4) |
| Content-hash identity, durable state that survives moves and index rebuilds | Same principle, our own schema (§4.3) |
| Timeline, zoomable grid, date scrubber, viewer with info, Live Photos, sub-kinds | PH-5, PH-2 |
| Favourites, albums with covers, Trash with restore | PH-5 |
| Browser upload with duplicate detection | PH-3 |
| Map of located photos | PH-7 |
| Restored phone continues its old backup without re-uploading | PH-3 claim by platform identity |

### 3.2 Beat (measured)

| # | Where umbrel stops | What OneMind does | Test that proves it |
|---|---|---|---|
| B1 | Phone may free space once the box has a copy; nothing ties this to backups | **Safe-to-free:** the phone offers "free up space" only for photos that are on the box **and** inside a backup snapshot that passed a verified restore (CORE-BACKUP-7). The owner can relax this to "on box" with a warning | PH-8 T3 |
| B2 | Uploads restart from zero after a dropped connection (resumable probe answered 501) | Resumable uploads (IETF HTTP resumable upload draft; iOS URLSession support since iOS 17 is UNVERIFIED and checked in PH-3; our Android client implements it); a 4 GB video survives a network change | PH-3 T4 |
| B3 | iOS background extension falls back to plain HTTP over a VPN address | HTTPS only, always. Background uploads use a certificate the phone's system trusts (§4.7, DN-1); if none is possible, background upload is off and the app says so | PH-4 T5 |
| B4 | No sharing between people in the house | Household libraries: shared albums with viewer or contributor roles, partner sharing, child libraries managed by a parent (§4.6) | PH-6 T1–T4 |
| B5 | Two phones uploading the same new bytes can store two copies; no cross-person single instance | Single-instance storage across the household **without** revealing who has what: the server always asks for the bytes it cannot prove the person already has, then stores them once (reflink or hardlink, refcounted) | PH-3 T6 |
| B6 | No place names; map tiles come from a vendor CDN; offline gets a world atlas | Offline reverse geocoding to city and country names; a regional vector basemap stored on the box, so the map works with no internet and tells no third party where you look | PH-7 T1–T3 |
| B7 | No semantic search, no faces | Opt-in on-box semantic search and face grouping with **permissively licensed models only** (§4.2), on CPU, paused while the box is busy; nothing leaves the box | PH-12 |
| B8 | OS fallback leaves Photos unavailable (newer schema refused) | `migrations: reversible`: every catalog migration is expand-then-contract, the previous release still reads the expanded schema, and a snapshot is taken before any migration. Rolling back the app keeps Photos working | PH-8 T5 |
| B9 | No Photos tools for AI agents | MCP read tools (search, albums, item metadata, thumbnails at 512px) and **request-only** changes (create album, add to album, move to Trash, share link) that wait for the owner's approval (§4.5) | PH-9 |
| B10 | Built-in Photos and Immich are strangers: two libraries, two phone apps, two copies | Immich from the Market attaches to the OneMind library **read-only** as an external library: one copy, one phone app, Immich's extra features still available (§4.8) | PH-13 T2 |
| B11 | Drives, network shares and camera cards are "post v1" | Import from a USB drive or SD card, a folder, Google Takeout and an iCloud Photos export, with the export's sidecar dates applied (PH-11) | PH-11 T1–T3 |
| B12 | A large upgrade rebuilds the library projection synchronously and delays start-up | Projection rebuilds run in the background with the old projection still served, and progress is shown | PH-1 T4 |

---

## 4. OneMind design

### 4.1 Decision: built-in Photos service, Immich as a Market app

| Option | For | Against |
|---|---|---|
| **A. Immich as the photos answer** (Market app, preinstalled) | Mature, faces, CLIP search, big community | AGPL-3.0 (L2): fine as a separate, unmodified program, but we cannot change it without publishing our changes, so it cannot become part of our accounts, approvals, backups and phone app. Its own phone app and login. Postgres + Redis/Valkey + ML container (2000Mi in research 13) is heavy for a Pi-class hub. Its default face models are published by InsightFace with **non-commercial research terms (UNVERIFIED; PH-0 T2 reads each model file)**, so a sold box must not ship or advertise them. Its release pace and breaking changes are outside our "deployments never fail" control |
| **B. Built-in OneMind Photos** (our code, Apache-2.0) | One identity, one phone app, approvals, safe-to-free, household sharing, MCP, backups and migrations under our rules; small enough for every box | We build and maintain it; faces and semantic search come later |
| **C. Both** | B is the default; A stays for people who want Immich | Two UIs; solved by attaching Immich read-only to B's library (B10) |

**Decision: C.** OneMind Photos is a first-party service shipped with every box. Immich is a Market app (L2, unmodified, licence notices kept, per C-LIC-028), installed only by the owner's choice, with a one-click read-only attach to the OneMind library. PhotoPrism (AGPL-3.0) and LibrePhotos (MIT) can enter the Market through the normal pipeline the same way.

### 4.2 Components and licences

All run as separate programs or libraries linked into our own code. Versions marked *pin at PH-0* are candidates; PH-0 adds each as a row to `research-output/evidence/license-matrix.csv` with a pinned commit before any code depends on it.

| Component | Use | Licence (SPDX) | Version |
|---|---|---|---|
| OneMind Photos service (Go) | catalog, ingest, API, backup protocol | Apache-2.0 (ours) | – |
| SQLite (via `modernc.org/sqlite`, pure Go) | catalog and FTS5 search | blessing (public domain); driver BSD-3-Clause | SQLite row exists; driver *pin at PH-0* |
| BLAKE3 (Go implementation, e.g. `lukechampine.com/blake3`) | content hash | MIT (Go port); reference CC0-1.0 OR Apache-2.0 | *pin at PH-0* |
| ExifTool | metadata reader, run as a separate process | Artistic-1.0-Perl OR GPL-1.0-or-later | *pin at PH-0* |
| libvips (via `govips` or the `vips` CLI) | thumbnails, HEIC/AVIF/RAW decode through its loaders | LGPL-2.1-or-later (dynamic link or separate process) | *pin at PH-0* |
| libheif + libde265 (HEIC decode only, no encoder) | iPhone HEIC | LGPL-3.0-or-later | *pin at PH-0* |
| FFmpeg / ffprobe, **LGPL build** (no `--enable-gpl`, no x264/x265) | video posters, duration, transcode for playback | LGPL-2.1-or-later | *pin at PH-0* |
| MapLibre GL JS | map in the dashboard | BSD-3-Clause | *pin at PH-0* |
| PMTiles | offline tile archive on the box | BSD-3-Clause | row exists (`aec8fa134122`) |
| Protomaps basemap styles; OpenStreetMap data | regional basemap extract | BSD-3-Clause (styles); ODbL-1.0 (data: attribution shown on the map, extract offered on request) | *pin at PH-0* |
| GeoNames `cities15000` | offline reverse geocoding | CC-BY-4.0 (attribution in About) | *pin at PH-0* |
| Natural Earth | low-zoom fallback | public domain | *pin at PH-0* |
| ONNX Runtime | on-box inference (PH-12) | MIT | row exists (v1.31.1) |
| sqlite-vec | vector search inside SQLite (PH-12) | MIT OR Apache-2.0 | *pin at PH-0* |
| Image-text embedding model (an OpenCLIP or SigLIP checkpoint whose weights are MIT or Apache-2.0) | semantic search (PH-12) | per checkpoint; **only MIT or Apache-2.0 weights trained on data whose terms allow commercial use** | *pin at PH-0* |
| Face detection: YuNet; face embedding: SFace (OpenCV model zoo) | face grouping (PH-12) | UNVERIFIED: MIT (YuNet), Apache-2.0 (SFace); PH-0 reads each file | *pin at PH-0* |
| restic | backups of the library | BSD-2-Clause | row exists (v0.19.1) |
| Immich (Market app only) | optional | AGPL-3.0 | row exists (v3.4.0) |

**Excluded:** InsightFace pretrained models (non-commercial terms), any model whose weights or training data carry non-commercial terms, GPL builds of FFmpeg in our image, and anything under PolyForm, BUSL or similar (L3). The app gate's licence check (contract §9.4) also runs on the Photos image's SBOM.

### 4.3 Placement and data model

**Placement.** OneMind Photos is a first-party app `photos` (manifest `apps/photos/onemind.app.yaml`, namespace `app-photos`, contract §11.5), installed at first boot and marked first-party so it cannot be removed by an agent. It serves its UI and API at `photos.<box>` behind the edge's forward-auth (NETWORKING §9.3), so every request carries a gateway-verified principal. It runs on the hub by default; the transcoding and ML workers (PH-12) may be placed on a stronger node through the fabric's capability labels.

**Storage** (one PVC on `onemind-local`, Retain, CORE-BACKUP-1):

```
library/<person-id>/<source-slug>/<YYYY>/<MM>/<original-name>   originals, plain files, never modified
library/.shared-store/<aa>/<hash>                                 single-instance bytes (B5), hardlinked or reflinked
catalog.db                                                        durable state (SQLite, WAL), backed up
derived/                                                          thumbnails, posters, embeddings, projection: disposable, excluded from backup
staging/                                                          in-flight uploads, never visible
```

Originals are human-readable files on purpose: if OneMind is gone, the photos are still a normal folder tree.

**Durable tables** (`catalog.db`; ids are prefixed ULIDs per §12.1):

| Table | Key fields |
|---|---|
| `blobs` | `hash` (BLAKE3, 32 bytes), `size`, `mime`, `refcount`, `store_path`, `verified_at` |
| `assets` | `ast_` id, `owner` (`person:<id>`), `kind` (photo, video), `sub_kind` (live, panorama, screenshot, spherical, burst, raw_pair, motion_photo), `taken_at`, `tz_offset_min`, `width`, `height`, `duration_ms`, `lat`, `lng`, `place_id?`, `tint`, `created_at` |
| `asset_files` | `asset_id`, `blob_hash`, `role` (original, motion, raw, edited, sidecar), `library_path` |
| `sources` | `src_` id, `owner`, `type` (box, iphone, android, import, folder), `name`, `platform`, `device_id`, `scope?`, `last_seen_at` |
| `receipts` | `source_id`, `client_key`, `blob_hash`, `platform_identity?`, `role?`, `received_at` |
| `albums` | `alb_` id, `owner`, `name`, `cover_asset?`, `kind` (manual, smart), `rule?` (smart albums: a saved filter) |
| `album_items` | `album_id`, `asset_id`, `added_by`, `added_at` |
| `album_members` | `album_id`, `person`, `role` (viewer, contributor) |
| `person_state` | `person`, `asset_id`, `favorite`, `hidden` |
| `trash` | `asset_id`, `deleted_by`, `deleted_at`, `purge_after` (default 30 days; never before the next verified backup, B1) |
| `coverage` | `blob_hash`, `snapshot_id`, `target_id`, `verified_restore_at` (filled from CORE-BACKUP-8 events) |
| `places` | `place_id`, `name`, `admin`, `country` (from GeoNames) |
| `schema_migrations` | `version`, `phase` (expand, contract), `applied_at` |

Favourites, hidden and album membership are keyed by **asset**, and an asset is tied to its blobs, so state survives moves, Trash and a derived-data rebuild. An edit made in OneMind adds an `edited` file to the same asset instead of replacing the original.

### 4.4 API, CLI and events (contract style)

The shapes below follow §12.1: `/v1/...`, RFC 3339 UTC times, prefixed ULIDs, `{"items": [...], "next_cursor": ...}` lists with `limit` (default 50, max 500), the §3 error envelope with `reason`. They are proposed for a contract PR **§12-p** (PH-0); nothing is binding until that PR merges.

| Method and path | Who | Purpose |
|---|---|---|
| `GET /v1/photos/summary` | person | counts, sizes, months that hold items |
| `GET /v1/photos/assets?filter=…&cursor=…` | person, agent (grant) | timeline page; filter = `q`, `kind`, `sub_kind`, `favorite`, `album_id`, `source_id`, `place`, `taken_from/to`, `bbox`, `trashed` |
| `GET /v1/photos/assets/{id}` | person, agent (grant) | detail incl. EXIF and place |
| `GET /v1/photos/assets/{id}/thumb?size=s|m|l` · `/original` · `/motion` | person; agent only `s` and `m` | renditions; originals support range requests |
| `PATCH /v1/photos/assets` | person | bulk favourite or hide |
| `POST /v1/photos/assets/trash` · `/restore` | person (own assets) | move to Trash, restore |
| `GET/POST/PATCH/DELETE /v1/photos/albums[/{id}]`, `POST /v1/photos/albums/{id}/items`, `/members` | person (owner or contributor) | albums, smart albums, sharing |
| `GET /v1/photos/map/points?filter=…` | person | compact located points |
| `GET /v1/photos/map/tiles/{z}/{x}/{y}` | person | tiles from the box's PMTiles archive |
| `POST /v1/photos/sources` | device | register or continue a phone source (idempotent by client id) |
| `POST /v1/photos/sources/{id}/check` | device | up to 500 `{client_key, size, hash?, platform_identity?, role?}` → each `have`, `need` |
| `POST /v1/photos/uploads` (+ resumable `HEAD`/`PATCH` per the draft) | device, person | upload; server hashes, verifies optional client hash, fsyncs, records receipt |
| `GET /v1/photos/sources/{id}/coverage?since=…` | device | per key: `on_box`, `backed_up`, `verified` (B1) |
| `GET /v1/photos/events` | person, device | SSE on top of `GET /v1/stream` filtering (`photos.changed`, `photos.indexing`) |

**Actions** (added to the §12.2 registry; executed by the gateway calling the Photos service):

| Type | Params | Risk | May request | Policy |
|---|---|---|---|---|
| `photos.album.create` / `.add` | `{owner, name?, album_id?, asset_ids}` | low | O, A, adult | yes |
| `photos.trash` | `{asset_ids}` | medium | O, A, adult (own) | no |
| `photos.share.link` | `{album_id, expires_at, strip_location: true}` | high | O, A, adult | **never** (it exposes data outside the house) |
| `photos.purge` | `{asset_ids?}` (Trash only) | critical | O, adult (own) | **never** |
| `photos.source.remove` | `{source_id, keep_items}` | medium | O, adult (own) | no |
| `photos.reindex` | `{scope}` | low | O, A, Au | yes |

People act directly on their own library through the endpoints (favourite, album, Trash). Agents, automations and anything that leaves the house go through actions.

**CLI** (`cmd/onemind/cli/photos.go`, one line in `root.go`): `onemind photos status`, `onemind photos import <path> [--as <person>]` (requests an import job), `onemind photos sources`, `onemind photos verify` (rehash a sample against `blobs`), `onemind photos reindex`.

**Events** (§12.3 envelope): `onemind.event.photos.backup.completed`, `.backup.stalled` (a phone silent for 7 days), `.import.finished`, `.integrity.failed`. Notifications (CORE-NOTIFY) turn the last two into alerts.

### 4.5 MCP surface (agents request, owner approves)

Tools projected through the gateway's MCP catalog (DEV-PLG-4 path), only for agents holding grant `photos:read` **for a named person's library** (never "all people"):

| Tool | Equals | Notes |
|---|---|---|
| `photos_search` | `GET /v1/photos/assets` | metadata only; at most 200 per call |
| `photos_get` | `GET /v1/photos/assets/{id}` | EXIF user comment and file names are returned inside an `untrusted_text` field (threat model §4.2) |
| `photos_thumbnail` | thumb `s` or `m` as an MCP image resource | never originals, never `l` |
| `photos_albums` | `GET /v1/photos/albums` | |
| `photos_backup_status` | per-source last backup and coverage counts | no file names |
| `request_action` | `photos.album.create`, `.add`, `photos.trash`, `photos.share.link`, `photos.reindex` | appears on the approval card with thumbnails rendered by the gateway, not by the agent |

No tool purges, removes a source, changes sharing members or reads a child's library. Every call is audited with the agent id, the person whose library was read and the count of items returned.

### 4.6 Accounts for the whole house

- Each person (`person:<id>`, roles per §12.10) has a private library. The owner role does **not** grant browsing other adults' libraries; it grants removing a person, which first offers to move their library to a kept archive.
- **Shared albums:** owner of the album adds members as viewer or contributor; contributors add their own assets (the blob is shared, not copied).
- **Partner sharing:** a person may share their whole library, or from a date, with one other person, read-only.
- **Children** (when the `child` role lands): a child's library is visible to the parents named on the child; a child cannot create share links; agents never see it.
- **Guests:** no library; can view albums shared with them through a time-limited invitation.

### 4.7 Security

| Risk | Control |
|---|---|
| Cross-person data leak | Every query is scoped by principal in one place (a repository layer with a mandatory `viewer` argument); a test suite runs every endpoint as a second person and expects 404 |
| Hash oracle (learning whether someone else has a photo) | `check` answers only from the asking person's own receipts and assets; single instance happens after the upload (B5) |
| Phone token theft | Device principal `device:<id>` per phone, scoped to `photos:backup` for one person and source; revocable from Settings and from the phone list |
| Plain HTTP from background uploads | Refused by the service. Background uploads need a certificate the phone's OS trusts (DN-1) |
| Location leaks on sharing | Share links strip GPS and serial numbers by default; the approval card says what will be visible |
| Malicious files (decoder exploits) | Decoders (ExifTool, libvips, ffmpeg) run in a separate worker with no network, read-only library mount, seccomp default profile, memory and time limits; a crashing file is quarantined with a reason |
| Prompt injection via EXIF text or file names | Marked `untrusted_text` in MCP output and never shown on approval cards as instructions |
| Data at rest | Depends on LUKS2 for `/data` (CORE-SEC-5); until then the Photos settings page states that photos are not encrypted on disk |
| Silent corruption | `blobs.verified_at`: a weekly background rehash of a rotating sample; mismatch raises `photos.integrity.failed` and points to the last verified backup |

**DN-1 (decision needed, founder):** how background uploads on iOS get a trusted certificate. Options: (a) at pairing, install the box CA as a configuration profile the person approves in iOS Settings; (b) use a publicly trusted certificate when the owner has set up a remote-access name; (c) no background upload on iOS, only while the app is open. Recommendation: (b) where available, else (a), with (c) as the honest fallback. Plain HTTP is not an option.

### 4.8 Immich as a Market app

- Packaged through the normal pipeline (`apps/immich/`, gate, scan, tier), unmodified, AGPL notices kept, source links on the app page.
- The manifest declares a setting `attach_onemind_library` (default on). When on, the install plan mounts the person's OneMind library **read-only** into Immich as an external library. Immich's own uploads (if a user keeps the Immich phone app) go to its own volume, clearly labelled.
- Machine learning in Immich is **off by default** on OneMind; turning it on shows that model downloads come from Immich's model host and may carry their own terms (DN-2: whether we allow Immich face recognition on sold boxes at all, after PH-0 checks the model terms).
- Sign-in: Immich's OAuth login against the OneMind identity provider once SEC-P1 / Kanidm (BD-03) exists; until then, behind forward-auth plus its own login.

### 4.9 UI screens

Dashboard (`dashboard/src/pages/photos/`, components in `ui/src/components/` where shared):

1. **Library:** month-grouped timeline, zoom levels, date scrubber, multi-select, keyboard navigation; GPU-drawn grid for large libraries; empty state that offers "Back up your phone" (QR) and "Import from a drive".
2. **Viewer:** full-screen, swipe and arrow navigation, Live and motion photos, video with seeking, info drawer (date, camera, place, albums, shared with), favourite, add to album, Trash.
3. **Albums:** mine, shared with me, smart albums; album page with members and share link state.
4. **Places:** map plus a list of places by name; works offline.
5. **People** and **Search by description** (PH-12, behind a setting).
6. **Trash:** days left before purge, and a note when purge waits for the next verified backup.
7. **Devices and imports:** phones with last backup, coverage (on box / backed up / verified), pause, remove; import jobs with progress.
8. **Settings:** folder scope for the box source, trash retention, safe-to-free rule, ML switches, storage used per person.

Home and dock (uileap): a Photos tile, plus widgets "Backed up today" and "On this day".

Phone (`mobile/`, branch `feat/mobile-photos`): **Backup** screen (status, per-network rules, battery rule, coverage, "Free up space" listing only safe items), and later a browse tab using the same API.

---

## 5. Epics

Stream: **Photos**, branches `feat/photos-<n>-<slug>`, each in its own worktree, claimed by a draft PR (WORKSTREAMS §6). Paths owned by the Photos stream: `cmd/onemind-photos/**`, `internal/photos/**`, `apps/photos/**`, `dashboard/src/pages/photos/**`, `test/photos/**`. Hotspots change only in their own small PRs (WORKSTREAMS §4).

| Epic | Title | Owner paths | Depends on | Acceptance tests |
|---|---|---|---|---|
| **PH-0** | Licence rows and contract §12-p | `research-output/evidence/license-matrix.csv` (add-only rows); contract PR `contract/12-photos` on `sdk/contracts/poc-v0.md` (hotspot, contract owner) | – | T1 every §4.2 component has a row with SPDX, pinned commit and use; T2 each model file's licence and training-data terms are read and recorded, and any non-commercial one is marked excluded; T3 §12-p merged with endpoint, action and event shapes |
| **PH-1** | Service skeleton and catalog | `cmd/onemind-photos/**`, `internal/photos/catalog/**`, `apps/photos/**` | PH-0, CORE-BACKUP-1 | T1 `catalog.db` migrations are expand/contract, and the previous release's binary reads the new schema; T2 app installs at first boot in `app-photos` with requests and limits, health and `backup:` hooks; T3 every list endpoint pages correctly at 100k assets (p95 < 150 ms on the reference hub); T4 a full projection rebuild runs while reads keep serving the old projection |
| **PH-2** | Ingest and indexer | `internal/photos/ingest/**` | PH-1 | T1 golden corpus (JPEG, HEIC, ProRAW/DNG, RAW+JPEG, Live Photo pair, Android motion photo, panorama, 360°, screenshot, video with rotation) yields the expected kind, sub-kind, date with offset, size and GPS; T2 decoders run in the sandboxed worker without network; a crafted file that crashes a decoder is quarantined, not retried forever; T3 three thumbnail sizes and a video poster for each item |
| **PH-3** | Backup protocol server | `internal/photos/backup/**` | PH-1, CORE-MOBILE-2 (device principals) | T1 `check` returns `have` only for the asking person's receipts; T2 an exact retry and a moved file both still satisfy the receipt; T3 Trash does not satisfy a receipt; T4 resumable upload of a 4 GB file survives three forced disconnects and ends with one blob; T5 a restored phone continues its source by platform identity without uploading; T6 two people uploading the same bytes concurrently end with one blob, refcount 2, and neither can learn the other has it |
| **PH-4** | Phone backup (iOS and Android) | `mobile/src/photos/**`, `mobile/modules/photo-backup/**` on `feat/mobile-photos` (with the mobile owner; `mobile/app.json` hotspot) | PH-3, DN-1 | T1 first backup of a 20k-item library completes on Wi-Fi with the app in the background (Android WorkManager; iOS background upload); T2 metered and roaming rules respected; T3 killing the app mid-upload resumes, not restarts; T4 no plain HTTP request is ever sent (proxy capture); T5 "Free up space" lists only verified items under the default rule |
| **PH-5** | Dashboard Photos UI | `dashboard/src/pages/photos/**`; one route line in `dashboard/src/App.tsx` (hotspot) | PH-1, PH-2, PH-3 | T1 timeline scroll at 60 fps with 50k items on the reference laptop; T2 viewer, favourites, albums, Trash and restore work by keyboard and screen reader (axe clean); T3 browser upload reports added versus already present; T4 screenshots in `docs/design/screens/` |
| **PH-6** | Household sharing | `internal/photos/share/**`, `dashboard/src/pages/photos/sharing/**` | PH-5, SEC-P1 identity | T1 the second-person suite: every endpoint as another adult returns 404 for private assets; T2 a contributor's addition appears to members without a byte copy; T3 partner sharing from a date shows only later items; T4 a child's library is visible to its parents only |
| **PH-7** | Map and places | `internal/photos/places/**`, `dashboard/src/pages/photos/map/**` | PH-2 | T1 with the network unplugged, map tiles and place names still load; T2 reverse geocoding names a known coordinate set correctly to city level; T3 no outbound request is made while browsing the map (egress capture); T4 OSM attribution visible |
| **PH-8** | Storage safety and backups | `internal/photos/safety/**`; manifest `backup:` block in `apps/photos/` | PH-1, CORE-BACKUP-5, CORE-BACKUP-7 | T1 `catalog.db` is captured with the SQLite hook and `derived/` is excluded; T2 restoring the app from a snapshot gives back albums, favourites and receipts, and phones do not re-upload; T3 coverage marks items `verified` only after a verified restore; purge waits for it; T4 weekly rehash detects a flipped byte and raises `photos.integrity.failed`; T5 rolling the app back one release after a migration keeps Photos readable |
| **PH-9** | MCP tools and actions | `internal/photos/agent/**`; catalog entry via the DEV-PLG-4 projection PR (agreed with the MCP owner); registry rows through the gateway-core owner | PH-0, PH-1, DEV-MCP grants | T1 `tools/list` shows Photos tools only with `photos:read` for that person; T2 no tool reaches purge, member changes or a child's library (static and runtime tests); T3 `request_action photos.share.link` creates a pending action that policy cannot approve; T4 injection fixtures in EXIF comments stay inert and are returned as `untrusted_text`; T5 every call is in the audit log |
| **PH-10** | CLI | `cmd/onemind/cli/photos.go`; one line in `cmd/onemind/cli/root.go` (hotspot) | PH-1, DEV-CLI-1 | T1 `status`, `sources`, `import`, `verify`, `reindex` work against the gateway with golden output in `sdk/testdata/`; T2 `import` creates an action and does not write directly |
| **PH-11** | Importers | `internal/photos/importers/**` | PH-2 | T1 a USB drive or SD card import keeps folder names as albums when asked and skips duplicates; T2 Google Takeout sidecar JSON dates and locations are applied; T3 an iCloud Photos export keeps Live Photo pairs |
| **PH-12** | Semantic search and faces (opt-in) | `internal/photos/ml/**`, `dashboard/src/pages/photos/people/**` | PH-0 T2, PH-5 | T1 only models marked allowed in PH-0 are loadable (hash pinned); T2 indexing pauses when the box is busy or on battery-backed power; T3 search recall on a labelled 1k-photo set above the bar set in the epic's spec; T4 deleting a person's face cluster deletes its embeddings; T5 nothing leaves the box (egress capture) |
| **PH-13** | Immich Market app with read-only attach | `apps/immich/**` (app pipeline stream) | PH-1, W2-PIPE | T1 the gate passes with licence class L2 and notices kept; T2 with attach on, Immich lists the OneMind library and cannot write to it (write attempt fails); T3 uninstalling Immich leaves the OneMind library untouched; T4 ML is off after install |
| **PH-14** | Desktop folder sync client | `clients/desktop/**` | PH2-DESKTOP (parked), PH-3 | Parked with PH2-DESKTOP. T1 a watched folder on a Mac or Windows PC backs up through the same protocol |

**Order:** PH-0 → PH-1 → PH-2 and PH-3 in parallel → PH-5 and PH-4 → PH-8 → PH-6, PH-7, PH-9, PH-10 → PH-11, PH-13 → PH-12. PH-8 must be done before any phone is allowed to free space.

## 6. Decisions needed

| Id | Question | Recommendation |
|---|---|---|
| DN-1 | iOS background upload certificate (§4.7) | Public certificate when remote access exists, else box CA profile; never plain HTTP |
| DN-2 | Allow Immich face recognition on sold boxes | Off by default; decide after PH-0 T2 reads the model terms |
| DN-3 | Trash retention default | 30 days, and never purged before the next verified backup |
| DN-4 | Where ML workers run when the hub is small | On a stronger node through fabric capability labels; off when no node qualifies |
