<!-- SPDX-License-Identifier: Apache-2.0 -->
# Photos server: the box side of phone photo backup (PHOTOS-SRV-1)

**Date:** 2026-11-12 · Part of [the leap](../README.md) · **Branch:** `feat/photos-server` · **Serves:** UMB-PHOTO-3 (backup protocol server, incl. UMB-CLIENT-4), the receipt half of UMB-PHOTO-8 / UMB-CLIENT-5 (`in_verified_backup`) · **Builds on:** [`docs/umbrel2/photos.md`](../../umbrel2/photos.md) (the study, decision C), `mobile/docs/photos-backup-api.md` (the phone's interim protocol, branch `feat/mobile-photos`, PR #34), [PLUMBING.md](PLUMBING.md), [BACKUPS.md](BACKUPS.md), contract §12.8.

> **Explain it like I am the founder**
> Your phone could already back up photos, but nothing on the box was listening. Now the box receives them.
> Each photo arrives in pieces, so a dropped Wi-Fi connection only costs the piece in flight. Before the box tells the phone "I have it", it checks that the bytes are exactly the ones the phone sent (a fingerprint match) and forces them onto the disk.
> Each person gets their own photo folder. If two people in the house have the same photo, the disk keeps one copy, but neither of them can find out that the other has it.
> The phone also gets a third answer besides "on the box": "in a backup that was test-restored". Only that level will ever be allowed to free space on the phone.

## 1. Decision: built-in OneMind Photos, Immich stays a Market app

The photos study ([`docs/umbrel2/photos.md`](../../umbrel2/photos.md) §4.1) chose **C**: OneMind Photos is our own first-party service, and Immich (AGPL-3.0) is an optional Market app that may attach read-only to the same library (UMB-PHOTO-13). This change builds the built-in side. It writes no Immich adapter.

**Why built-in rather than Immich** (study §4.1, summarised):
- **One identity and one phone app.** Immich has its own login and its own phone app. The OneMind phone app already speaks this protocol with the box's bearer token.
- **Our safety rules.** "Safe to free up space" must mean "in a verified off-box backup" (B1). Immich has no notion of OneMind's backups or approvals, and its receipts cannot say this.
- **Licence and control.** We cannot change Immich (AGPL) without publishing our changes. Its default face models carry non-commercial terms (UNVERIFIED until UMB-PHOTO-0). Its release pace is outside our "deployments never fail" control.
- **Size.** Immich needs PostgreSQL, Valkey and an ML container. That is heavy for a Pi-class hub. This server adds no process and no dependency.

**Why it lives in the gateway for now.** The phone discovers Photos on the hub's own origin and calls `/v1/photos/...` with the same bearer token (`mobile/src/photos/discovery.ts`). A core feature module (PLUMBING §1) reuses the gateway's principals, clock, events and audit, and keeps its tables on the shared ledger database (SQLite or PostgreSQL, tested on both). It also adds no new port or process. The study's separate service (`cmd/onemind-photos`, UMB-PHOTO-1) remains the place for the catalog work that needs one: EXIF ingest, thumbnails and ML (UMB-PHOTO-2, -12). The wire protocol and the folder layout below do not change if the routes move there.

**Where this differs from the study, and why:**

| Study | Here | Why |
|---|---|---|
| BLAKE3 storage hash, SHA-256 on the wire | SHA-256 for both | Both phones compute SHA-256 natively and the box must verify it anyway; a second hash would read every file twice. BLAKE3 can be added later as a column if speed needs it |
| Catalog in its own `catalog.db` | Tables `photos_*` on the gateway database (feature `photos`, PLUMBING §3) | One database to back up and migrate; PostgreSQL works out of the box (BD-04) |
| `cmd/onemind-photos` service | `core/onemind_core/photos/` + `routers/photos.py` | See above; the protocol is unchanged when it moves |
| `check` from "the asking person's own receipts and assets" (§4.7) | Same | The phone's doc says "this source's receipts". The person-wide rule is the study's, is no oracle (it is the person's own data), and spares an iPad re-sending what the iPhone sent. **Mobile doc update needed** (§8) |

## 2. API (interim contract §12-p)

Every route needs a bearer token of a **person** with role `owner` or `adult`. Guests and agents get 403 (guests have no library, study §4.6; agents never upload, and their read tools are UMB-PHOTO-9). With Photos off (the default) every route answers 404. Errors use the §3 envelope.

| Method and path | Request | Answer |
|---|---|---|
| `POST /v1/photos/sources` | `{client_id, name, platform: ios\|android\|other}` | `201` new, `200` known (same person and `client_id`): `{id, client_id, name, platform}` |
| `POST /v1/photos/sources/{id}/check` | `{items: [{client_key, size, hash: "sha256:<hex>"}]}`, at most 500 | `{items: [{client_key, status: have\|need}]}` in order |
| `POST /v1/photos/uploads` | headers `Upload-Length`, `Upload-Complete: ?0`, `OneMind-Source-Id`, `OneMind-Client-Key`, `OneMind-Content-Hash`, `OneMind-File-Name` (percent-encoded), optional `OneMind-Created-At` | `201`, `Location: /v1/photos/uploads/upl_…`, `Upload-Offset`, `Upload-Limit: max-size=<n>`. If an unfinished upload exists for the same item, its address and current offset are returned |
| `HEAD /v1/photos/uploads/{id}` | – | `204`, `Upload-Offset` (bytes on disk), `Upload-Complete`, `Upload-Length`, `Upload-Limit`, `Cache-Control: no-store`; `410 expired` for a failed or idle upload |
| `PATCH /v1/photos/uploads/{id}` | `Upload-Offset`, `Upload-Complete: ?0\|?1`, body | not last: `204` + offsets; last: `200` `{client_key, hash, deduped}`. A wrong offset gives `409` with the true `Upload-Offset`. Repeating the last PATCH of a finished upload replays the receipt |
| `GET /v1/photos/sources/{id}/coverage` | – | `{total, on_box, backed_up, verified, as_of}` |
| `GET /v1/photos/sources/{id}/receipts?cursor=&limit=` | limit 1–500, default 50 | `{items: [{client_key, hash, received_at, level}], next_cursor}`, `level` ∈ `on_box`, `in_backup`, `in_verified_backup` (what "Free up space" will read) |

**Resumable uploads** follow the IETF draft `draft-ietf-httpbis-resumable-upload` (creation, offset retrieval, append, `application/partial-upload`). Read on 2026-11-12, the current revision is -15, whose Appendix B says "The current interop version is 10". The phone sends `Upload-Draft-Interop-Version: 7`, which the draft's change log places at revisions -04/-05 (UNVERIFIED mapping; the change log names bumps, not numbers). The headers and status codes this server uses (409 with `Upload-Offset` on a mismatch, `204` with `no-store` on HEAD) are the same in both. The server accepts the header and does not branch on it.

## 3. Identity, dedupe and the hash oracle

- **Blob:** a set of bytes, keyed by SHA-256, stored once (`photos_blobs`).
- **Asset:** one person's photo, unique per `(owner, blob)` (`photos_assets`). A person never holds two copies of the same bytes.
- **Receipt:** "this phone's item `(source, client_key)` is these bytes, in this person's asset" (`photos_receipts`).
- **`check` says `have`** only when the asking person has an asset with that hash and size, **and** both the stored copy and the person's own library file exist with that size. A receipt row alone is never proof: a deleted or damaged copy turns the answer back into `need`, the phone re-sends, and the upload heals both. The person's file is a hard link, so healing only the stored copy (a new inode) would leave their file damaged; it is replaced through a temporary name and a rename. A heal also resets the photo's backup level (§5), because older snapshots hold the damaged bytes. A hit without a receipt (a duplicate on the phone, or bytes from the same person's other phone) records the receipt without an upload.
- **No hash oracle.** Another person's bytes never make `check` say `have`. The second person uploads every byte, the box verifies them, and only then, if the bytes are already on disk, links the person's file to the existing copy instead of keeping a second one. Their receipt (`deduped: false`) is the same as if nobody else had the photo. `deduped: true` means only "you already had this".
- **Isolation:** every query takes the caller's own id. Another person's sources and uploads answer 404, never 403, so their existence is not revealed.

