<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind on the Beelink (or any x86-64 PC), from a USB stick

**Time:** 30 minutes plus first boot. **You need:** a 4 GB+ USB stick, a Mac or PC to write it, a monitor and keyboard for the Beelink, and a wired network. **This erases the Beelink's internal disk.**

> **Explain it like I'm the founder.** You make **one installer stick**. You boot the Beelink from it, choose the internal disk, type `ERASE`, and the stick copies OneMind onto the disk, checks every byte and restarts into OneMind. The stick is not changed, so it works for the next box. The stick's own README is [os/boards/installer-x86_64/README.md](../../os/boards/installer-x86_64/README.md).

> **UNVERIFIED on real hardware:** the installer passes its QEMU tests (I1-I5); the Beelink's boot menu key, its UEFI settings and the speed below are what the build notes say, not something anyone has measured on a Beelink yet.

## What this box can and cannot do
The Beelink U55 is **2 cores and 8 GB of memory** (UNVERIFIED: check the label or `free -h`).
- **Can:** be a **hub**: dashboard, phone app, the gateway, backups, and a handful of light apps at once (a notes app, a budget app, a file share, a password vault).
- **Cannot (yet):** run **virtual machines** (the machines feature wants an x86 hub with hardware virtualization and about 15 GB of memory; the box says so itself and refuses with the reason), heavy apps that need several GB each (photo machine-learning, local AI models), or many apps together. Start with two or three apps and watch `free -h`.
- **Expect:** a few minutes for the first boot, a slow first start of each app (k3s pulls images over your internet).

## 1. Download and write the stick
From the newest `dev-*` pre-release ([the list](https://github.com/onemindos/ONEMINDOS/releases)): `onemind-installer-amd64-<version>.img.xz` and `SHA256SUMS`. It is a DEV BUILD with throwaway keys. Check it (`shasum -a 256 -c SHA256SUMS --ignore-missing`), then write it with [balenaEtcher](https://etcher.balena.io/) (it reads `.img.xz` directly: pick the file, pick the stick, **Flash**) or, if you prefer a terminal, `xz -dc onemind-installer-*.img.xz | sudo dd of=/dev/rdiskN bs=4m` (replace `N` with the stick's number from `diskutil list`; the wrong number erases the wrong disk).

## 2. Boot the Beelink from it
1. Plug in the stick, the network cable, monitor and keyboard. Power on and tap **F7** (the boot menu) as it starts. Choose the **USB** entry.
2. If it will not start, open the firmware setup (**Del** at power-on) and switch **Secure Boot off**. Dev builds are unsigned.
3. The screen lists the disks it can install to. It does not offer the stick, read-only disks or disks smaller than 32 GiB.

## 3. Install
Pick the internal disk, choose the role **`setup`** (decide later in the browser) or **`hub`**, type **`ERASE`**. It writes, verifies (`verified sha256=…` appears) and reboots. Remove the stick when it says so.

You can also drive the installer from your Mac: open `http://onemind-installer.local:8080/` while the stick is running. That page needs the **8-digit code** shown on the Beelink's screen. Only do this on a network you trust.

## 4. First boot and setup
After the reboot the first start takes a few minutes. Then, from your Mac on the same network, open <http://onemind.local:8080/>, choose **hub** (skip this if you chose `hub` in the installer; then the owner token is on the Beelink's screen instead), and **copy the owner token** the page shows once. Reload after a minute: the dashboard. Sign in with the token.

## If it does not work
| You see | Try |
|---|---|
| The Beelink boots straight to the old system | F7 again and choose the USB entry; check Secure Boot is off |
| No disks offered | the internal disk is under 32 GiB, mounted, or read-only; use a larger disk |
| `onemind.local` not found | use the Beelink's address (shown on its screen, or in your router's device list) with `:8080` |
| It says the check failed | do not use it; write the stick again and keep the log (`photograph the screen`) |
