<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind on your Mac (Apple Silicon, UTM)

**Time:** about 20 minutes plus first boot. **You need:** a Mac with an M-series chip, 8 GB of free disk, and [UTM](https://mac.getutm.app/) (free from its website; the App Store copy costs money for the same program).

> **Explain it like I'm the founder.** *UTM* runs a second computer inside a window on your Mac. We give it OneMind's disk (`.qcow2` is just the disk-file format UTM understands) and it boots like a real box. The Mac's own chip is arm64, so we use the arm64 build and it runs at full speed with no emulation.

> **UNVERIFIED until you follow it:** the screen names below are UTM 4.x; the boot, the network and the setup page have passed in QEMU only (the same firmware and virtio devices), not in UTM itself. If a name differs, tell us which.

## 1. Download
From the newest `dev-*` pre-release ([the list](https://github.com/onemindos/ONEMINDOS/releases)): `onemind-arm64-efi-<version>.qcow2` and `SHA256SUMS`. It is a DEV BUILD with throwaway keys. In Terminal: `cd ~/Downloads && shasum -a 256 -c SHA256SUMS --ignore-missing` must say `OK`.

## 2. Make the machine in UTM
1. **Create a New Virtual Machine → Virtualize → Other.**
2. **Boot Device: None** (we bring our own disk), no ISO. Hardware: **Memory 8192 MB** (4096 works for a look), **CPU cores 4**. Storage: accept any size; we delete it next.
3. Name it `OneMind` and **Save** (do not tick "open settings" yet; open them from the sidebar after saving).
4. In the machine's settings:
   - **Drives**: delete the default blank drive. **New → Import…** and pick the `.qcow2`. Interface **VirtIO**.
   - **QEMU → UEFI Boot** must be **on** (it is by default for "Other"). OneMind's disk boots with GRUB's EFI loader; with UEFI off you get a black screen.
   - **Network → Network Mode: Shared Network** (the default). The Mac reaches the box on a private address and the box reaches the internet. For the box to be seen by your phone on the home Wi-Fi, choose **Bridged (Advanced)** instead and pick your Wi-Fi/Ethernet; bridging needs your Mac's permission prompt.
   - **Serial** (optional): **New → Serial → Built-in terminal**. The box's first-boot messages, including the owner token, go to the serial console as well as the screen.
5. **Secure Boot is off** (dev builds are unsigned). Leave UTM's "Secure Boot" box unticked.

## 3. First boot
Press play. Within about 10 minutes the screen shows `ONEMIND-FIRSTBOOT: not configured; waiting for the setup wizard at http://onemind.local:8080/`. The first start of every service is slow; the `32 GiB` disk grows on its own.

## 4. Open the setup page
On the Mac, open <http://onemind.local:8080/>. If the name does not resolve (mDNS is sometimes blocked), find the box's address on the console screen or in Terminal with `arp -a | grep -i '192.168.64'` and open `http://<that address>:8080/`.

Choose role **hub**, name it, submit. **Copy the owner token** the page shows once (it is also on the serial console). A minute later reload: the dashboard is there. Sign in with the token.

## 5. Turning it off and starting over
- Shut down from the dashboard or the console; UTM's stop button is a power cut (the box recovers, that is what the A/B design is for).
- To start from zero, delete the VM in UTM and re-import the file. The disk file is changed by the VM, so keep the download if you want a clean copy.

## If it does not work
| You see | Likely cause | Try |
|---|---|---|
| Black screen, no text | UEFI off, or a Secure Boot box ticked | settings above |
| `onemind.local` not found | mDNS blocked or Bridged mode on a guest Wi-Fi | use the IP address |
| Page loads, no token | you closed the page after the first view | the token is on the serial console; otherwise re-import the disk and start again (nothing is lost, the box is new) |
| Dashboard says not ready | services still starting | wait 2 more minutes |

Build it yourself instead of downloading: `make rootfs BOARD=arm64-efi && make image BOARD=arm64-efi && make convert BOARD=arm64-efi` (needs Docker; see [mac-dev-loop](../learning/mac-dev-loop.md)). The qcow2 lands in `out/image-arm64-efi/`.