## 4. Storage and durability

```
<ONEMIND_PHOTOS_DIR>/staging/<upload id>                                     unfinished uploads
<ONEMIND_PHOTOS_DIR>/library/.shared-store/<aa>/<sha256>                     each set of bytes, once
<ONEMIND_PHOTOS_DIR>/library/<person>/<phone>-<id6>/<YYYY>/<MM>/<file name>   hard link to the stored copy
```

Originals keep their own names as plain files, so the photos survive without OneMind (study §4.3). A filesystem that cannot hard-link gets a copy instead. Names are cleaned to a single path segment (NFC, no separators or control characters, at most 180 bytes) and never overwrite: `IMG_1 (2).HEIC`. The month comes from the phone's creation time until ingest reads EXIF (UMB-PHOTO-2).

**Order of durable steps.** A receipt exists only after all of them:
1. Each PATCH streams to `staging/<id>` under an exclusive `flock` (a second writer gets 409) and is **fsynced before** its `Upload-Offset` is acknowledged. The offset is the file's length on disk, so a crash can only make it smaller, never claim bytes that are not there.
   Note: each PATCH body is at most 256 KiB (the gateway body cap, contract 12.1; larger gets 413), so a file goes up in many parts.
2. On the last part the box computes SHA-256: from the hash state it kept in memory, or by re-reading the file after a restart. It compares this with `OneMind-Content-Hash`. A mismatch deletes the bytes, fails the upload (410 afterwards), publishes `photos.upload.rejected` and gives no receipt.
3. The verified file is hard-linked into the shared store, and the person's library entry is linked from it. **Each directory is fsynced.** Only then does the box read the clock for the asset's time, which the backup levels use (§5).
4. One database transaction records the blob, asset, receipt and the upload's receipt (for replay). Then the box answers 200.

