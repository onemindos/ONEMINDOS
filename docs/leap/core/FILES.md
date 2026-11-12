<!-- SPDX-License-Identifier: Apache-2.0 -->
# FILES: the core file service and its API

**Date:** 2026-11-12 · Part of [the leap](../README.md) · **Branch:** `feat/files` · **Design:** `docs/umbrel2/files-backups.md` §4 (on `main`) · **Built on:** contract §12 (`sdk/contracts/poc-v0.md`) and [PLUMBING.md](PLUMBING.md) · **Serves:** FILES-2, the gateway half of FILES-1 and FILES-6. The dashboard Files page (FILES-4) builds against this page.

> **Explain it like I am the founder**
> Every person in the household gets a private folder ("My files"), and the household gets one Shared folder. The box keeps them under `/data/onemind/files`. You can browse, preview, download (and resume a download), upload big files that survive a dropped connection, rename, move and delete. Deleted things go to a Trash for 30 days. The owner can set how much space each person may use.
> Apps and AI agents cannot see any of it by default. An agent can *ask* for one folder, read-only or read-write; nothing changes until the owner approves. Every change, every approval and every file an agent reads is written to the audit log.

## 1. Spaces and who may use them

A location is always a **root** plus a **path** inside it. Roots are ids, never host paths: `home:<person_id>` and `shared`. Paths look like `/Photos/2026/IMG_1.jpg`; `/` (or empty) is the root itself.

| Role (§12.6) | Own Home | Shared | Others' Homes |
|---|---|---|---|
| `owner` | read-write | read-write | none |
| `adult` | read-write | read-write | none |
| `child` | read-write | read-only | none |
| `guest` | none (no Home) | read-only | none |
| unknown role | none | none | none |
| agent | only inside approved grants | only inside approved grants | only inside approved grants (see §5) |

