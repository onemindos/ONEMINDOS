---
title: Backups
description: OneMind does not back anything up yet. What that means for you today, what is already built, and what is coming.
status: planned
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

:::caution[No backups yet]
OneMind does **not** back up your apps or their data today. Do not keep the only copy of anything important on a OneMind box yet.
:::

## What this means today

- **Removing an app deletes its data.** The app's files live in its own area on the hub (`app-<id>`), and removing the app deletes that area. See [Apps](../apps/#remove-an-app).
- **Uninstalling deletes every app's data.** `sudo deploy/install.sh --uninstall` removes k3s and everything stored in it. It keeps the gateway's own records (its database and audit log in `/var/lib/onemind`) unless you add `--purge`.
- **A broken disk loses everything on it.** Nothing is copied off the box.

What you can do now:

- Use each app's own export or backup feature, where it has one, and keep the copy somewhere other than the OneMind box.
- Treat a developer install as a place to learn and test, not as the home of your only copy of photos, passwords or documents.

## What is already built <span class="om-tag om-tag--warn">not switched on</span>

The backup agent is on `main` (`internal/backup`) and has been tested with real restic in Debian 13 virtual machines, but the node agent does not start it yet, and there is no backup screen. You cannot run a backup from OneMind today. When it is switched on, it will:

- take a **snapshot every hour** with [restic](https://restic.net), a well-known open-source backup program, into an encrypted repository on a USB disk, on another OneMind machine, or in S3-compatible storage;
- back up the system's own records, the cluster's state, each app, and each machine's identity as separate pieces;
- thin out old snapshots on a ladder: one per hour for a day, one per day for a week, one per week for a month, one per month for a year;
- once a week, **restore every piece into an empty scratch folder and read it back**, so "last verified restore" means something;
- let you browse any snapshot and put back one file or folder, after first snapshotting what is there now, so every restore can be undone;
- refuse to run when the USB disk is not plugged in, instead of filling the system disk.

The OneMind image's update client also takes a restic snapshot before every OS update, when restic is set up. That runs only on the image, which is not released yet.

## Coming soon

- Backups set up from the dashboard, with a copy off the box by default (the 3-2-1 rule: three copies, on two kinds of storage, one somewhere else).
- A recovery key you save during setup, so you can restore even if the box is lost.
- Restoring a whole box onto new hardware.
- An alert when backups stop or fail.

**Who may do what:** an AI agent will be allowed to start a backup and read its status. Restores, key changes, destination changes and deletions will always need a person, because restoring someone else's snapshot hands them the box.

The full design is in [Backups](../../concepts/backups/).