| Failure | What happens |
|---|---|
| Connection drops mid-PATCH | The bytes that arrived stay; HEAD reports them; the phone continues from there |
| Body stalls longer than `ONEMIND_PHOTOS_READ_TIMEOUT_S` | Cut off with 409 and the true offset, and the lock is released |
| Box restarts mid-upload | Staged bytes stay; the final hash is computed from disk |
| Last response lost | HEAD says `Upload-Complete: ?1`; the repeated last PATCH replays the receipt |
| Crash between linking files and the database commit | Nothing is acknowledged; the phone re-sends. The earlier library link stays as an orphan (UMB-PHOTO-8 reconciliation, §8) |
| Disk short of space | Refused at creation: the new length plus all unfinished uploads plus `ONEMIND_PHOTOS_RESERVE_BYTES` must fit |

## 5. Receipt levels: `on_box`, `in_backup`, `in_verified_backup`

The levels come from the backup coordinator's events (contract §12.8 v1 types), received in-process through `gw.events.subscribe`:

| Event | Payload Photos reads | Effect |
|---|---|---|
| `backup.run.finished` | `result: "succeeded"`, `snapshot_id`, `target_id`, `started_at` (RFC 3339), `units` containing `"photos"`, optional `finished_at` | records the snapshot |
| `backup.verify.finished` | `result: "passed"`, `snapshot_id`, `target_id`, `unit: "photos"` (or `units`) | marks that snapshot verified |
| `backup.snapshot.removed` (**proposed**, not in §12.8 yet) | `snapshot_id` or `snapshot_ids`, `target_id` (without it, the ids match on every target) | the snapshot no longer counts |

**Rule:** a photo is `in_backup` when it was on the box before the newest kept snapshot of the `photos` unit **started**, where "on the box" is the time read after its library file was linked and fsynced (or healed), and `in_verified_backup` when it was on the box before the newest kept **verified** snapshot started. Library files are never deleted yet, so a snapshot holds everything that existed when it started. Other events, failed runs and runs without the `photos` unit change nothing. Coverage counts per phone: `total` and `on_box` are the phone's receipts (equal until Trash exists), `backed_up` and `verified` apply the rule.

**Asks of the backup stream** (CORE-BACKUP-8, gateway coordinator K3): back up `ONEMIND_PHOTOS_DIR` together with the gateway database as unit `photos`; publish the two §12.8 events with the fields above through `gw.events.publish_event`; add `backup.snapshot.removed` (contract owner) so a deleted or pruned snapshot stops counting. Without these events every photo stays `on_box`, which is the safe default.

## 6. Settings (`@config_section("photos")`)

| Variable | Default | Meaning |
|---|---|---|
| `ONEMIND_PHOTOS_ENABLED` | `0` | `1` turns the routes on |
| `ONEMIND_PHOTOS_DIR` | – (required when enabled) | library root, on Retain storage (`onemind-local`, CORE-BACKUP-1) |
| `ONEMIND_PHOTOS_MAX_UPLOAD_BYTES` | 64 GiB | largest file; sent as `Upload-Limit` |
| `ONEMIND_PHOTOS_UPLOAD_TTL_S` | 7 days | an unfinished upload idle this long expires and is swept |
| `ONEMIND_PHOTOS_READ_TIMEOUT_S` | 60 | a PATCH body that stalls this long is cut off |
| `ONEMIND_PHOTOS_RESERVE_BYTES` | 1 GiB | free space kept back |
| `ONEMIND_PHOTOS_MAX_OPEN_UPLOADS` | 64 | unfinished uploads per phone |

