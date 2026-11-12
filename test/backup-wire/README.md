<!-- SPDX-License-Identifier: Apache-2.0 -->
# Backups switched on: the real-system proof

**Serves:** BACKUP-WIRE-1, DB-SHARED-1, CORE-BACKUP-6/7 acceptance ("back up, break data, restore, badge turns green after a scratch restore"); BACKUPS.md BT-1, BT-3, BT-5, BT-13 (part).

> **In plain words.** This script builds a throwaway Debian 13 machine (a Lima VM on a Mac), installs OneMind on it the way a developer would, plugs in a pretend USB disk, installs a small test app that keeps a file and a database row, backs it up, breaks both, restores them through an approved request, and checks that the badge only turns green after the box has proven it can restore. Nothing is installed on the Mac itself.

```sh
test/backup-wire/lima-e2e.sh            # create the VM, run, keep it for inspection
test/backup-wire/lima-e2e.sh --delete   # delete the VM afterwards
```

`lima-e2e.sh` cross-compiles `onemindd` on the host, copies only what the install reads (`deploy/`, `core/`, `sdk/schema/`, `apps/`, this folder), and runs `in-vm.sh` as root inside the VM. `in-vm.sh` prints `PASS` or `FAIL` per check and exits non-zero on any failure. It uses the owner token and the emergency kit's key without printing them.

## What it checks

| Step | Checks |
|---|---|
| 1. Developer install | `deploy/install.sh --role hub` brings up k3s, NATS, the gateway, `onemindd` and `onemind-backup.service`; the agent listens on `127.0.0.1:7481` only; an unsigned restore job is refused (403); setup is blocked on the emergency kit |
| 2. Destination | a loop-mounted ext4 image at `/run/onemind/backup/<uuid>` added as a USB destination through `POST /v1/backups/destinations` (owner shortcut) |
| 3. Probe app | `backup-probe/` (one volume on `onemind-local`, `spec.database`, a `backup.pre` hook) installs; the shared PostgreSQL starts on Retain storage; the app logs in to its own database with its own role and cannot open the maintenance database; no password in the install result |
| 5. Backup | a run with `system`, `k3s` and `app:backup-probe` all succeeded; the pre hook ran inside the app container; plain restic lists the snapshot by its tags; it holds the volume and the `pg_dump`; excluded paths are absent; the heartbeat carries `backup.last_result` |
| 6. Emergency kit | wrong groups refused, right groups confirm, setup unblocked; **the owner key alone opens the repository with plain restic**; the key is nowhere under the gateway's state or `/etc/onemind` |
| 7-8. Break, restore | file and row broken; `POST /v1/restores` waits for approval with a plan that saves today's data first; after approval the file and the database are back; the health gate passed on fresh pods; a pre-restore snapshot exists |
| 9. Rewind | browsing the pre-restore snapshot through the API and downloading `notes.txt` returns the broken version |
| 10. Badge | the app badge is "unverified" until `POST /v1/backups/verify`; after the scratch restore it is "verified", and the box badge and health are green |
| 11. Undo | restoring the pre-restore snapshot brings the broken file and rows back |
| 12. Audit | requests, approvals, restore state changes and snapshot downloads are in the audit log, and its hash chain verifies |

## Results

| Date (UTC) | VM | Result | Notes |
|---|---|---|---|
| 2026-11-12 | Lima, `template:debian-13` (Debian 13 cloud image 20261103, arm64, vz), 4 CPU, 6 GiB, deleted after | **42 of 42 checks passed** (run 6, commit after `9b0fd31`) | k3s v1.37.2+k3s1, restic 0.19.1, postgres 17.11-trixie; runs 1-5 found the three bugs below and two check-script mistakes |

**Not covered here:** amd64 (the pins are the same release; no amd64 VM was run), S3 and box destinations (the agent's own Lima test covers rest-server append-only), whole-box restore at onboarding (not built), a restore after the app was removed and reinstalled (Go unit test only).

### Bugs this run found (fixed on the branch)
1. **Adding a destination deleted the device key.** Destination credentials and the device key shared `<state>/secrets/`, and reconfiguring pruned every file it did not list. Credentials now live in `<state>/target-secrets/`, the config refuses a device key there, and a Go test covers it.
2. **Restores could not write app volumes.** `ReadWritePaths=-/var/lib/rancher/k3s/storage` is silently dropped by systemd when the folder does not exist yet at service start (before the first app volume). The restore then failed before changing anything and the app was started again, as designed, but nothing was restored. The install now creates the folders with a tmpfiles.d entry, at every boot; the image patch asks for the same.
3. **The health gate never saw the restarted pod.** Kubernetes records `creationTimestamp` in whole seconds; the gate compared it with a sub-second start time, so a pod created in the same second (10:35:48Z for a restart at 10:35:48.38) was never "fresh". The gate now cuts the start time to its second (every old pod is already gone by then); a unit test holds the exact timestamps.

### A failed restore rolled back on the real system (BT-6)
Bug 3 made run 4's restore fail its health gate, which exercised the rollback path for real. After 300 s the restore ended `failed` with steps "health gate failed, rolling back" and "previous data put back"; the app's file read `BROKEN` and its table `BROKEN,EXTRA` again (the state before the restore), and the moved-aside folder was gone. Nothing was lost, and the action said so: "backup-probe did not come back healthy after the restore; its previous data is back".