Until the identity stream merges, people are the `kind: person` principals of the tokens file and `person_id` is the principal id (so the example owner's Home is `home:owner`). The owner does **not** read other people's Homes through FILES.

On disk: `<ONEMIND_FILES_ROOT>/home/<dir>/`, `<root>/shared/`, and `<root>/.system/{trash,uploads}/` (never inside a space). `<dir>` is the person id when it is a plain lower-case name, else a hash of it.

## 2. Endpoints

All need a bearer token (§3). Lists return a JSON array with `?limit=` (default 100, max 500) and `?cursor=`; when more remain, the response has `Link: <…>; rel="next"` (§12.1). Times are RFC 3339 UTC.

| Method and path | Who | Body or query | Returns |
|---|---|---|---|
| `GET /v1/files/roots` | any | – | `[{root, kind: home\|shared\|grant, name, path, access: r\|rw, writable, used_bytes, quota_bytes, free_bytes, grant_id?}]`. Agents see one entry per grant |
| `GET /v1/files/list` | read access | `root, path, limit, cursor` | `[{name, path, type: file\|dir\|symlink\|other, size, mtime, mime?}]`, folders first; names that are not valid UTF-8 (written by something other than FILES) are left out |
| `GET /v1/files/stat` | read access | `root, path` | one entry plus `root`, `access`, `versions_available` (false until Rewind, FILES-7) |
| `GET /v1/files/preview` | read access | `root, path` | `{mime, kind: image\|video\|audio\|pdf\|text\|other, size, inline_safe, image?: {width, height}, text?: {excerpt, truncated}}`. No thumbnails yet (FILES-3) |
| `GET /v1/files/download` | read access | `root, path, inline?` | the bytes. `Range: bytes=a-b`, `a-` or `-n` → `206` with `Content-Range`; `If-Range` with the `ETag`; unsatisfiable → `416`. Always `nosniff` and `CSP: sandbox`; `inline=true` is honoured only for safe types (never SVG or HTML) |
| `POST /v1/files/ops` | write access | `{op: "mkdir", root, path}` | the new entry |
| | | `{op: "move", root, path, to_root?, to_path}` | the entry at its new place; never overwrites (`409 exists`) |
| | | `{op: "rename", root, path, name}` | the renamed entry |
| | | `{op: "trash", root, path}` | the trash item |
| | | `{op: "restore_trash", trash_id, to_root?, to_path?}` | the restored entry; `409 exists` if something is in the way |
| `GET /v1/files/trash` | person | `trash=home\|shared` | `[{id, trash, root, path, name, type, size, trashed_at, trashed_by, purge_at}]`. The `shared` trash is visible to owner and adults |
| `POST /v1/files/trash/empty` | person with that trash | `{trash?, reason?, expires_at?, approve?}` | `202`, a request (§4) |
| `GET /v1/files/quotas` | owner | – | `[{person_id, root, limit_bytes, used_bytes}]`, plus the Shared row |
| `PUT /v1/files/quotas/{person_id}` | owner (direct write) | `{limit_bytes: int\|null}` | the row; `null` = no limit |
| `POST /v1/files/grants` | owner; an agent for itself | `{subject: {kind: app\|agent, id}, root, path, access: r\|rw, slot?, reason?, expires_at?, approve?}` | `202`, a request (§4) |
| `GET /v1/files/grants` | owner all; agent own; a person those on their Home | `include_revoked?` | `[{id, subject, slot, root, path, access, request_id, approved_by, created_at, revoked_at, revoked_by}]` |
| `DELETE /v1/files/grants/{id}` | owner, the Home's person, or the agent itself | – | the revoked grant (removing power is a direct write, §12.1) |
| `GET /v1/files/requests`, `GET /v1/files/requests/{id}` | owner all; others own | `state?` | requests (§4) |
| `POST /v1/files/requests/{id}/approve` | owner | `{plan_sha256?, webauthn?}` (§12.4) | the request, now `succeeded` or `failed` |
| `POST /v1/files/requests/{id}/deny` | owner | `{reason?}` | the request, `cancelled` with `deny_reason` |
| `POST /v1/files/requests/{id}/cancel` | the requester | – | the request, `cancelled` |
| `OPTIONS`, `POST /v1/files/uploads`; `HEAD`, `GET`, `PATCH`, `DELETE /v1/files/uploads/{id}` | write access | tus, §3 | |

## 3. Uploads (tus 1.0.0)

Any tus client works (tus-js-client in the browser and React Native, MIT). Extensions: `creation`, `termination`, `checksum` (sha256), `expiration`. Every request sends `Tus-Resumable: 1.0.0` (else `412`).

1. **Create.** `POST /v1/files/uploads` with `Upload-Length` and `Upload-Metadata` (tus base64 pairs): `root`, `path` (the destination folder), `filename`, optional `sha256` (hex of the whole file) and `overwrite` (`1`). Instead of `sha256` metadata a client may send RFC 9530 `Repr-Digest: sha-256=:<base64>:`. The gateway checks write access, the name, that nothing has that name (unless `overwrite`), the quota (the full length is reserved now) and free space. → `201`, `Location: /v1/files/uploads/upl_…`, `Upload-Offset: 0`, `Upload-Expires` (24 h).
2. **Send.** `PATCH <Location>` with `Content-Type: application/offset+octet-stream`, `Upload-Offset` (must equal the server's, else `409 offset_mismatch`) and optionally `Upload-Checksum: sha256 <base64 of this chunk's digest>`. A chunk that fails its checksum is discarded: `460`, offset unchanged. A chunk is at most `ONEMIND_FILES_CHUNK_MAX_BYTES` (64 MiB). → `204` with the new `Upload-Offset`.
3. **Resume.** After a dropped connection or a gateway restart: `HEAD <Location>` → `Upload-Offset`; continue from there.
4. **Finish.** The PATCH that delivers the last byte also checks the whole file's sha256 against the declared one and the caller's write access (a revoked grant stops it), then moves the file into place in one rename. Mismatch → `409 digest_mismatch` and the upload is deleted. Success → `204` with `OneMind-File-Sha256`. With `overwrite`, the old file goes to the trash first, so it can be restored.
5. **Cancel.** `DELETE <Location>` → `204`. Unfinished uploads expire after 24 h.

Why tus and not the IETF resumable-upload draft: tus is stable and has maintained permissive clients for every platform we ship; the draft still changes. The digest headers already follow the IETF style where they overlap.

## 4. Requests that need an owner approval

Changing who can reach a folder (`files.grant.create`, risk `sensitive`) and deleting a trash for good (`files.trash.empty`, risk `destructive`) are requests, never direct writes. They follow §12.1 and §12.3:

```json
{"id": "frq_01J…", "type": "files.grant.create", "risk": "sensitive", "state": "awaiting_approval",
 "params": {"subject": {"kind": "agent", "id": "hermes"}, "root": "shared", "path": "/Media", "access": "r", "slot": null},
 "plan": {"summary": "agent hermes gets read-only access to shared:/Media", "…": "…"},
 "reason": "index my music", "requested_by": {"id": "hermes", "kind": "agent"},
 "approved_by": null, "approved_via": null, "approval": null, "deny_reason": null, "result": null,
 "plan_sha256": "sha256:…", "expires_at": "…", "created_at": "…", "updated_at": "…"}
```

- States: `awaiting_approval` → `succeeded` (with `result`: `{grant_id}` or `{items, bytes}`) or `failed`; `cancelled` (denied or withdrawn) and `expired` (24 h default, 7 days at most).
- `202` with `Location`; `Idempotency-Key` header: same key and body replays (`OneMind-Idempotent-Replay: true`), a different body is `409 idempotency_mismatch`.
- `approve: true` is the owner shortcut (create and approve at once); from anyone else it is `403` and nothing is filed.
- Non-owners may have at most 10 requests waiting: the 11th is `429 rate_limited`, reason `too_many_pending`.
- Only an owner approves; agents never do. A grant into `home:<X>` can be approved only by `X` (so today only grants into Shared or the owner's own Home can become active). The folder must still exist at approval, else `409 stale_precondition` and the request keeps waiting. An owner's request checks the folder at once (`404`); an agent's request is checked only at approval, so filing one reveals nothing about folders the agent cannot read.
- `plan_sha256` is the sha256 of the canonical `{type, params, plan}`. An approve body whose `plan_sha256` differs is `409 stale_precondition`, reason `plan_changed`.
- Approval guards other features register (passkey step-up, F-2) run before the change is applied, with `context.ApprovalGuard`'s arguments: the principal, the request id, the approve body and the HTTP request. For the owner shortcut they run before anything is filed, so a refused step-up leaves no request behind.

**Apps.** An app reaches files only through an approved `subject.kind: app` grant. `FilesService.app_mounts(app_id)` returns `[{grant_id, slot, host_path, read_only}]` for the executor to mount (hook to be wired by the sandbox owner, §7).

## 5. Agents

An agent sees only its grants: `GET /v1/files/roots` lists them, and list, stat, preview and download work inside them. A read-write grant also allows uploads, mkdir, move, rename and trash inside it; the granted folder itself is like a space root, so the agent cannot move, rename or trash it (`403`, `no_grant`). Every agent read is audited (`files.read` with op, root, path and size). An agent may revoke its own grant.

## 6. Errors

The §12.2 envelope `{error, message, reason?}`. Branch on `error`; `reason` refines it.

| HTTP | `error` | Common `reason` |
|---|---|---|
| 403 | `permission_denied` | `role`, `no_grant`, `symlink`, `not_self`, `not_home_owner` |
| 404 | `not_found` | `upload_expired`, `upload_terminated`, `upload_failed` |
| 409 | `conflict` | `exists`, `into_itself`, `space_root`, `not_a_file`, `not_a_folder`, `offset_mismatch`, `upload_busy`, `digest_mismatch`, `idempotency_mismatch` |
| 409 | `stale_precondition`, `expired` | `plan_changed` |
| 412 | `conflict` | `tus_version` |
| 413 | `payload_too_large` | `quota_exceeded`, `insufficient_space`, `upload_too_large`, `chunk_too_large` |
| 415 | `conflict` | `content_type` |
| 416 | `conflict` | `range` (with `Content-Range: bytes */size`) |
| 422 | `conflict` | `invalid_path`, `invalid_root`, `invalid_metadata`, `invalid_digest`, `invalid_cursor` |
| 429 | `rate_limited` | `too_many_pending` |
| 460 | `conflict` | `checksum_mismatch` (tus) |
| 503 | `unavailable` | `storage_unavailable` |

## 7. Events (audit log, NATS `onemind.event.files.*`, in-process subscribers)

`files.folder.created`, `files.moved`, `files.renamed`, `files.trashed`, `files.restored`, `files.purged` (reason `retention` or `emptied`), `files.upload.created|completed|failed|terminated|expired`, `files.quota.set`, `files.request.created|approved|denied|cancelled|expired|failed`, `files.grant.created|revoked`, `files.trash.emptied`, `files.read` (agents only). Payloads carry roots, paths, sizes and ids, never file contents. Denials are `authz.denied`.

## 8. Settings (`ONEMIND_FILES_*`)

| Variable | Default | Meaning |
|---|---|---|
| `ROOT` | `/data/onemind/files` | where the spaces live (absolute) |
| `DEFAULT_QUOTA_BYTES` | `0` (none) | per-person limit when the owner set none |
| `SHARED_QUOTA_BYTES` | `0` (none) | limit for Shared |
| `MIN_FREE_BYTES` | 256 MiB | free disk an upload or move must leave |
| `TRASH_RETENTION_DAYS` | `30` | then items are purged |
| `UPLOAD_MAX_BYTES` | 64 GiB | largest upload |
| `CHUNK_MAX_BYTES` | 64 MiB | largest PATCH body |
| `UPLOAD_EXPIRY_HOURS` | `24` | unfinished uploads expire |
| `PREVIEW_TEXT_BYTES` | 64 KiB | text excerpt size |

## 9. Choices made here, and what is left

Choices (each can be changed in a follow-up; recorded so nobody builds against a guess):

- **Requests are feature-owned, action-shaped records** (`files_requests`), not rows of `/v1/actions`: `actions.py` only knows app types today and is a hotspot. When the §12.5 registry becomes generic, `files.grant.create` and `files.trash.empty` move onto it with the same fields.
- **Bytes pass through the gateway** for now. The design moves them to a node file server in `onemindd` with short-lived file tokens (FILES-1 Go part); the API above stays the same, `download` and `uploads` would then answer with a redirect to the node.
- **`child` reads Shared but does not write it; `guest` has no Home.** §12.6 gives these roles no file rules; these are the least-privilege reading.
- **A grant into another person's Home** waits for that person's consent flow (identity stream); the owner cannot approve it.
- Data-plane writes by a person inside their own spaces are direct, audited writes (decision D-F1 recommendation).

Left for other streams or later epics: the Files page (FILES-4, dashboard stream), thumbnails and search (FILES-3), sharing to people and links (`files.share.*`), copy, the executor mount hook (CORE-SANDBOX owner), MCP tools `files_list`/`files_read`/`files_request_access` (DEV-MCP owner), Rewind (FILES-7), usage computed from an index instead of a walk (FILES-3), and a contract PR "12-files" that makes these paths binding.

## 10. Tests

`core/tests/test_files_*.py`: roles, privacy of Homes, every op, ranges, symlink refusal, a 4,000-path fuzz of the confined walk, tus resume/checksum/digest/overwrite/expiry, quotas, trash retention, grants (request, approve, deny, cancel, expiry, idempotency, pending cap, stale folder, revoke during an upload) and the audit trail. Run `make -C core test`, and the same with `ONEMIND_TEST_DB_URL=postgresql://…`.
