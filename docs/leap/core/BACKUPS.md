<!-- SPDX-License-Identifier: Apache-2.0 -->
# Backups and restore (CORE-BACKUP)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** E9 (Backups v0 + badge) · **Deeper docs:** `docs/architecture/BACKUPS.md` (architecture stream, branch `docs/core-architecture`, in progress); [`research-output/06-backups-recovery.md`](../../../research-output/06-backups-recovery.md) (W5-R1…R14) · **Serves:** brief 30 B7 (D-B7.1…D-B7.7); core-alignment BAK-P1…P5, BAK-B1…B4; R-2, M-2.

> **Explain it like I am the founder**
> The box backs itself up every hour with restic, encrypted, to a USB disk, another OneMind box or S3 storage.
> A backup only counts as green after the box has **actually restored it** into a scratch space and the apps came up healthy; that is the "verified restore" badge.
> You hold the recovery key on paper. Agents may start a backup and read its status; restoring, changing keys or destinations, or deleting backups always waits for you.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| Storage class `onemind-local` with `Retain`; app data deleted only by an explicit action | Velero, Longhorn backup or ZFS send as defaults (W5-R12) |
| restic agent in `onemindd`: hourly GFS, encrypted, three keys, emergency kit | A OneMind-hosted off-site service |
| k3s datastore online backup with integrity check inside the same snapshot | Warm standby / mirror (W5-R11, year 1) |
| Destinations: USB, another OneMind box (append-only rest-server), S3-compatible | Cross-household "buddy" backup (BAK-B3, later) |
| Restore one file, one app or the whole box; restore at onboarding | Live HA across nodes |
| Verified-restore badge; red after 7 days without a verified restore | |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| Pre-update restic snapshot of `/data` (optional) | `internal/update/` | `main` (PR #15) |
| restic pinned version | `internal/backup/pins.go` (not yet in `os/versions.lock.yaml`; `grep restic os/versions.lock.yaml` finds nothing on 2026-11-12) | partial |
| Seed apps' PVCs use k3s `local-path` (reclaim `Delete`) | `apps/*/manifests/pvc.yaml` | `main` |
| Everything else in brief 30 B7 | – | not built |

## 3. Design

### 3.1 What is backed up (research 06 §3)
| Layer | How |
|---|---|
| Cluster state | SQLite online `.backup` + `PRAGMA integrity_check` (gates the snapshot) + k3s token, node password, encryption config; records the exact k3s version |
| OneMind state | gateway ledger, audit log + last checkpoint, app list with versions, TLS CA, NATS config |
| App volumes | `onemind-local` folders, with manifest hooks (§3.4) |
| User files | as app volumes, optionally own schedule |
| Keys | **never** only inside the backup: emergency kit held by the owner |
| Excluded | images, caches, thumbnails, logs |

### 3.2 Keys and the emergency kit (CORE-BACKUP-2)
One restic repository per box with three keys: **device** (on the box, used by the schedule), **owner recovery** (printed or exported once; restores alone), **escrow** (optional). First boot cannot finish until the owner confirms the kit (contains the restic owner key and the LUKS recovery key, SECURITY CORE-SEC-5).

### 3.3 Commands and API
```console
$ onemind backup status
Repository   usb:onemind-backup (restic 0.19.1)   size 41.2 GB
Last backup  2026-11-16 09:00   ok   (hourly, keep 24h/7d/4w/12m)
Verified     2026-11-15 03:10   ok   uptime-kuma ✓ ntfy ✓ home-assistant ✓
Off-site     box:garage-box      2026-11-16 03:00 ok
$ onemind backup now            # creates action backup.run; runs at once if a standing approval covers it
action a_41  backup.run  accepted (policy:pol_backup_now)  → succeeded in 38 s
$ onemind restore 4f2a9c --app uptime-kuma
action a_42  backup.restore  awaiting_approval  → approve on your phone
```

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/backups/status` | any principal (agents with `backups:read`) | status above as JSON, with `verified_at` per app |
| `GET /v1/backups/snapshots?app_id=<id>` | owner, adult | snapshot list (id, time, size, k3s version) |
| `POST /v1/backups/runs` (action `backup.run`) | owner or agent | action; standing approval may accept it |
| `POST /v1/restores` (action `backup.restore`; API.md §5.3, plus `scope: file` and `path` to add there) | owner or agent request | **always** owner approval with passkey |
| `backup.destination.add` / `.remove`, `backup.snapshot.delete` (API.md §5.12), `backup.key.rotate` (to add to API.md §5.12) | owner request | owner approval; never covered by standing approvals |

```python
st = client.backups.status(); print(st.verified_at)                              # Python
```
```ts
await om.actions.request({ type: "backup.run", params: {} });                    // TypeScript
```
```go
a, _ := om.Actions.Request(ctx, onemind.Action{Type: "backup.restore",
        Params: map[string]any{"scope": "app", "app_id": "uptime-kuma", "snapshot": "4f2a9c"}}) // Go
```
**MCP:** a later `backup_status` read tool; `request_action` accepts `backup.run` and `backup.restore` (the latter always waits).

### 3.4 App hooks (CORE-BACKUP-5, W5-R5; manifest change)
```yaml
spec:
  backup:
    mode: hot            # hot | cold (cold scales to 0 during the snapshot)
    pre:  ["sqlite3 /data/kuma.db '.backup /data/kuma.db.bak'"]
    paths: ["/data"]
    exclude: ["/data/kuma.db", "/data/kuma.db-wal"]
    restore: {post: ["rm -f /data/kuma.db && mv /data/kuma.db.bak /data/kuma.db"]}
```
Hooks run inside the app's own pod (same sandbox), never on the host.

### 3.5 Verified-restore badge (CORE-BACKUP-7, BAK-B1, D-B7.6)
- Daily `restic check --read-data-subset`; on failure retry once and run a memory test before reporting damage.
- Weekly: restore each app into a scratch namespace `restore-<id>-<date>` on a scratch storage class with reclaim policy `Delete` (so cleanup frees the space), run the app's probes with **fresh** signals, then delete.
- A backup counts as verified only if the datastore is inside its size budget and compaction is not lagging (REC-DEC-49).
- The badge goes red after 7 days without a verified restore (plan E9) and raises an alert.

### 3.6 Restore modes (W5-R6)
**Portable** (default): new hardware or arch; images re-pulled. **Exact**: same box, same node name. Restore at onboarding offers both. Restore uses the same fresh-signal health check as the OS gate before it reports success.

## 4. Security model
- Restoring an attacker's snapshot hands them the box (research 06 C-W5-013): restore, key and destination changes and deletes **always** need the owner's passkey; standing approvals cannot cover them.
- Off-site box targets are append-only (rest-server `--append-only`): a stolen or compromised box cannot delete its own history.
- Repository passwords are random, never derived from short passwords; the device key file is 0600 on the LUKS-encrypted data partition.
- Backups contain k3s Secrets; with secrets encryption on (CORE-SEC-5) they stay encrypted inside the snapshot, and the encryption config travels in the same snapshot so restore works.

## 5. Versioning and compatibility
- The repository is plain restic (W5-R14): an owner can restore without OneMind. restic version is pinned in `os/versions.lock.yaml`; a restic upgrade must read repositories written by the previous pinned version (CI test).
- Each snapshot records the OneMind version, k3s version and app versions; restore refuses to put a newer k3s datastore under an older k3s (k3s minor guard, brief 30 B5).
- `spec.backup` is additive; apps without it get a default (`hot`, all PVCs, no hooks) and a "crash-consistent only" label.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Retain | Deleting a PVC keeps its data folder (D-B7.1) |
| Fresh-VM restore | Restore a box onto a fresh VM: all pods back with identical data (plan E9, D-B7.3) |
| Owner key alone | The printed owner key restores without the device key |
| Pre-update | Every OS update has a snapshot taken first (plan E9) |
| Badge | Fake clock +7 days without a verified restore → badge red and one alert |
| Approval | An agent's `backup.restore` stays `awaiting_approval`; a standing approval cannot accept it |
| Append-only | The source box cannot `forget` snapshots on the off-site box |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-BACKUP-1 | `onemind-local` Retain StorageClass as default; seed apps switched | S | image + deploy |
| CORE-BACKUP-2 | `internal/backup` agent: restic, schedule, three keys, emergency kit | L | 1, SEC-5 |
| CORE-BACKUP-3 | k3s datastore online backup with integrity gate | M | 2 |
| CORE-BACKUP-4 | Destinations: USB, OneMind box (append-only), S3 | M | 2 |
| CORE-BACKUP-5 | Manifest `backup:` hooks | M | 2, schema PR |
| CORE-BACKUP-6 | Restore file/app/box, approval-gated; restore at onboarding | M | 2, 3 |
| CORE-BACKUP-7 | Verified-restore badge (daily check, weekly scratch restore) | M | 6 |
| CORE-BACKUP-8 | Gateway API + Backups screen + alerts | S | 2, DASH-1, NOTIFY-1 |

## 8. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/backup-agent` | new `internal/backup/`, `cmd/onemind/cli/backup.go` (with DEV-CLI-7), `deploy/systemd/onemind-backup.service` |
| `feat/backup-api` | new `core/onemind_core/backups.py`, `dashboard/src/pages/Backups.tsx` |
| image + deploy | `os/rootfs/.../storageclass-onemind-local.yaml`, `deploy/install.sh` |
| `feat/onemindd-updater` | keeps the pre-update snapshot; calls `internal/backup` once it lands |
| Hotspots (serialized) | `cmd/onemindd/main.go` (`backup` subcommand), `os/versions.lock.yaml` (restic), schema (`spec.backup`), contract §3 action types |
