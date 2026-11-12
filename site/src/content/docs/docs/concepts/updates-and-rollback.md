---
title: Updates and rollback
description: Signed A/B updates that are kept only after the box proves it is healthy.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

A box that updates itself must be able to undo a bad update by itself. OneMind keeps **two copies of the OS** (slot A and slot B). An update is written to the copy you are not running. You reboot into it, and it is **kept only if the box proves it is healthy**. Otherwise the next boot returns to the old copy.

## The health gate <span class="om-tag om-tag--unknown">being built</span>

Most systems that do A/B updates mark the new copy good as soon as one of their own programs starts, or when boot reaches a certain point. OneMind waits for **fresh** signs that it is doing its job: k3s ready and the core services answering, measured after this boot, never read from saved state. The gate is on `main` in [`os/gate/`](https://github.com/onemindos/ONEMINDOS/tree/main/os/gate) and is tested in QEMU in CI as part of the image battery.

- **RAUC** manages the slots.
- **Debian 13** is the base. The root filesystem is read-only, so packages are never upgraded in place.

## Update policy <span class="om-tag om-tag--unknown">being built</span>

Updates are automatic **by a policy the owner set**:

| Channel | Default | What it carries |
|---|---|---|
| security | installs automatically, in your maintenance window | Debian security fixes, rebuilt nightly when a fix exists |
| stable | notifies you; you approve | new features |

You can postpone, set the window, or turn automatic installs off. The EU Cyber Resilience Act asks for automatic security updates on by default, with an easy opt-out; this policy is built to meet that.

On the box, `onemindd` checks the channel, verifies the signed metadata (**TUF**, The Update Framework), takes a backup snapshot first, installs into the other slot, reboots at a safe point, and records whether the update was **committed** or **rolled back**. This client is on `main` in [`internal/update/`](https://github.com/onemindos/ONEMINDOS/tree/main/internal/update); it has nothing to install until the OneMind image and a signed channel are published:

```sh
onemind update status     # booted slot, channel, last result
onemind update check      # is there something newer?
onemind update apply      # install now (inside your policy)
```

## Nightly security rebuilds <span class="om-tag om-tag--warn">in review</span>

CI checks the Debian security tracker against the packages in the current image. When a fix exists, it rebuilds from a new, pinned Debian snapshot and runs the SBOM, a CVE scan, ClamAV over the root filesystem and the QEMU boot battery. Only then does it sign the bundle and publish it to the security channel.

## On a developer install

`deploy/install.sh` runs on a stock OS, so there is no second slot and no rollback. It turns on Debian's `unattended-upgrades` for security updates only. Treat it as the weaker path it is.

## Apps

App updates follow the app's own channel. Security-channel app updates install within your policy; everything else is an action waiting for approval. See [Apps and trust cards](../apps-and-trust-cards/).
