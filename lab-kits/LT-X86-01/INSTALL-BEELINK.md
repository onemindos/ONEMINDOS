<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-X86-01, part 1 · Install OneMind on the Beelink from the installer stick

**Status:** kit-ready (blocked: founder-hardware) · **Time:** about 45 minutes · **Serves:** #234 (M-LIVE: OneMind running live on real hardware), D-007, brief 30 B2 · **Then:** the RAUC rollback tests in [README.md](README.md) (those use a different, test-only image; do this install first)

> **Explain it like I'm the founder.** You write one **installer stick** on your Mac. You boot the Beelink from it, pick the internal disk, type `ERASE`, and the stick copies OneMind onto the disk, checks every byte, and restarts into OneMind. Then you open the dashboard from your Mac and sign in with a one-time **owner token** (a long secret string that proves you own this box). **This erases the Beelink's internal disk.** Nothing here has run on a real Beelink yet: every "expect" below is what the build notes and the QEMU tests say, so write down anything that differs.

## What you need
- A **4 GB or larger USB stick** you can erase (the installer is about 1 GB).
- The Beelink, a monitor (HDMI), a USB keyboard, and a **wired** network cable to the same router your Mac is on.
- Your Mac, with the dev release files from the newest `dev-*` pre-release on <https://github.com/onemindos/ONEMINDOS/releases>: `onemind-installer-amd64-<version>.img.xz` and `SHA256SUMS`.
- The internal disk must be **32 GiB or larger** and have nothing you want to keep.

## A. Write the stick (Mac)
1. Check the download. In the folder with the files:
   ```bash
   shasum -a 256 -c SHA256SUMS --ignore-missing
   ```
   Expect `onemind-installer-amd64-<version>.img.xz: OK`. Anything else: download again, do not use it.
2. Plug in the stick and find its number:
   ```bash
   diskutil list external
   ```
   Find the stick by its size and name. It is `/dev/diskN` (for example `disk4`). **Your Mac's own disk is `disk0`/`disk1`; never use those.**
3. Make the safety check ask you twice (from the repo root; it writes nothing):
   ```bash
   sh lab-kits/common/check-target-disk.sh /dev/diskN
   ```
