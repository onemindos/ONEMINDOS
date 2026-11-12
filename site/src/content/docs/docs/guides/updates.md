---
title: Updates and rollback
description: How to keep a developer install up to date today, what happens to security updates, and what the OneMind image will add.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

How updates work depends on how you installed OneMind. Today there is only one way, the **developer install** on a stock Debian system. The **OneMind image**, which can undo a bad update by itself, is being built. The [concept page](../../concepts/updates-and-rollback/) explains the design in depth.

## On a developer install <span class="om-tag om-tag--ok">works today</span>

### Security updates for the operating system

The install script turns on Debian's own automatic updates (`unattended-upgrades`) for **security fixes only**, and `needrestart`, which restarts the services that use an updated library. You do not need to do anything for these.

They are installed **in place**: if one breaks something, nothing rolls it back. That is the main weakness of a developer install, and the reason the script prints "unsupported developer install, no OS rollback" at the start and the end.

### Updating OneMind itself

OneMind's own parts (the node agent `onemindd`, the gateway and the dashboard) are built from your copy of the source code. To update them, get the newest code and run the install script again, with the same options as the first time:

```sh
cd ONEMINDOS
git pull
sudo deploy/install.sh --role hub          # on the hub, plus --hub URL if you used it before
```

On each other machine, run the join command again (the hub prints it every time the script runs):

```sh
cd ONEMINDOS
git pull
sudo deploy/install.sh --role node --hub http://<hub-address>:8080 --token <join-token>
```

Running the script again is safe. Every step checks what is already there, rebuilds only what changed, and restarts a service only when its program or settings changed. Your owner token, the gateway's records and your apps are kept.

### Rolling back a developer install

There is **no supported rollback** on a developer install, for the operating system or for OneMind:

- Debian security updates cannot be undone by OneMind.
- Checking out an older commit and running the script again rebuilds the older OneMind, but this is **not tested**, and it does not undo changes a newer gateway made to its database.
- The last resort, `sudo deploy/install.sh --uninstall` and a fresh install, **deletes every app and its data**.

If the box matters to you, wait for the OneMind image.

### App updates <span class="om-tag om-tag--unknown">coming soon</span>

New versions of apps reach the catalog through the repository, where each one passes the same security checks. But there is no "update app" action yet: an app you already installed keeps the version it was installed with. Do not remove and reinstall an app to update it, because removing deletes its data.

## On the OneMind image <span class="om-tag om-tag--unknown">coming soon</span>

The image is being built and tested in CI, but it cannot be downloaded yet, and no signed update channel is published. When it ships, updates work like this:

- **Two copies of the system** (slots A and B). An update is written to the copy you are not running.
- **The box proves it is healthy** after rebooting into the new copy: k3s ready and the core services answering, measured fresh after this boot. Only then is the update kept. Otherwise the next boot goes back to the old copy, by itself.
- **Signed updates.** The box checks the update's signed index (TUF) against a key built into the image, so a fake or an old update is refused.
- **A snapshot first.** The box backs up its data with restic before installing, when backups are set up.
- **Your policy.** Security fixes install automatically inside a maintenance window (02:00 to 05:00 by default); feature updates wait for you. You can change the window, postpone, or turn automatic installs off.

The command-line tool already has the update commands. They work only on the image; on a developer install they have no settings file (`/etc/onemind/update.conf`) and nothing to do:

```sh
onemind update status     # what is running, what is available, the last result
sudo onemind update check # look for an update and say what the policy would do; never installs
sudo onemind update apply # install now, as the owner (still waits for a pending health check)
```

Updating the image through an approval in the dashboard, like apps, is planned.
