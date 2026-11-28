<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind Sync (F1): the record-sync protocol every OneMind app uses offline

**For:** builders of OneMind apps (box module, app kit, screens) · **Date:** 2026-11-26 · **Status:** spike 1 of D-032 ([ONEMIND-APPS.md](https://github.com/onemindos/ONEMINDOS/blob/docs/onemind-apps-architecture/docs/design/ONEMIND-APPS.md) §3, §3b), proposal with a working prototype. The founder decides whether it becomes the contract.
**Builds on:** D-029 (the gateway decides, NATS enforces and carries), D-027/D-028 (AI never actuates without a person), D-032 (every app complete and offline on web, Android and iOS).
**Code:** box `core/onemind_core/sync/`, `core/onemind_core/routers/appsync.py`, proof app `core/onemind_core/reminders/`; client kit `clients/sync/`; tests `core/tests/test_sync_reminders.py`, `clients/sync/__tests__/`, `clients/sync/e2e/`.

## 1. What it is, in one paragraph

Each device keeps its own copy of a person's items (a local store, SQLite on the phone) and a queue of changes it has not sent yet (the **outbox**). When the box is reachable the device **pushes** the outbox and then **pulls** what changed since its **cursor** (a bookmark in the box's change log). Every change carries an **idempotency key**, so a change sent twice is applied once. When two devices changed the same item, the box **keeps both** (the second becomes a *conflict copy*) instead of letting one silently overwrite the other. Files keep their own sync (`/v1/sync/changes`, chunks, Syncthing, Samba); content several people type into at once (Notes, Docs) will carry CRDT updates over this same feed later.

## 2. Transport: plain HTTPS and JSON

- Two routes per app, nothing else: `GET /v1/sync/<app>/changes` and `POST /v1/sync/<app>/push`. `<app>` is a fixed path segment registered by the app (today only `reminders`), not a free parameter: the app's record type is typed in `/openapi.json` (so in `@onemind/sdk`), and the switch-off gate can match the app's prefix.
- No websocket, no NATS on the phone (D-029: phones do not join NATS in 1.0). A "something changed, pull now" nudge can later ride `/v1/events` the way `sync.root_changed` does for files; it would carry no data.
- Because the protocol is only these two JSON calls, the transport can change later (§9) without touching any app.

## 3. Who may sync what

- **Auth is the normal gateway principal:** the person's bearer token or signed-in session, the same as every other route. No sync-specific credential.
- **Only a person syncs, and only their own items.** Each item belongs to the person who created it (`owner_id`); the feed is filtered by the caller, and an item id is scoped per person, so another person's id is never an oracle (pushing the same id just makes your own item). An agent gets 403 `permission_denied`, written to the audit log as `authz.denied`.
- **Route scope:** like the file-sync routes, no narrower scope covers sync yet, so a scoped token needs `*`. Consequence today: a child's narrow token cannot sync. A per-app scope (`reminders:read`, `reminders:write`) should come with the Reminders app.
- **A switched-off built-in answers 409** `stale_precondition` with `reason: app_disabled`, from `BuiltinGate` (`core/onemind_core/builtins.py`), before any sync code runs, because the app's descriptor owns `/v1/sync/<app>`. A caller the gateway cannot sign in gets 401, not 409. The client kit does not retry a 4xx (except 408 and 429) and keeps the outbox, so nothing is lost while the app is off.

## 4. The change log and the feed

The box keeps one append-only table for every app, `sync_changes`: `seq` (gateway-wide, increasing), `app`, `owner_id`, `item_id`, `version` (1, 2, 3... per item), `deleted`, `conflict_of`, `data`, `changed_at`. An item's current state is its newest row.

`GET /v1/sync/<app>/changes?cursor=<c>&limit=<n>` (limit 1 to 500, default 200) answers a **JSON array** of that person's changes after the cursor, oldest first:

```json
[{"cursor": "42", "item_id": "r1", "version": 3, "deleted": false, "conflict_of": null,
  "changed_at": "2026-11-11T22:00:00Z",
  "data": {"id": "r1", "title": "Buy milk", "due_at": "2026-11-12T09:00:00Z", "done": false, "updated_at": "2026-11-11T22:00:00Z"}}]
```

- **The cursor is monotonic and opaque:** keep the `cursor` of the last change you applied and send it back. No cursor means "from the start". When more changes wait, the answer has `Link: <...?cursor=..>; rel="next"` (the gateway's one paging shape, contract §12.1); an empty array means you are up to date. A device that crashes after applying changes but before saving the cursor gets them again: applying a change twice is harmless.
- **Tombstones:** a delete is a change with `deleted: true` and `data: null`. The device drops the item.
- **Every cached item carries its age.** The device records when it last read the feed to its end; an item's age is "now minus that time", shown as "updated 3 min ago" and, offline, as the age of what you see. `changed_at` says when the item itself last changed. An item the box has never confirmed (made offline) has no age and shows as "waiting to sync".

## 5. Push: idempotency keys and the conflict rule

`POST /v1/sync/<app>/push` with `{"ops": [...]}` (1 to 100). Each operation:

| Field | Meaning |
|---|---|
| `key` | Idempotency key, 8 to 80 of `A-Za-z0-9_.:-`. Made once, when the person makes the change, and reused on every retry. |
| `item_id` | Made by the device (a UUID), so items can be created offline. 1 to 64 of `A-Za-z0-9_-`, starting with a letter or digit (also a valid NATS subject token, §9). |
| `op` | `upsert` (with `data`, the app's record) or `delete` (no `data`). |
| `base_version` | The item version this device last saw; `null` for a new item. |

The box applies the operations in order, in one transaction (all or none), under one lock so cursors commit in order. Per operation:

1. **Seen key:** the key was applied before, so the box answers its first result again with `replayed: true` and changes nothing. The same key with a different operation is 409 `key_reused` and nothing in the push is applied; two operations with one key in a push are 422 `duplicate_key`.
2. **Base matches** (the item's current version, or `null` for an item that does not exist): applied; the version goes up by one; `status: applied`.
3. **Delete of an item that is gone or never existed:** applied, nothing written.
4. **Stale base, upsert:** **nothing is overwritten.** The data is stored as a new item, the **conflict copy**, with id `<item_id[:40]>-conflict-<12 hex of sha256(key)>` (fixed by the key, so a retry names the same copy), `version 1` and `conflict_of: <item_id>`. `status: conflict`; the result's `item_id` is the copy. Both copies reach every device through the feed; the person merges or deletes one.
5. **Stale base, delete:** dropped; the newer edit stays. `status: conflict`.

The answer is `{"results": [{"key", "status", "item_id", "version", "conflict_of", "replayed"}]}`. The route is on the OpenAPI lint's idempotency exemption list because every operation carries its own key (the same reasoning as `POST /v1/bridges/{bridge_id}/events`).

**Why "keep both":** last-writer-wins loses a person's work without telling them. A copy costs one extra row and one tap to tidy up. Field-level merging is a later refinement per app; CRDTs (Yjs or Automerge, licences to confirm) are for text several people edit.

## 6. AI and approvals

The sync routes are a person's own devices talking to the box; agents are refused and have no MCP tool over them (`surfaces/parity.py` lists them as `person`). An agent reaches Reminders through the app's REST API: read tools, plus request-only tools that a person approves (AI never actuates without human approval). An approved change is written by the gateway like any other change, so it appears in every device's feed.

## 7. The client kit (`clients/sync/`)

Plain TypeScript, no UI, no runtime dependency; the dashboard, the phone and the desktop import it.

- **Storage interface** `SyncStorage`: meta (cursor, last pull time), cached items, outbox. `MemoryStorage` for tests and the web; `SqliteStorage` takes an expo-sqlite database handle (`execAsync`, `runAsync`, `getFirstAsync`, `getAllAsync`, the expo-sqlite 58 names). expo-sqlite itself is added to `mobile/` by #1290; the tests run `SqliteStorage` on Node's own SQLite.
- **Outbox:** `save()` and `remove()` write the local copy and an outbox entry at once, with the key and the base fixed at that moment. An edit to an item whose entry has not left the device is folded into it (same key). Once an entry may have reached the box (`sent`), a later edit gets its own entry whose base is "after that entry": if that entry is applied the base becomes its new version; if it conflicted, the later edit keeps the old base and becomes a conflict copy too, so an offline edit never overwrites a newer one.
- **Loop:** `sync()` pushes (one entry per item per round, up to 100) and then pulls to the end of the feed. `syncWithBackoff()` retries network errors, 5xx, 408 and 429 with exponential backoff (1 s, 2 s, 4 s ... capped), never other 4xx.
- **Conflict copies** arrive through the feed like any item, with `conflictOf` set, so a screen can show "Conflict: kept both".

## 8. What the prototype does not do yet

- **Compaction and 410:** the log is never pruned and the first sync replays it all. Next: prune superseded rows after a retention window, answer 410 `cursor_expired` for an older cursor, and teach the kit to restart from no cursor on 410.
- **A box restored from backup** could hand out cursors that go backwards. Next: an epoch in the cursor (`<epoch>.<seq>`) and 410 on a mismatch.
- **More than one gateway process:** the push lock is per process. A second process needs `pg_advisory_xact_lock` (PostgreSQL) or a single writer.
- **Retention of idempotency receipts:** kept forever today; a window (for example 30 days) is enough because a device retries within that time.
- Per-app scopes (§3), a pull nudge on `/v1/events`, the Reminders REST API, `onemind reminders` CLI group and MCP read and request tools (D-032: API + CLI + MCP), and Reminders on the signed system apps list.

## 9. Later: the change log in JetStream

D-029 keeps NATS between machines; the change log can still be **kept in** JetStream on the hub without phones joining NATS:

- One stream, `ONEMIND_SYNC`, on subjects `onemind.sync.<app_id>.<owner_key>.<item_id>` (`owner_key`: an opaque hash of the person id, since a person id is not a subject token). `sync` would be a new kind in `sdk/schema/onemind.subjects.json` (a contract change; not registered by this spike).
- Each committed change is one message (the same JSON as a feed entry), published by the gateway with `Nats-Msg-Id = <app>:<seq>` so a re-publish after a crash is dropped by JetStream's duplicate window.
- `MaxMsgsPerSubject = 1` keeps only the newest state of each item, tombstones included: that is compaction for free, and the stream sequence becomes the cursor.
- The feed becomes an ordered consumer filtered to `onemind.sync.<app>.<owner_key>.>` that starts after the cursor; the gateway still checks the principal and serves the same HTTPS JSON. When the cursor's meaning changes, the gateway answers 410 once and devices resync from the start, so no app changes.
- Other OneMind machines (a second hub, a worker that indexes reminders) can then read the stream through their own NATS accounts, with the gateway deciding who may (D-029).
