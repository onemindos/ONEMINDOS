<!-- SPDX-License-Identifier: Apache-2.0 -->
# USB installer for x86_64 PCs (`installer-x86_64`)

**Serves:** the founder's request of 2026-11-12 (every deployment boots straight into OneMind), D-007, brief 30 B2. **Tests:** `test/qemu/CRITERIA-INSTALLER.md` (I1–I5, pre-registered), `test/unit/test_installer.py`.

> **Explain it like I am the founder**
> Flashing a disk image with a USB adapter works, but a Beelink's NVMe drive sits inside the box. The installer is the usual way around that (Ubuntu, Proxmox and Home Assistant OS ship one): you write **one stick**, boot the PC from it, pick the internal disk, type `ERASE`, and the stick copies OneMind onto the disk, checks every byte, and restarts into OneMind. The stick itself is never changed, so it works again on the next box.

## Use it

1. `make installer BOARD=installer-x86_64` → `out/installer-x86_64/onemind-installer-amd64-<version>.img` (about 1 GB of data; write it to any 4 GB+ stick with balenaEtcher, Raspberry Pi Imager or `dd`).
2. Boot the PC from the stick (Beelink: F7 at power-on for the boot menu). Secure Boot must be off for dev builds.
3. The screen (and the serial console) shows the disks it can install to. The stick itself, read-only disks, mounted disks and disks smaller than the image (32 GiB) are listed as "not offered".
4. Pick the disk, pick the role (`hub`, `worker`, `leaf`, or `setup` to choose later in the browser), type **`ERASE`**. Anything else writes nothing and goes back to the menu.
5. It writes, verifies, sets the role, points the firmware's next boot at the new disk and reboots. Pull the stick when it says so (if you do not, the firmware boot entry it set still boots the disk).

From another computer on the same network, `http://onemind-installer.local:8080/` (or the address the menu prints) shows the same choice. An install from that page needs the **8-digit one-time code** shown on the PC's screen; five wrong codes turn the page's installs off until the stick is rebooted. Anyone on your LAN can otherwise see the page, so only boot the installer on a network you trust.

## What it checks (why the install can be trusted)

| Step | Check |
|---|---|
| Before writing | The compressed image on the stick has the sha256 recorded when the stick was built (`payload.json`); build.sh only packs an image whose sha256 matches the image build's `SHA256SUMS`. |
| While writing | The decompressed stream must be exactly the image size and hash to the image's sha256. All-zero blocks are **zeroed on the disk** (`BLKZEROOUT`), never skipped, so old data cannot survive inside the new filesystems. |
| After writing | The disk's cache is dropped and the whole image range is read back; its sha256 must equal the image's again. The console prints `verified sha256=…`. |
| Then | The GPT backup header moves to the real end of the disk and `onemind-data` grows to fill it (`e2fsck` + `resize2fs`; if that fails the box still works at 32 GiB and a warning is printed). |
| Role | `onemind.conf` on the new disk's ESP gets `role = …` and is read back; `onemind-firstboot` applies it at the first boot (docs/leap/core/IMAGES.md §3). |

## What is on the stick

| Part | Contents |
|---|---|
| ESP (FAT, volume id `4F4E-4955`, not the images' `4F4E-454D`) | GRUB built from the stick tree's own `grub-efi-amd64-bin`, its `grub.cfg`, the kernel and initramfs, `README.txt` |
| `onemind-installer-root` (ext4, mounted read-only; `/var` and `/tmp` in RAM) | Debian 13 from the same pinned snapshot as the images (`os/rootfs/debian.args`): kernel, systemd, `gdisk`, `e2fsprogs`, `mtools`, `zstd`, `efibootmgr`, Python 3 for the menu and page, avahi. `/usr/share/onemind-installer/payload/`: the zstd-compressed `onemind-x86_64-efi-<version>.img` and `payload.json` |

No root password and no login: tty1 and the serial console run the installer menu instead of a login prompt. No keys are made or carried; the image inside is already signed by its own build.

## Files

| File | What |
|---|---|
| `board.yaml` | arch, target board (`x86_64-efi`), GRUB target, ESP volume id |
| `Containerfile` | the live tree (Debian 13, pinned base digest and snapshot) |
| `build.sh` | tree + image → stick image (GPT: ESP, read-only root); runs in the tools container |
| `rootfs/usr/lib/onemind-installer/onemind_installer.py` | menu, LAN page, install + verify |
| `rootfs/usr/lib/systemd/system/` | `onemind-installer@tty1`, `@ttyS0` (menus, one shared lock) and `onemind-installer-web` |

## Not done yet (tracked)

- **arm64 installer:** the Containerfile and program already take `arm64` (kernel and GRUB packages switch on `TARGETARCH`); a `installer-arm64` board.yaml with `target_board: arm64-efi`, `grub_target: arm64-efi`, `efi_binary: BOOTAA64.EFI`, `console=ttyAMA0` and an AAVMF run of the battery are still to do.
- **Secure Boot:** the stick's GRUB is unsigned, like the images' dev GRUB (BD-08: signed shim/UKI arrives with B4.4).
- **Real hardware:** run on the Beelink as part of kit LT-X86-01 (QEMU results only so far).
- **Whiptail-style screen:** the menu is plain text on every console, which is also what the QEMU battery drives.