4. Write it. Easiest: open [balenaEtcher](https://etcher.balena.io/), pick the `.img.xz` file (it reads it directly), pick the stick, **Flash**. Terminal alternative:
   ```bash
   diskutil unmountDisk /dev/diskN
   xz -dc onemind-installer-amd64-<version>.img.xz | sudo dd of=/dev/rdiskN bs=4m
   diskutil eject /dev/diskN
   ```
   `rdiskN` (with the `r`) is the same stick, faster. Takes a few minutes. macOS may say "disk not readable" afterwards: that is normal (it cannot read Linux partitions). Click **Eject**.

## B. Beelink settings (BIOS / UEFI)
Power on and tap **Del** to open the firmware setup. Set only these, change nothing else:

| Setting | Value | Why |
|---|---|---|
| Secure Boot | **Disabled** | Dev builds are not signed (BD-08). LT-X86-03/04 test Secure Boot later. |
| Boot mode | **UEFI** (not Legacy/CSM) | The image boots with GRUB EFI. |
| USB boot | Enabled | To start from the stick. |

Write down the BIOS version (shown on the setup's first page) for the results. Save and exit (usually **F4**). If the menu looks different, photograph each page.

## C. Boot the installer
1. Plug in the stick, the network cable, monitor and keyboard. Power on and tap **F7** (boot menu). Choose the entry that names the **USB** stick (maybe "UEFI: <stick brand>"). If F7 does nothing, try **F12** or **Esc**, or set the stick first in the setup's Boot tab.
2. GRUB shows for 3 seconds, then Linux starts. No login prompt appears: the installer menu runs by itself.
3. The screen shows `OneMind installer: writes OneMind <version> (x86_64-efi) to a disk of this computer.`, a LAN address line, and numbered disks, for example `[1] nvme0n1 ...`. The stick, read-only disks, mounted disks and disks under 32 GiB are listed as `not offered`.
   - Your internal disk is missing: it is under 32 GiB or in use. Photograph the screen and stop.

## D. Install
1. Type the number of the **internal** disk (check the size and model against the label, not the stick), press Enter.
2. Role: type `hub` (this box is the owner's main box; it then shows the owner token on its own screen), or `setup` to choose in the browser instead. The kit assumes **`hub`**. Name shown in the dashboard: press Enter for `OneMind`.
3. A red-bordered warning names the disk. Type `ERASE` and Enter. Anything else writes nothing.
4. Wait about 5 to 15 minutes. You will see progress lines, then `verified sha256=...`, then it counts down to a reboot. **Remove the stick when it says so** (if you forget, the firmware entry it set still boots the new disk).

## E. First boot and owner sign-in
1. The first start takes **a few minutes** (it makes the box's own certificate authority and starts k3s and the gateway). The screen prints `ONEMIND-FIRSTBOOT:` lines and, for a hub, a line starting **`ONEMIND OWNER TOKEN:`** followed by the token. **Photograph the screen or copy the token now.** It is shown on the console only and the box stores just a hash, so it cannot be shown again.
2. It also prints the box's LAN address and the box CA fingerprint. Note the address.
3. On your Mac (same network), open the address the Beelink's screen prints. For a `hub` that is **`https://onemind.local`** (or `https://<beelink-ip>` if the name is not found; look the IP up on the screen or in your router's device list). Use `https`, not `http`: for a hub, plain HTTP on `:8080` listens on the box itself only, so `:8080` from the Mac is refused. If you chose `setup`, open `http://onemind.local:8080/` (or `http://<beelink-ip>:8080/`) instead, pick **hub** on that page and copy the token it shows once. If the screen prints a different URL from any of these, use the one on the screen.
4. After about a minute the dashboard loads. For a hub the browser will show a certificate warning: that is the box's own CA (check the fingerprint against the screen) and expected for now; continue past it.
5. Sign in with the owner token.
6. Never paste the token into the results file, a chat, or a commit.

## F. What "pass" looks like
Mark each line. Everything must be true without touching the Beelink's keyboard after the install reboot.

| # | Check | Pass looks like |
|---|---|---|
| 1 | Stick verified on the Mac | `shasum` printed `OK` |
| 2 | Stick booted | Installer menu appears with the version and the disk list |
| 3 | Install wrote and checked | `verified sha256=...` on screen, no `FAILED` |
| 4 | Box restarted into OneMind alone | After the stick was pulled, it booted the internal disk and printed `ONEMIND-FIRSTBOOT:` lines |
| 5 | Owner token shown | `ONEMIND OWNER TOKEN:` line seen once |
| 6 | Dashboard reachable from the Mac | The dashboard loads within 10 minutes of the reboot |
| 7 | Owner sign-in works | The token signs you in and the Home screen shows this box as online with the role `hub` |
| 8 | Survives a power cycle | Hold the power button, power on again, wait 5 minutes: the dashboard loads and the same token still signs in (no new token printed) |

**PASS** = all 8. **FAIL** = any of 3 to 8 not met after one clean retry. Record exactly which step and photograph the screen. A failure at 2 only (boot menu or Secure Boot trouble) is **BLOCKED** (note the firmware's behaviour), not a software FAIL.

## G. If it does not work
| You see | Try |
|---|---|
| Boots straight to the old system | F7 again and choose the USB entry; check Secure Boot is off and boot mode is UEFI |
| Black screen after GRUB | Wait 2 minutes; then photograph it and note the BIOS version (BLOCKED, with the screenshot) |
| No disks offered | The internal disk is under 32 GiB, mounted, or read-only |
| `onemind.local` not found | Use the URL printed on the Beelink's screen, or `https://<beelink-ip>` for a hub (`http://<beelink-ip>:8080` only for the `setup` path); make sure Mac and Beelink are on the same network |
| `FAILED: ...` or "check failed" | Do not use the disk. Write the stick again, retry once, keep the photo |
| Token missed | Re-run the install (the box stores only a hash); this is a test box |

## H. Record
1. Fill [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md) using [RESULT-INSTALL.md](RESULT-INSTALL.md) in this folder as the filled-in layout, saved as `research-output/evidence/lab/founder-hardware/LT-X86-01-install.md`.
2. No serial numbers, MAC addresses, your home IP, the owner token or home paths in anything you commit. Run `sh lab-kits/common/redact.sh` over any pasted log and `make hygiene` before committing.
3. Keep the stick: it works on the next box. When you are done testing, you can reinstall over the same disk or leave it.
