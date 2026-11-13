<!-- SPDX-License-Identifier: Apache-2.0 -->
# Backups and Restore (`@onemind/ui` backups)

**Serves:** CORE-BACKUP-8 (Backups screen), CORE-BACKUP-6 (restore with undo), CORE-BACKUP-7 (verified badge), ONB-B2 (the emergency kit cannot be skipped). **API:** contract §12.12, served by `core/onemind_core/routers/backups.py` (see `core/onemind_core/backups/README.md`). **Demo:** `npm run dev`, then `#/backup`, `#/backup/rewind`, `#/backup/restore`, `#/backup/kit` (add `?state=loading|error|stale` on the overview).

**Plain English.** One screen answers "is my stuff safe?" with a word, not just a colour: *Verified* means the box restored the backup into a scratch space and read it back in the last 8 days. Rewind lets the owner open any restore point like a folder, download a file, or ask to put one file or the whole app back. A restore is a request: it waits for approval, saves today's data first, and puts it back by itself if the app does not come up healthy. The emergency kit shows the recovery key once and then asks for two of its groups, so a kit that was only glanced at never counts as saved.

## What is here

| Part | File | What it does |
|---|---|---|
| Shapes | `types.ts` | `BackupsStatus`, `BackupBadge`, `Destination`, `BackupRun`, `Snapshot`, `TreeEntry`, `Restore`, `KitState`, `KitOneTime`, `Load<T>` |
| Rules | `logic.ts` | badge words and age, notices in order of urgency (agent down, no destination, kit, one copy only), volume names and breadcrumbs, restore points by day, type-back and restore confirmation, the restore request and its curl twin |
| Overview | `BackupsOverview.tsx` | health, last backup, last tested restore, next run, copies; a badge per app (with "copied while running" for apps without hooks); destinations; recent runs with failed units named |
| Destination | `DestinationForm.tsx` | USB disk, another OneMind box (append-only), S3; credentials write-only |
| Rewind | `Rewind.tsx` | restore points by day, folder browser from each volume root, download, "Put back…", "Restore all of …" |
| Restore | `RestoreDialog.tsx` | the plan in plain words, typed app id for a whole-app restore, optional reason, "the same request from a terminal"; `RestoreProgress` follows steps, the health gate and offers undo |
| Kit | `EmergencyKit.tsx` | show once, download or print, "I saved it", type back two groups; no skip; the key is dropped from memory once confirmed |

## Rules the code keeps
- Components never fetch; the dashboard passes API objects and the hub's `now`.
- Stale data is never shown as live: a stale overview says so and disables every request.
- Every state has a word next to its colour (WCAG 1.4.1); tests run axe on the overview, Rewind and the kit.
- Opening a snapshot is announced as audited, because the hub records every read.

## Wiring into the dashboard (later pass, dashboard stream)
`dashboard/src/pages/Backups.tsx` renders `BackupsOverview` from `GET /v1/backups/status` and `/runs`; Rewind uses `/snapshots`, `/snapshots/{id}/tree` and a download URL for `/file` with the session; `RestoreDialog` posts `/v1/restores`; onboarding mounts `EmergencyKit` with `POST /v1/backups/kit` and `/kit/confirm`, and finishes only when `status.setup.blocking` is empty.
