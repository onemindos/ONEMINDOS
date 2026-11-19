<!-- SPDX-License-Identifier: Apache-2.0 -->
# Host actions: restart, shutdown, OS install and factory reset on the box

**Date:** 2026-11-19 · **Issues:** #146 (system controls), #142 (OS updates) · **Status:** PR 1 built (service, restart, shutdown, OS install hand-off); PR 2 (factory reset wipe) designed here, next · **Founder decision:** factory reset wipes all on-box data and keeps off-box backups (#146, 2026-11-18) · **Locked rule:** AI never actuates without owner approval (D-001 to D-014).

> **Explain it like I am the founder**
> The gateway (the box's brain, running in k3s) can record that you approved "restart" or "install 1.2.0", but it has no right to power the machine off. That is on purpose: the gateway faces the network. So a small separate program, `onemindd host serve`, runs as root on the box and listens only on a local file-like socket that just root and the gateway's user can open. The gateway hands it the id of an action you already approved. The program writes that down first (so a retry never runs it twice, and the answer survives the reboot it causes), then does it. It never decides anything itself.

## 1. Pieces

| Piece | Where | What it does |
|---|---|---|
| `onemindd host serve` | `cmd/onemindd/host.go`, `internal/host/` | The API below, the journal, restart and shutdown through systemd, the OS install hand-off to `internal/update` |
| `onemind-host.service` | `os/rootfs/layers/onemind/usr/lib/systemd/system/` | Root, sandboxed like `onemind-update.service` plus `CAP_CHOWN` for the socket group. Started by `onemind-firstboot` on the hub role |
| Journal | `/data/onemind/host/actions/<action_id>.json` | One file per action, written whole (temp file, fsync, rename, fsync of the folder) |
| Socket | `/run/onemind/host.sock` | Mode 0660, `root:onemind` (same `ops.Listen` as the storage service). Every connection's peer credentials (SO_PEERCRED) are checked: root, or group `onemind`; anyone else gets 403 before any handler runs |

## 2. The socket contract (for the gateway follow-up)

JSON over HTTP/1.1 on the Unix socket, like `onemindd storage serve` (`core/onemind_core/storage.py` `_UnixConnection` can be reused as is).

| Call | Answer |
|---|---|
| `GET /v1/status` | `{"schema": "onemind.host/v1", "boot_id", "journal": bool, "operations": [{"kind", "available", "unavailable_reason"}], "active_operation": Op or null, "at"}`. Kinds in this order: `restart`, `shutdown`, `factory-reset`, `os-install` |
| `POST /v1/operations` `{"action_id", "kind", "version"?}` | **202** + Op: new, accepted. **200** + Op: this action id is already known with the same request (idempotent retry; nothing new runs). **409** `{"error": "refused", "reason", "message"}`: `busy`, `action_id_reused`, `unavailable`. **400** `bad_request`: malformed, unknown field, unknown kind, version missing or present where it must not be. **503** `no_journal`. **403** `permission_denied` |
| `GET /v1/operations/{action_id}` | **200** Op, **404** `unknown_action` |
| `GET /v1/operations` | the 50 newest Ops |

`action_id`: 1 to 128 of `A-Z a-z 0-9 _ . : -` (the gateway's action id). `version` (os-install only): the gateway's `InstallParams.version` pattern.

**Op** = `{"action_id", "kind", "version"?, "state", "reason"?, "message", "boot_id", "accepted_at", "updated_at", "finished_at"?}`. States: `accepted` → `running` (os-install, factory-reset arming) → `going_down` → `succeeded`, or `failed` with a stable `reason`: `host_error`, `interrupted`, `version_not_offered`, `engine_busy`, `engine_declined`, `engine_error`, `unavailable`.

**Mapping in the gateway** (follow-up PR after #355 and #357 merge; nothing in `core/` changes in this PR):

| Gateway action type | kind |
|---|---|
| `system.restart` | `restart` |
| `system.shutdown` | `shutdown` |
| `system.factory_reset` | `factory-reset` |
| `os.update.install` (`params.version`) | `os-install` |

The follow-up adds `HostSocketExecutor` in `core/onemind_core/system.py`:
1. `unavailable(type)`: `GET /v1/status`; the kind's `unavailable_reason`, or the `NoHostPath` message when the socket is missing.
2. `SystemExecutor.run` needs the action id: change it to `run(action)` and send `POST /v1/operations {"action_id": a.id, "kind": ...}`. 202 or 200: return `None` (still running), like the storage executor. 409 or 400: `ExecResult("failed", message)`.
3. A poller (the storage poller's `_sync_operations`) reads `GET /v1/operations/{id}` for open actions and closes them on `succeeded` or `failed`. `going_down` means the box (and the gateway) is about to stop: the gateway restarts with the action `outcome_unknown` and the poller then reads `succeeded` from the journal.
4. `os.update.install` does the same with `version`; the health gate's later verdict still arrives through the heartbeat (`osupdate.py observe`).

## 3. Restart, shutdown, OS install

- **Restart / shutdown:** journal `accepted`, wait `--delay` (3 s) so the gateway records the answer, journal `going_down`, then `systemctl reboot` or `systemctl poweroff` (systemd stops every unit cleanly). A failed command: `failed`, `host_error`. On the next start, `Resume` turns a `going_down` from an earlier boot (different `boot_id`) into `succeeded`.
- **Anything left open by a crash or power cut** (`accepted`, `running`, or `going_down` on the same boot) becomes `failed`, `interrupted`. It is never re-run unasked: a restart the owner approved an hour ago must not happen by surprise.
- **OS install** runs `internal/update`'s engine in this process: first `ModeCheck` (is `version` the update on offer? else `version_not_offered`), then `ModeApply`, the same path as `onemind update apply`: restic snapshot, RAUC install into the other slot (RAUC re-checks the signature), reboot, health-gated trial, automatic rollback (D-007). Two wrappers keep it honest: the installer refuses unless the engine's target version is still the approved one (a channel that moved on between check and apply installs nothing), and the rebooter journals `going_down` before the engine reboots. The engine's own lock stops it racing the update service. Never a raw `rauc install`.

## 4. Factory reset (PR 2)

**What is wiped:** the data set (every member, see below): apps, k3s state, settings, the owner and passkeys, the box CA and identity, tokens, the backup device key, local snapshots, the journal itself; plus `onemind.conf.applied` on the ESP (the first-boot settings, which can hold a join code). **What is kept:** both A/B system slots and GRUB's boot state, the ESP's RAUC trial note (`/boot/efi/onemind/pending`), and every off-box backup (restic repositories on other disks, boxes or clouds). Restoring from them after setup needs the owner's printed recovery key, because the device key is wiped with the box (BACKUPS.md §2: the owner key restores alone).

**Two phases, safe across power loss:**

| Step | Who | Writes | A power cut here means |
|---|---|---|---|
| 1. Arm | `host serve` (running box) | journal `running`; marker `/boot/efi/onemind/factory-reset` (`ACTION_ID`, `REQUESTED_AT`, written temp + fsync + rename + fsync) on the ESP, which is not on the data set and survives the wipe | before the marker: nothing happened; `Resume` reports `interrupted`. After: the next boot wipes (the owner approved it) |
| 2. Reboot | `host serve` | journal `going_down`; `systemctl reboot` | the marker is there: the next boot wipes |
| 3. Wipe | `onemind-factory-reset.service`, early boot: `DefaultDependencies=no`, `RequiresMountsFor=/boot/efi`, `Before=data.mount onemind-data-assemble.service onemind-data-layout.service onemind-data-check.service local-fs.target`, `ConditionPathExists=/boot/efi/onemind/factory-reset` | marker `STATE=wiping`, `ATTEMPTS+1`; wipes each member; removes `onemind.conf.applied` | every step is repeatable, so the next boot simply starts the wipe again. The marker is removed only after the last step |
| 4. Done | same unit | marker renamed to `factory-reset.done` (`ACTION_ID`, `COMPLETED_AT`) | the boot goes on: `/data` mounts the empty data set, `onemind-data-layout` makes the folders, `onemind-firstboot` finds no state and starts the setup wizard. No second reboot |

**The wipe, per data set kind:**
- Today (plain ext4 on `PARTLABEL=onemind-data`, one partition on the system disk): `blkdiscard` (best effort; SSDs drop the blocks) then `mkfs.ext4 -F -L onemind-data -E root_owner=0:0`, the same file system the image ships.
- After the storage patch (LUKS2 + btrfs, maybe a mirror): every LUKS2 partition labelled `onemind-data` whose OneMind token names this box's set (`ops.Choose` already tells this box's set from a disk of another box): `cryptsetup erase` (destroys every keyslot: the data can never be decrypted again) then `wipefs -a`. First boot's `storage assemble --init` formats the system-disk partition; the other disks come back as blank disks.

**If the wipe fails** (a disk error): the unit writes `/run/onemind-recovery/status` with `REASON=factory-reset` and fails; `OnFailure=` isolates `onemind-recovery.target`, so the old data is **never** mounted after a reset was approved. The next boot tries again.

**Refused when armed:** during an update trial or a pending reboot (the ESP `pending` note or the update state), or while a storage operation runs; the box would otherwise lose the gate's notes mid-trial.

**Older slot caveat:** a rollback to a slot built before PR 2 has no wipe unit; the marker then waits until a slot that has it boots. PR 2's QEMU test covers a power cut in step 3.

## 5. What is not tested here

QEMU checks (real reboot, real `systemctl poweroff`, a full install through the socket) need Linux with KVM; CI's image battery runs them. The Go tests use fakes for systemd and the engine, and a real Unix socket for the peer check.