On a developer install (`deploy/install.sh`), add `ONEMIND_PHOTOS_ENABLED=1` and `ONEMIND_PHOTOS_DIR=/var/lib/onemind/photos` to `/etc/onemind/gateway.env`. The image's `onemind-core` is still a stand-in pod, so the image needs no change yet.

## 7. Tests

| Where | What | Run |
|---|---|---|
| `core/tests/test_photos.py` (38) | Happy path; replay and the race with a finishing request; offsets, overflow, short last part; three drops (raw ASGI disconnects) then one stored copy; stall; restart (disk rehash); flock busy; expiry and sweep; digest mismatch; duplicates; same person's second phone; no oracle across people with one inode; concurrent identical uploads; "a receipt alone is no proof"; a damaged copy healed in the person's own file and its level reset; a deleted library file asked for again; edited photo; validation; receipt levels from events; a snapshot that starts while a file is stored does not count; a removal without a target; paging; limits; names | `make -C core test`, and with `ONEMIND_TEST_DB_URL=postgresql://…` |
| `test/photos/mobile-e2e.test.ts` + `run-mobile-e2e.sh` | The phone's real `runBackup` engine, `HttpPhotosApi` and SHA-256 code against a live gateway. A library with a duplicate, a second run sending nothing, a half-delivered chunk resumed with every byte sent once, and a second person asked for every byte; then the box's files are counted | `test/photos/run-mobile-e2e.sh <mobile dir>` (needs `feat/mobile-photos`; skips without it) |

Result on 2026-11-12 after review: the full core suite passes on SQLite (342) and the photos tests on PostgreSQL 17 (38) on macOS. Before review: the full core suite passed on SQLite and PostgreSQL 17 on macOS (338), and on SQLite on Debian 13 arm64 in a Lima VM (Linux 6.12; 337, run before the race test was added; the photos tests on both tmpfs and ext4). The end-to-end run passes against SQLite and PostgreSQL: 4 jest tests, and on the box 6 stored copies, 6 + 1 library files and an empty staging folder.

## 8. Not done here, and open items

| Item | Owner | Note |
|---|---|---|
| **Discovery:** the phone requires an app `photos` in `GET /v1/apps` that is installed and running. The catalog has no such entry | app pipeline (UMB-PHOTO-1 `apps/photos/` first-party manifest) or mobile | Until then the phone shows "not in catalog" on a real box; the demo and these tests do not use discovery |
| **HTTPS:** the gateway speaks HTTP; the phone refuses it | networking (CORE-NET-8 edge, box CA), F-48 / DN-1 | Photos behind the edge at the hub origin |
| Interop version 7 vs the draft's 10 | mobile (`UPLOAD_INTEROP_VERSION`) | Server accepts both; re-read the draft before bumping |
| Phone doc says `check` uses this source's receipts only | mobile (`photos-backup-api.md`) | Server uses the person's photos (study §4.7, §1 above) |
| Device principals and source-scoped upload tokens | CORE-MOBILE-2, UMB-CLIENT-2 | Today a phone uses its person's token |
| Trash, and "Trash never satisfies a receipt" | UMB-PHOTO-5 | `on_box` equals `total` until Trash exists |
| Orphan library links after a crash before commit; weekly rehash (`photos_blobs.verified_at`); integrity alerts | UMB-PHOTO-8 | |
| `backup.snapshot.removed` event; `photos` backup unit | contract owner, CORE-BACKUP-8 | §5 |
| EXIF dates, thumbnails, kinds | UMB-PHOTO-2 | Months use the phone's creation time |
| Encryption at rest | CORE-SEC-5 (LUKS2) | Photos are not encrypted on disk until then |
| CLI (`onemind photos …`), MCP tools, dashboard pages | UMB-PHOTO-10, -9, -5 | |

No new dependencies: the server uses the Python standard library (`hashlib`, `fcntl`, `os`) and the gateway's existing FastAPI and SQLAlchemy. Nothing from umbrelOS was copied (PolyForm Noncommercial; the study describes it only).
