<!-- SPDX-License-Identifier: Apache-2.0 -->
# See OneMind running (DEV-SEE-01, #234, milestone M-LIVE)

**Goal:** you boot a real OneMind on your own Mac, on the Beelink, or on a cloud droplet by following one page, with no CI digging.

> **Explain it like I'm the founder.** Every night a robot builds OneMind from `main` and posts three downloads on the GitHub *Releases* page as a **pre-release called `DEV BUILD dev-<date>-<commit>`**. A *pre-release* is GitHub's label for "not the finished product". These builds are signed with **throwaway keys**: fine for looking, wrong for anything real. Pick the download for where you want to run OneMind:

| I want to run it on | Download (from the newest `dev-*` pre-release) | Guide |
|---|---|---|
| My Apple Silicon Mac, in a window (UTM) | `onemind-arm64-efi-<v>.qcow2` | [mac-utm.md](mac-utm.md) |
| The Beelink (or any x86-64 PC), from a USB stick | `onemind-installer-amd64-<v>.img.xz` | [beelink-usb.md](beelink-usb.md) |
| A DigitalOcean droplet | `onemind-vm-do-<v>.qcow2` | [digitalocean.md](digitalocean.md) |

Where to find them: <https://github.com/onemindos/ONEMINDOS/releases> (tick "pre-release"; the newest `dev-*` entry). Check a download: `shasum -a 256 -c SHA256SUMS --ignore-missing` in the folder that holds it and `SHA256SUMS`.

## What you will see, on every machine

1. The first boot takes a few minutes (the box makes its own certificate authority and starts its services).
2. A **setup page** answers at `http://onemind.local:8080/` on the same network (or at the box's IP address, port 8080). Choose the role **hub** (the box that holds the dashboard).
3. The page shows your **owner token once**. Copy it: it is the key to the dashboard, only its checksum is kept, and it cannot be shown again. (It is also printed on the box's console.)
4. Reload the page after about a minute: the dashboard opens. Paste the token to sign in.

## Honest status

Nothing in these guides has been followed on real hardware yet by anyone but the author's QEMU runs; each guide carries an **UNVERIFIED** box listing the exact steps that need your eyes. When one step is wrong, say which and it is fixed in the guide, not in your head.

If a step fails, [../learning/mac-dev-loop.md](../learning/mac-dev-loop.md) explains the build side, and `os/recovery/README.md` explains what a box shows when it cannot start.
