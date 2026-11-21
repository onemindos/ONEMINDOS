<!-- SPDX-License-Identifier: Apache-2.0 -->
# Host actions: restart, shutdown, OS install and factory reset on the box

**Date:** 2026-11-19 · **Issues:** #146 (system controls), #142 (OS updates) · **Status:** PR 1 built (service, restart, shutdown, OS install hand-off); PR 2 (factory reset wipe) designed here, next · **Founder decision:** factory reset wipes all on-box data and keeps off-box backups (#146, 2026-11-18) · **Locked rule:** AI never actuates without owner approval (D-001 to D-014).

> **Explain it like I am the founder**
> The gateway (the box's brain, running in k3s) can record that you approved "restart" or "install 1.2.0", but it has no right to power the machine off. That is on purpose: the gateway faces the network. So a small separate program, `onemindd host serve`, runs as root on the box and listens only on a local file-like socket that just root and the gateway's user can open. The gateway hands it the id of an action you already approved. The program writes that down first (so a retry never runs it twice, and the answer survives the reboot it causes), then does it. It never decides anything itself.

## 1. Pieces

| Piece | Where | What it does |
|---|---|---|
| `onemindd host serve` | `cmd/onemindd/host.go`, `internal/host/` | The API below, the journal, restart and shutdown through systemd, the OS install hand-off to `internal/update` |
| `onemind-host.service` + `onemind-host.socket` | `os/rootfs/layers/onemind/usr/lib/systemd/system/` | Root, sandboxed like `onemind-update.service` (`SystemCallFilter=~@privileged`, which also forbids chown). systemd creates the socket (socket activation), so the service never chowns and holds no `CAP_CHOWN`. Started by `onemind-firstboot` on the hub role |
| Journal | `/data/onemind/host/actions/<action_id>.json` | One file per action, written whole (temp file, fsync, rename, fsync of the folder) |
| Socket | `/run/onemind/host.sock` | Mode 0660, `root:onemind`, made by `onemind-host.socket`. Every connection's peer credentials (SO_PEERCRED) are checked: root, or the gateway's **uid** (user `onemind`); any other process, even one in group `onemind`, gets 403 before any handler runs |

## 2. The socket contract (for the gateway follow-up)

JSON over HTTP/1.1 on the Unix socket, like `onemindd storage serve` (`core/onemind_core/storage.py` `_UnixConnection` can be reused as is).

| Call | Answer |
|---|---|
| `GET /v1/status` | `{"schema": "onemind.host/v1", "boot_id", "journal": bool, "operations": [{"kind", "available", "unavailable_reason"}], "active_operation": Op or null, "at"}`. Kinds in this order: `restart`, `shutdown`, `factory-reset`, `os-install` |
| `POST /v1/operations` `{"action_id", "kind", "version"?}` | **202** + Op: new, accepted. **200** + Op: this action id is already known with the same request (idempotent retry; nothing new runs). **409** `{"error": "refused", "reason", "message"}`: `busy`, `action_id_reused`, `unavailable`, `update_in_progress` (restart, shutdown or reset while an OS update is downloading, installing, waiting to reboot or on its trial). **400** `bad_request`: malformed, unknown field, unknown kind, version missing or present where it must not be. **503** `no_journal`. **403** `permission_denied` |
| `GET /v1/operations/{action_id}` | **200** Op, **404** `unknown_action` |
| `GET /v1/operations` | the 50 newest Ops |

`action_id`: 1 to 128 of `A-Z a-z 0-9 _ . : -` (the gateway's action id). `version` (os-install only): the gateway's `InstallParams.version` pattern.

**Op** = `{"action_id", "kind", "version"?, "state", "reason"?, "message", "boot_id", "accepted_at", "updated_at", "finished_at"?}`. States: `accepted` → `running` (os-install, factory-reset arming) → `going_down` → `succeeded`, or `failed` with a stable `reason`: `host_error`, `interrupted`, `version_not_offered`, `update_pending`, `engine_busy`, `engine_declined`, `engine_error`, `unavailable`, `not_wiped`.

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
- **A factory-reset record that survives a reboot** becomes `failed`, `not_wiped`: the journal is on `/data`, which the wipe erases, so a surviving record proves the wipe did not run.
- **An unreadable journal record** stops the service from acting (status only), because it may hide an open action.
- **Anything left open by a crash or power cut** (`accepted`, `running`, or `going_down` on the same boot) becomes `failed`, `interrupted`. It is never re-run unasked: a restart the owner approved an hour ago must not happen by surprise.
- **OS install** runs `internal/update`'s engine in this process: first `ModeCheck` (is `version` the update on offer? else `version_not_offered`), then `ModeApply`, the same path as `onemind update apply`: restic snapshot, RAUC install into the other slot (RAUC re-checks the signature), reboot, health-gated trial, automatic rollback (D-007). Three guards keep it honest. (1) If the check finds an install already `pending_reboot` or on `trial`, the request is refused (`update_pending`): the engine's `ModeApply` would otherwise reboot into that other version without installing anything. (2) The installer refuses unless the engine's target version is still the approved one (a channel that moved on between check and apply installs nothing). (3) The rebooter re-reads the engine's status and reboots only into the approved version, refusing with `update_pending` otherwise; it journals `going_down` just before. The engine's own lock stops it racing the update service. Never a raw `rauc install`.

## 4. Factory reset (PR 2)

**What is wiped:** the data set (every member, see below): apps, k3s state, settings, the owner and passkeys, the box CA and identity, tokens, the backup device key, local snapshots, the journal itself; plus `onemind.conf.applied` on the ESP (the first-boot settings, which can hold a join code). **What is kept:** both A/B system slots and GRUB's boot state, the ESP's RAUC trial note (`/boot/efi/onemind/pending`), and every off-box backup (restic repositories on other disks, boxes or clouds). Restoring from them after setup needs the owner's printed recovery key, because the device key is wiped with the box (BACKUPS.md §2: the owner key restores alone).

**Two phases, safe across power loss:**

| Step | Who | Writes | A power cut here means |
|---|---|---|---|
| 1. Arm | `host serve` (running box) | journal `running`; marker `/boot/efi/onemind/factory-reset` (`ACTION_ID`, `REQUESTED_AT`, `DATA_SET` = the data set's UUID (ext4 UUID today, btrfs set UUID after the storage patch), `EXPIRES_AT` = a short window such as 1 hour, written temp + fsync + rename + fsync) on the ESP, which is not on the data set and survives the wipe | before the marker: nothing happened; `Resume` reports `interrupted`. After: the next boot wipes (the owner approved it) |
| 2. Reboot | `host serve` | journal `going_down`; `systemctl reboot` | the marker is there: the next boot wipes |
| 3. Wipe | `onemind-factory-reset.service`, early boot: `DefaultDependencies=no`, `RequiresMountsFor=/boot/efi`, `Before=data.mount onemind-data-assemble.service onemind-data-layout.service onemind-data-check.service local-fs.target`, `ConditionPathExists=/boot/efi/onemind/factory-reset` | marker `STATE=wiping`, `ATTEMPTS+1`; wipes each member; removes `onemind.conf.applied` | every step is repeatable, so the next boot simply starts the wipe again. The marker is removed only after the last step |
| 4. Done | same unit | marker renamed to `factory-reset.done` (`ACTION_ID`, `COMPLETED_AT`) | the boot goes on: `/data` mounts the empty data set, `onemind-data-layout` makes the folders, `onemind-firstboot` finds no state and starts the setup wizard. No second reboot |

**The wipe, per data set kind:**
- Today (plain ext4 on `PARTLABEL=onemind-data`, one partition on the system disk): `blkdiscard` (best effort; SSDs drop the blocks) then `mkfs.ext4 -F -L onemind-data -E root_owner=0:0`, the same file system the image ships.
- After the storage patch (LUKS2 + btrfs, maybe a mirror): every LUKS2 partition labelled `onemind-data` whose OneMind token names this box's set (`ops.Choose` already tells this box's set from a disk of another box): `cryptsetup erase` (destroys every keyslot: the data can never be decrypted again) then `wipefs -a`. First boot's `storage assemble --init` formats the system-disk partition; the other disks come back as blank disks.

**If the wipe fails** (a disk error): the unit writes `/run/onemind-recovery/status` with `REASON=factory-reset` and fails; `OnFailure=` isolates `onemind-recovery.target`, so the old data is **never** mounted after a reset was approved. The next boot tries again.

**The marker is checked before anything is wiped.** If `DATA_SET` does not match the data set on this boot, or `EXPIRES_AT` has passed, the unit wipes nothing: it writes `REASON=factory-reset-stale` to `/run/onemind-recovery/status` and goes to recovery mode, where the owner decides. This stops a marker from wiping a different disk set, or from firing weeks later.

**Arming only on a committed slot.** The arm step refuses unless the booted slot is committed: no update trial, no ESP `pending` note, update state not `pending_reboot` or `trial`. Then a rollback cannot move the box onto a slot without the wipe unit while a marker is waiting. Even so, a slot without the wipe unit that boots with a marker present would mount the old data. PR 2 therefore also makes `onemind-data-check` (which every slot from now on carries) refuse to pass while a marker exists, and the expiry bounds the window.

**Refused when armed:** during an update trial or a pending reboot (the ESP `pending` note or the update state), or while a storage operation runs; the box would otherwise lose the gate's notes mid-trial.

**Older slot caveat:** a slot built before PR 2 has neither the wipe unit nor the marker check. Arming only on a committed slot, together with the expiry, keeps the box from rolling back onto such a slot while a reset is armed. PR 2's QEMU tests cover a power cut in step 3, a stale marker and a mismatched data set.

## 5. What is not tested here

QEMU checks (real reboot, real `systemctl poweroff`, a full install through the socket) need Linux with KVM; CI's image battery runs them. The Go tests use fakes for systemd and the engine, and a real Unix socket for the peer check.
