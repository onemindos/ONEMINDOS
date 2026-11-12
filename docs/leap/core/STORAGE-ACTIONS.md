<!-- SPDX-License-Identifier: Apache-2.0 -->
# Storage actions: mirrors as approved, journaled operations, and LUKS2 members

**Date:** 2026-11-12 · Part of [the leap](../README.md) · **Branch:** `feat/storage-actions` · **Epics:** STORAGE-ACT-1, STORAGE-LUKS-1; UMB-STOR-2, -4, -5 and the member side of CORE-SEC-5 (H-11) · **Design it implements:** [`docs/umbrel2/storage.md`](../../umbrel2/storage.md) §4.3–§4.10 · **Image part:** [STORAGE-ACT-os.patch.md](STORAGE-ACT-os.patch.md) · **Evidence:** [`research-output/evidence/lab/storage-actions/`](../../../research-output/evidence/lab/storage-actions/README.md)

> **Explain it like I am the founder**
> Your box can now protect its data on two or more disks, and change that later, without anyone typing disk commands. Plug in a disk and ask (in the dashboard, or through an agent). OneMind shows exactly what it will do: which disk it will erase, by model and the last four characters of its serial number. Only you can approve. Then it runs the steps one at a time and writes each step down before and after. If the power goes out halfway, the box finishes the job (or undoes the half-done part) when it comes back. You can turn one disk into a mirror, add a disk, swap a failing disk, take a disk out, and repair after a disk was missing. Every disk is encrypted. One recovery key, shown to you once, opens all of them; on boxes with a TPM chip you never have to type it. A **mirror** (RAID 1) keeps two copies of everything on different disks. A **journal** is a step-by-step record kept on disk so work can resume. **LUKS2** is Linux's disk encryption format, and a **keyslot** is one of the keys that can open it.

## 1. What exists now

| Piece | Path | What it does |
|---|---|---|
| Plans | `internal/storage/plan.go`, `plan_ops.go` | `create`/`add` (PlanProtect), `replace`, `remove`, `repair`, each a list of exact commands plus the checks they passed, sealed by `plan_sha256`. Steps carry an `id` and a `phase` |
| LUKS2 | `internal/storage/luks.go` | First-boot format (recovery key, set key, TPM2), header clone for new members, the OneMind token, recovery-key generation |
| Operation engine | `internal/storage/ops/engine.go`, `resolve.go`, `journal.go` | Runs one plan at a time from a durable journal; resumes or rolls back after a power cut; re-finds disks the kernel renamed |
| Boot assembly | `internal/storage/ops/assemble.go` | Unlocks the current members (TPM2, else the recovery key once), mounts normal, degraded or recovery mode |
| Node service | `cmd/onemindd/storage.go`: `onemindd storage serve`, `init`, `assemble` | Local Unix-socket API (`server.go`); its own privileged unit |
| Gateway | `core/onemind_core/storage.py`, `routers/storage.py`, hook in `actions.py` | Storage action types, plans for the approval card, operation tracking, health and state events |

## 2. How a disk change happens

1. **Request.** `POST /v1/storage/actions {type, params}`, from an owner or an agent (remove: owner only). The gateway asks the node to render the plan from a fresh disk inventory. A blocked plan (system disk, a disk with data on it, no headroom, too small, …) is refused with the failed checks. Otherwise the action is filed (`awaiting_approval`) and the plan is stored in `storage_operations` for the approval card.
2. **Approve.** `POST /v1/actions/{id}/approve` (owner only; agents get 403). The gateway renders the plan again. A different `plan_sha256` (another disk on that cable, a member that changed) is `409 stale_precondition`, and the action stays pending.
3. **Dispatch.** The gateway sends `{kind, params, plan_sha256, action_id}`, never commands. The node renders the plan a third time and starts only if the hash matches.
4. **Run.** The engine journals each step (`pending → running → done | skipped | failed`) in `/data/onemind/storage/ops/op-<id>.json`, written as a temp file, fsynced, renamed, and the folder fsynced.
5. **Close.** The gateway's poller reads the journal. It ends the action `succeeded` or `failed` (rolled back, needs attention, never started) and publishes `storage.operation.finished`.

## 3. Interfaces (proposed for contract §12 by UMB-STOR-0)

