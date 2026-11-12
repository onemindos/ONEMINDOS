---
title: Backups
description: "The backup design: restic, 3-2-1 by default, verified restores, and a format you can leave with."
status: planned
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

:::note[Planned]
Backups are designed and researched, not built. The one piece in review is the snapshot the update client takes before every OS update. Everything below is the plan, from [research 06](https://github.com/onemindos/ONEMINDOS/blob/main/research-output/06-backups-recovery.md).
:::

## What we will build

- **Engine: restic.** A standard, documented, BSD-licensed format. If OneMind disappears, you can restore with plain restic.
- **3-2-1 by default.** Hourly snapshots kept on a grandfather-father-son schedule, plus a copy off the box: to another OneMind box (append-only), or to any S3-compatible storage.
- **The whole box, not just files.** The k3s datastore (with its token and encryption config), every app's data, and the app list as plain YAML.
- **App-consistent.** Each app's manifest will declare how to back it up: hot or cold, commands to run before and after, SQLite databases to copy safely, paths to skip.
- **Three keys.** A key on the device, your own recovery key, and optional escrow. You finish setup only after saving the emergency kit. Keys are never derived from a short password.
- **Verified restores.** A daily partial read check, a weekly scratch restore with app health probes, and a dashboard line that says "last verified restore". You get an alert when backups go stale or fail.
- **Two restore modes.** Portable (to different hardware or another architecture) and exact (same hardware). You can restore during onboarding of a new box.

## Who may do what

Agents may **start** a backup and **read** backup status. **Restores, key changes, destination changes and deletions always need a human**, because restoring an attacker's snapshot hands them the box.

## Storage

App volumes use a storage class that **retains** data when an app is removed. Data is deleted only through an explicit "remove data" action, which takes a backup first.
