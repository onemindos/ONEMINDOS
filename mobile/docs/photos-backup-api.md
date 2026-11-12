# Photo backup: interim API (phone ↔ OneMind Photos)

**Status:** interim. The phone app is built against this shape so that the backup client, its tests and the demo exist before the server (PH-3). It follows the photos study's proposal for contract **§12-p** (`docs/umbrel2/photos.md` §4.4 on the study branch). Nothing here is binding until §12-p merges into `sdk/contracts/poc-v0.md`. When it does, change `mobile/src/photos/protocol.ts` (every route and header lives there) and this page together.

**Why a built-in service and not Immich:** the photos study chose decision **C**: OneMind Photos is a first-party service on every box, and Immich is an optional Market app that attaches read-only to the same library. So the phone talks to OneMind Photos, not to Immich's API.

## Discovery

The phone finds Photos in the OneMind catalog (`GET /v1/apps`, contract §3): the app with `id: "photos"`, `installed: true` and a running `status`. The gateway serves the Photos API under the hub's own origin at `/v1/photos/...`, behind the same bearer token. If Photos is missing, not installed or not running, the Backup screen says which and sends nothing.

## Transport rules

- **HTTPS only** (study B3, decision DN-1). The client refuses an `http://` hub address before any request; the Backup screen says "Backup needs a secure connection". There is no plain-HTTP fallback for background uploads.
- The token is sent only to the hub's origin. An upload `Location` on another origin is refused.
- All times are RFC 3339 UTC; errors use the contract §3 envelope `{"error": "<code>", "message": "..."}`.

## Routes

| Method and path | Body / headers | Answer |
|---|---|---|
| `POST /v1/photos/sources` | `{"client_id", "name", "platform": "ios"\|"android"\|"other"}`; idempotent by `client_id` (a random id made once per install) | `{"id": "src_…", "client_id", "name", "platform"}` |
| `POST /v1/photos/sources/{id}/check` | `{"items": [{"client_key", "size", "hash"}]}`, at most 500 | `{"items": [{"client_key", "status": "have"\|"need"}]}` |
| `POST /v1/photos/uploads` | no body; headers below | `201`, `Location: /v1/photos/uploads/{upl}`, `Upload-Offset: 0` |
| `HEAD /v1/photos/uploads/{upl}` | — | `204`, `Upload-Offset`, `Upload-Complete: ?0\|?1`, `Upload-Length` |
| `PATCH /v1/photos/uploads/{upl}` | `Upload-Offset`, `Upload-Complete: ?0\|?1`, `Content-Type: application/partial-upload`, bytes | not last: `204` + `Upload-Offset`; last: `200` + `{"client_key", "hash", "deduped"}` |
| `GET /v1/photos/sources/{id}/coverage` | — | `{"total", "on_box", "backed_up", "verified", "as_of"}` |

**Upload creation headers:** `Upload-Draft-Interop-Version` (constant `UPLOAD_INTEROP_VERSION` in `protocol.ts`; UNVERIFIED against the server, checked in PH-3), `Upload-Complete: ?0`, `Upload-Length`, `OneMind-Source-Id`, `OneMind-Client-Key`, `OneMind-Content-Hash: sha256:<64 hex>`, `OneMind-File-Name` (percent-encoded UTF-8), optional `OneMind-Created-At`.

**Resumable uploads** follow the IETF HTTP "Resumable Uploads" draft (creation, offset retrieval with `HEAD`, append with `PATCH`). A `PATCH` whose `Upload-Offset` is not what the box holds gets `409` with the true `Upload-Offset`; the phone asks with `HEAD` and continues from there. A dropped connection keeps the bytes that arrived. An unknown or expired upload gets `404`/`410`, and the phone creates a new one.

## Identity and dedupe

- **`client_key`**: 64 hex, `SHA-256("onemind-photos-key/v1\n" + client_id + "\n" + platform asset id)`. Stable for one install; it reveals neither the asset id nor the device.
- **`hash`**: `sha256:` + the SHA-256 of the exact bytes (computed natively on the phone by `expo-file-system`). The box rehashes what it receives and refuses a mismatch (`409`). The box's own storage hash (BLAKE3 in the study) is its business; the wire uses SHA-256 because both phone platforms compute it natively.
- **`check` answers `have` only from this source's own receipts**: the same key with the same hash, or the same hash already received from this source under another key (a duplicate on the phone; the box records the new key without an upload). Bytes held only by another person's phone are never matched, so `check` is not a hash oracle (study B5). The box may still store one copy internally.
- **Receipts survive moves and are not satisfied by Trash** (study §1.3, PH-3 T2/T3): this is the server's rule; the phone just trusts `have`.

## Coverage (safe-to-free, B1)

`on_box` counts items the box received from this phone; `backed_up` counts those inside a box backup snapshot; `verified` counts those inside a snapshot that passed a restore check. The phone shows all three and offers no "free up space" yet. When it does (after PH-8), it will list only `verified` items.

## What the phone does

`mobile/src/photos/engine.ts`, one run:
1. Checks the rules (backup on, Wi-Fi only, charging only) and photo permission; if blocked, records why and stops.
2. Registers the source once.
3. Lists the selected albums (each item once, even when it is in several albums).
4. Hashes new or edited items, then asks `check` in batches of up to 500.
5. Uploads each `need` item in chunks (4 MiB by default), re-checking time and rules between chunks. Before a duplicate of something sent this run, it asks `check` again instead of uploading.
6. Reads coverage.

A run ends cleanly on a lost connection, a rule change, the OS ending background time, or a deadline. The next run asks `HEAD` and continues from the box's offset. The phone's ledger (a JSON file in the app's private folder) holds keys, hashes, open upload addresses and the last run, never bytes or the token.

## Mock

`mobile/src/photos/mockServer.ts` implements every route above in memory (receipts per source, offsets, hash check, injected drops). The tests run the real HTTP client and engine against it, and the demo ("Try the demo") uses it with a made-up library, so the demo never talks to a network.
