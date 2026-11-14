<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 02: inside the umbrelOS 2.0.1 images

**For:** Zeus · **Date:** 2026-11-14
**Status:** founder-requested study of a competitor's published images. It adds no decision and copies no umbrelOS code: `umbreld` declares the PolyForm Noncommercial License 1.0.0 in its `package.json`, so it is study-only (see [`docs/ADR-001-foundation.md`](../../ADR-001-foundation.md)).
**Feeds:** the image line ([`docs/learning/07-image-ab-updates-health-gate.md`](../07-image-ab-updates-health-gate.md), `os/`), the downloads page (`site/src/pages/downloads.astro`), decision D12 in [`docs/leap/LANES.md`](../../leap/LANES.md) (ADR-001 wording: Rugix vs RAUC).

---

## 1. What was looked at, and how
The four files from umbrel.com's downloads page, version 2.0.1:

| File | What it is | Size |
|---|---|---|
| `umbrelos-amd64.img.xz` | disk image for Intel/AMD, run from a USB drive | 1.5 GB compressed, 8.1 GB unpacked |
| `umbrelos-amd64-usb-installer.iso` | installer that writes umbrelOS to an internal drive; also the VM download | 1.8 GB |
| `umbrelos-pi.img.zip` | disk image for Raspberry Pi 5 and 4 | 1.3 GB compressed, 6.3 GB unpacked |

The SHA-256 of each file matched the prefix shown on the downloads page. Nothing was booted or run. The partition tables were read from the raw bytes, the FAT boot partitions were mounted read-only, and the ext4 system partition was read with `debugfs` inside a throwaway Debian 13 container.

## 2. What we found

### Same base as us
`/usr/lib/os-release` in the system partition says **Debian GNU/Linux 13 (trixie)**. umbrelOS ships on the same base OneMind chose in D-007.

### A/B updates with Rugix
The images use **Rugix** for A/B updates (the boot files are in a `rugpi/` folder, the root runs `init=/usr/bin/rugix-ctrl`, and the config is in `/etc/rugix/`). Rugix is the tool ADR-001 named "the Umbrel-proven choice"; this confirms that claim with evidence.

| Partition | amd64 image | Pi image |
|---|---|---|
| 1 | EFI system, 256 MiB (GRUB + Rugix boot settings) | EFI system, 256 MiB (Pi `autoboot.txt`) |
| 2 | boot A, 512 MiB ext4 (kernel + initrd) | boot A, 128 MiB FAT (Pi firmware, kernel) |
| 3 | boot B, 512 MiB, empty | boot B, 128 MiB, empty |
| 4 | system A, 6.6 GiB ext4 | system A, 5.4 GiB squashfs (read-only) |

The second system slot and the data partition are not in the image. An empty `.rugix/bootstrap` marker on the first partition makes Rugix create them on first boot, sized to the real disk. That keeps the download small.

How each board picks a slot:
- **PC (amd64):** GRUB reads two copies of a settings file, each checked with a SHA-1 sum, plus a "boot the spare once" flag. A corrupt settings file is ignored instead of bricking the boot.
- **Raspberry Pi:** the Pi firmware's own **tryboot** feature (`tryboot_a_b=1`): the next boot tries partition 3 once; if it is not confirmed, the Pi falls back to partition 2.

### Writable data is bind-mounted from `/data`
The system slot is never written to. `/etc/fstab` bind-mounts the writable parts from the data partition: logs, the Docker store, `/home`, the time-sync state and the Kopia backup store.

### If the data disk fails, it still boots
`/etc/rugix/system.toml` sets `fail-on-mount-error = false` and explains why: if the data partition cannot be mounted, the box boots with temporary state and `umbreld` switches to a **recovery mode**, instead of a box that cannot boot at all.

### The rest of the stack
- Apps run on **Docker + containerd**. OneMind uses k3s.
- Backups use **Kopia**. OneMind uses restic.
- `umbreld` is a Node.js program in `/opt/umbreld`, version 2.0.1.
- The installer ISO is a small **NixOS** live system (Linux 6.18) that carries the full `umbrelos-amd64.img.xz` inside it and writes it to the chosen disk. The same ISO is offered for virtual machines.

### The downloads page pattern
Each row on their page shows the board, how it runs ("from a USB drive" or "install to an internal drive"), the file name, its size, a shortened SHA-256, a stable button and a beta button, and a link to that board's install guide.

## 3. What this means for OneMind
These are observations, not decisions. Each points at the build step it could feed.

| Observation | OneMind today | Possible use |
|---|---|---|
| Debian 13 under a consumer home OS | D-007, same base | Evidence that D-007 is sound for this product class |
| Rugix A/B at Umbrel; RAUC A/B at Home Assistant OS | RAUC is built and battery-tested in QEMU | Evidence for D12 (ADR-001 wording). It reopens nothing: both tools are proven, and the repo is on RAUC. |
| Second slot and data created on first boot | [`os/boards/x86_64-efi/layout.yaml`](../../../os/boards/x86_64-efi/layout.yaml) lays out the whole 32 GiB disk up front: both 10 GiB system slots, a recovery partition and data | Growing on first boot would shrink the download a lot; a candidate item for the image line |
| Data mount failure boots into recovery mode | [`os/rootfs/layers/base/etc/fstab`](../../../os/rootfs/layers/base/etc/fstab) mounts `/data` without `nofail`, so in standard systemd behaviour a failed data disk stops the boot in emergency mode: a console shell, with no network page or phone alert. After an update the health gate's G5 check ([`os/gate/onemind-k3s-check`](../../../os/gate/onemind-k3s-check)) does catch an unwritable `/data`. The recovery partition is empty in v0 (`os/assemble/assemble.py`). Not tested on a booted image | A gap worth a backlog item for the image line: boot to a minimal recovery service that says "data disk failed" on the network and phone, plus a QEMU battery test that detaches the data disk and expects that screen |
| One installer ISO serves USB install and VMs | `os/boards/installer-x86_64` exists | Same pattern; nothing to change |
| Downloads page with stable and beta per board | `downloads.astro` lists artefacts with checksums and a signature check | Consider a beta channel column once there is a signed release (F-27) |

## 4. Words used
- **Partition:** a fixed slice of a disk with its own filesystem.
- **EFI system partition:** the small FAT partition a PC's firmware reads to find the bootloader.
- **ext4 / FAT / squashfs:** filesystem formats. squashfs is compressed and read-only.
- **Bind mount:** making a folder from one place appear at another path.
- **tryboot:** a Raspberry Pi firmware feature that boots a different partition once, for testing an update.
- **NixOS:** a Linux distribution built from a single declarative config; umbrelOS uses it only for its installer.

## 5. Check yourself
1. Why does umbrelOS leave the second system slot out of the download?
2. What happens on a umbrelOS box whose data disk fails, and why is that better than refusing to boot?
3. Name one thing umbrelOS and OneMind share, and two things they do differently.