A feature PR does not edit the contract (WORKSTREAMS §4). These names are what the code serves today; the UMB-STOR-0 contract PR adopts or renames them.

**Action types** (§12.5 rows to add)

| Type | Params | Risk | Requested by | Runs on |
|---|---|---|---|---|
| `storage.mirror.create` | `{device, node_id?}` (one disk → mirror) | destructive | O, A | J (local socket in v0) |
| `storage.mirror.add` | `{device, node_id?}` (n → n+1; raid1c3 metadata at three) | destructive | O, A | J |
| `storage.mirror.replace` | `{member, device, wipe?, node_id?}` (`member`: devid, device, disk or `missing`) | destructive | O, A | J |
| `storage.mirror.remove` | `{member, unprotect?, wipe?, node_id?}` | destructive | O | J |
| `storage.mirror.repair` | `{node_id?}` (scrub, soft-convert, re-stamp tokens, clear the marker) | write | O, A | J |

**Routes**

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/storage` | any principal | `{node_id, enabled, available, state, encrypted, generation, needs_scrub, reasons, repair, profiles, members[{devid, missing, size_bytes, allocated_bytes, errors}], active_operation, recovery_key_pending, tpm2}`; no disk identities |
| `GET /v1/storage/devices` | owner | disks with role, model, full serial, health |
| `POST /v1/storage/plans` | requesters | `{type, risk, plan, plan_sha256}`; nothing filed |
| `POST /v1/storage/actions` | requesters (remove: owner) | `202 {action, plan, plan_sha256, risk, …}` + `Location`; `Idempotency-Key` header or body field; replay `200` |
| `GET /v1/storage/operations/{action_id}` | requesters | the stored plan, state, progress and, while it runs, the node's journal step by step |
| `POST /v1/storage/recovery-key` | owner | `{one_time: {recovery_key}}` once, `Cache-Control: no-store`; then `404` |

**Node socket** (`/run/onemind/storage.sock`, `internal/storage/ops/server.go`): `GET /v1/status`, `POST /v1/plans`, `POST /v1/operations`, `GET /v1/operations[/{id}]`, `POST /v1/recovery-key/take`.

**Settings** (`@config_section("storage")`): `ONEMIND_STORAGE_ENABLED` (off by default), `ONEMIND_STORAGE_SOCKET`, `ONEMIND_STORAGE_POLL_S` (60), `ONEMIND_STORAGE_TIMEOUT_S` (15).

## 4. The engine: what happens after a power cut

Every step has a **phase**. That decides what a failure does:

| Phase | Steps | On failure | After a power cut |
|---|---|---|---|
| `prepare` | wipe, partition, settle, header copy, LUKS UUID, open, new member's token | **roll back**: close the mapping, erase the copied keyslots, wipe and blank the target | restart the whole prepare phase on the target (the header copy in `/run` is gone; a partition cannot be made twice). The target is not in the set yet, so this is safe |
| `join` | other members' tokens, `device add` | **roll back**: `btrfs device remove` (nothing moved yet), then as above | `device add` is skipped when the disk is already a member |
| `commit` | balance, replace, resize, device remove, old-member cleanup | **stop forward-only** (`failed`): the set stays usable and the steps are restartable. Exception: a replace that failed before the new disk took the devid rolls back | balance: wait while the kernel runs the balance it resumed at mount, resume a paused one, then re-run the soft convert (a no-op when done). replace: wait on `/sys/fs/btrfs/<fsid>/exclusive_operation`; done when the new disk holds the devid. device remove: skipped when the devid is gone |
| `verify` | profile check, stats reset, marker clear | `failed` | re-run |

Other rules:
- **One operation at a time** (`409 busy`). The journal folder is `flock`ed, so a second service cannot run on the same set.
- **Disks are found again by identity, not by name.** Every device path in a plan gets a key: the GPT partition id the plan wrote for new members, the existing partition ids, and stable disk ids (WWN, serial). After a reboot that swapped `vdb` and `vdc`, the remaining steps are rewritten (`relocated` in the journal). A target with no partition yet is accepted only at its old path, blank, with the same size and model. A target that is gone means rollback (prepare/join) or `needs_attention` (commit).
- **The engine never runs commands it is sent**, and only allow-listed programs (`sgdisk`, `cryptsetup`, `btrfs`, …).
- **Fault injection:** while `/run/onemind/storage/hold-before-<step>` exists, the engine waits before that step (root-only tmpfs). This is how the lab cut power at exact points.

## 5. LUKS2 on every member (H-11)

| Keyslot | Content | Made by |
|---|---|---|
| recovery | the owner's recovery key: 256 random bits in systemd's modhex format, shown once, never stored | `onemindd storage init` (first boot) |
| set key | 512 random bits, kept inside the unlocked set at `/data/onemind/storage/keys/set.key` (root, 0600) | `init`; opens a member the engine just prepared |
| TPM2 | `systemd-tpm2` token sealed to PCR 7 (+ signed PCR 11 policy when the image ships its public key) | `init` when a TPM2 is present |

**New members get a byte copy of an existing member's header** (`luksHeaderBackup` → `luksHeaderRestore` → `luksUUID`): the same keyslots, so the same recovery key and TPM2 policy open them. That is the only way to give a new disk the recovery keyslot without asking the owner for the key, and it needs no key at all. Verified on cryptsetup 2.7.5: the recovery key opens every member in the lab. **The trade-off:** all members share one volume key. The members are open together in memory anyway, and AES-XTS sector tweaks differ per sector, but equal 16-byte blocks at the same offset of two stolen disks would look equal. The alternative is to have the owner type the recovery key whenever a disk is added. Founder decision F-63 (DECISIONS-NEEDED).

**The OneMind token** (LUKS2 token 30, `onemind-storage`): `{set_uuid, member_uuid, partuuid, generation}`. Rules the boot assembly follows (`ops.Choose`):
- A partition counts only if its token names **its own** GPT partition id. A header copied onto another disk carries the source's id, so a disk cut between the copy and its own token is never unlocked as a member (lab phase 4).
- The set with a member on the system disk is assembled; disks of other sets are reported as foreign.
- Only the newest generation is unlocked. Every membership change moves the remaining members one generation further, so a removed or replaced disk is stale. A replace keeps the old member current until `btrfs replace` has finished, then demotes it.
- If the newest generation cannot mount, older-generation members of the set are tried before a degraded mount (btrfs ignores a disk that really left; its superblock is wiped). `repair` re-stamps every member at one generation.

**Recovery key shown once:** `init` leaves it in `/run/onemind/storage/recovery-key` (tmpfs). The owner's dashboard takes it through `POST /v1/storage/recovery-key`, and the node overwrites and deletes the file. A reboot before that loses it; rotation (a new key on every member, using the set key) is a follow-up.

## 6. Events for notifications (CORE-NOTIFY-1)

The gateway publishes these with `publish_event` (audit, NATS `onemind.event.storage.*`, in-process subscribers):

| Event | Severity | Dedupe key | When |
|---|---|---|---|
| `storage.state` | info / critical | – | the set's state changed (`protected`, `unprotected`, `degraded`, `unavailable`, `unsupported`) |
| `storage.degraded` | critical | `storage:<node>:set` | entered `degraded`, `unavailable` or `unsupported` |
| `storage.ok` | info | `storage:<node>:set` | left those states |
| `storage.disk.failing` | critical | `storage:<node>:disk:<hash>` | SMART verdict became critical |
| `storage.disk.warning` | warning | same | became warning |
| `storage.disk.ok` | info | same | back to ok |
| `storage.operation.finished` | info / warning / critical | – | an operation succeeded, rolled back, failed or needs attention |
| `storage.recovery_key.shown` | info | – | the owner took the key (the key itself is never in an event) |

Payloads carry the node id, disk path, model and serial **tail** only; `<hash>` is a hash of the disk id. The notifications stream adds these lines to `core/onemind_core/notify/catalogue.py` (branch `feat/notify-monitor`; the storage branch does not edit it):

```python
    Spec("storage.degraded", "open", "storage", "critical", "Data on {node_id} is not fully protected",
         "{reasons}", dedupe="storage:{node_id}:set", link="/settings/storage", notify_resolve=True,
         fix=lambda _d: {"type": "storage.mirror.repair", "params": {}}),
    Spec("storage.ok", "resolve", "storage", resolves=("storage:{node_id}:set",)),
    Spec("storage.disk.failing", "open", "storage", "critical", "Disk {model} (…{serial_tail}) is failing",
         "{reasons}. Replace it soon.", dedupe="storage:{node_id}:disk:{disk_key}", link="/settings/storage"),
    Spec("storage.disk.warning", "open", "storage", "warning", "Disk {model} (…{serial_tail}) needs attention",
         "{reasons}", dedupe="storage:{node_id}:disk:{disk_key}", link="/settings/storage"),
    Spec("storage.disk.ok", "resolve", "storage", resolves=("storage:{node_id}:disk:{disk_key}",)),
```

## 7. Security

- The node's socket is mode 0660, root and group `onemind` (the gateway); each connection's peer credentials are checked again (`SO_PEERCRED`). In the lab a user outside the group could not connect.
- Three renders of the plan (request, approval, run) with the same `plan_sha256`: a swapped disk never gets wiped.
- Agents request and read; they never approve (403 before any handler runs). `remove`, which can lower protection, is owner-only.
- No secret goes through the gateway except the recovery key, once, to an owner, with `no-store`. Keys reach `cryptsetup` on stdin or from tmpfs files; plans and journals contain no key.
- **Gap until the identity stream merges:** contract §12.3 wants a passkey step-up on destructive approvals. The identity branch adds it as an approval guard on `/v1/actions/{id}/approve` for every type; until then the owner token approves (F-12 interim, API.md §8.4). Storage actions are off by default (`ONEMIND_STORAGE_ENABLED`).

## 8. v0 limits

- Only the hub's own disks. Other nodes need the signed jobs of contract §12.11; a request for another node is refused.
- An unreachable node service is `409 stale_precondition` (the §12.2 `unavailable` / 503 code is not in the §3 error set yet).
- Feature-owned action types plug into `actions.py` through `register_type`, `file` and `finish` (one hook, WORKSTREAMS §3), until DEV-API-7's registry replaces it. `POST /v1/actions` and MCP `request_action` do not take storage types yet.
- No `storage init --plain` for boards without LUKS (F-62), no recovery-key rotation, no "wipe this disk" action (the lab blanked a half-prepared disk by hand once), no scrub scheduler (UMB-STOR-6), no heartbeat `storage` object yet.

## 9. Tests

- Go: `go test -race ./internal/storage/... ./cmd/onemindd`. The engine runs against a simulated box: power cuts before and after a step's effect, during a kernel balance (running and paused), during prepare with disks renamed across the reboot, a target unplugged while off, a stale replace status, a resumed-replace race, rollback, remove, replace and the socket API. The assembly tests cover the choice rules (copied headers, foreign sets, stale generations), late disks, one cached prompt, degraded and recovery mode.
- Python: `core/tests/test_storage.py` runs a fake node service on a real Unix socket: request, approve, run and finish; stale plan; agent refusals; idempotency; restart mid-operation; never started; events once; recovery key once. It passes on SQLite and PostgreSQL 17 with the whole core suite.
- Debian 13 VM lab: all phases pass, and five bugs found there are fixed ([lab README](../../../research-output/evidence/lab/storage-actions/README.md)).

## 10. Follow-ups

| What | Epic |
|---|---|
| `onemind storage` CLI group on the action API (typed serial tail before a wipe) | UMB-STOR-9 |
| MCP `get_storage_status`, `list_storage_devices`; `request_action` with storage types | UMB-STOR-9, DEV-MCP-3 |
| Dashboard storage page and approval card (`ui/src/storage/` first) | UMB-STOR-8 |
| Monthly scrub, alert thresholds, SMART without waking sleeping disks (`smartctl -n standby`) | UMB-STOR-6 |
| Heartbeat `storage` object (§12.10) from the node service | UMB-STOR-3 |
| Contract rows for the types and routes above | UMB-STOR-0 |
| Recovery-key rotation (new key on every member through the set key) | CORE-SEC-5 follow-up |
| `storage init --plain` and plain-btrfs assembly, if F-62 picks it for cloud boards | F-62 |
| A "wipe this disk" action (format is critical, UMB-STOR-13) and storage actions on other nodes (signed jobs, §12.11) | UMB-STOR-13, CORE-FABRIC |
