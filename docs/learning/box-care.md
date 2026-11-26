<!-- SPDX-License-Identifier: Apache-2.0 -->
# Box care: what keeps a 24/7 OneMind box healthy (Step 2b)

Build step: Step 2b of the Debian bones (founder-approved 2026-11-25), feeding the box check-up in Settings > Care (#505, FD-08). Proof: first-boot check F24 (`test/qemu/CRITERIA-FIRSTBOOT.md` section 18). All of it is plain Debian 13 packages from the pinned snapshot.

## What is on the box and why

| Piece | What it does, in plain words | How we set it |
|---|---|---|
| **fwupd** | Updates the firmware inside the machine (BIOS, SSD, dock) using LVFS, the Linux Vendor Firmware Service, a public catalogue that vendors such as Dell publish to. | The daily metadata download (`fwupd-refresh.timer`) is **masked**: the box never contacts LVFS or flashes anything by itself. The owner starts a refresh and approves each update. `fwupd-signed` (x86 only) is the signed UEFI program that capsule updates (the way a PC BIOS is updated from the OS) need under Secure Boot. Metadata and cache live on `/data` (`/var/lib/fwupd`, `/var/cache/fwupd`). |
| **fstrim.timer** | Tells the SSD which blocks are free (TRIM), weekly, so it stays fast and wears evenly. | One choice for ext4 and btrfs: the weekly timer, limited to `/data` by a drop-in, because the slot root is read-only (trimming it would fail every week). If `/data` becomes btrfs, its kernel already discards asynchronously (`discard=async` is the default since kernel 6.2), so the weekly run is a harmless catch-up and no mount option has to change. Open point: an encrypted `/data` (LUKS) passes TRIM only when opened with `--allow-discards`; `data_encrypt.py` does not today. That trades a little privacy (which blocks are empty) for SSD health, so it stays a founder decision. |
| **lm-sensors** | The `sensors` command: CPU, board and fan readings. | Package only. The hottest thermal zone is already read by `internal/detect/metrics.go`. |
| **thermald** | Intel's thermal daemon: it throttles the CPU before the machine overheats. | x86 package list only (it does not exist for arm). Debian's unit already refuses to start in a VM. |
| **udisks2** | Lists USB drives and mounts them on request. | No polkit and no desktop helper (`gvfs`, `udiskie`) is installed, so nothing mounts a plugged-in drive and only root, the host helper acting for the owner, may mount. A udev rule sets `UDISKS_AUTO=0` so any future client agrees. State: `/var/lib/udisks2` on `/data`. |
| **Hardware watchdog** | A timer chip that resets the machine if the OS stops petting it. | `RuntimeWatchdogSec=30s` already comes from the base layer (all x86 boards); the rpi5 board overrides it with 10 s. Nothing new was needed. |
| **rasdaemon** | Writes memory (ECC), PCIe and CPU machine-check errors to a database: the "is this hardware dying" log. Read it with `ras-mc-ctl --summary` and `--errors`. | Enabled; database in `/var/lib/rasdaemon` on `/data`, so it survives reboots and A/B updates. |

State rule: the root is read-only, so each of these four directories is a bind mount from `/data/state/...` (fstab, `onemind-data-layout.service`, and the recovery check waits for them).

## What a VM cannot prove (the Dell all-in-one must)

Run on the real box after install: `fwupdmgr get-devices` lists real devices, `fwupdmgr refresh` (owner-run) fetches LVFS and `fwupdmgr get-updates` answers; `sensors` shows chips and `systemctl status thermald` is active; plug in a USB stick: it shows in `udisksctl status`, is not mounted, and mounts only on `udisksctl mount`; `ls /dev/watchdog*` exists (`iTCO_wdt` on Intel) and `echo c > /proc/sysrq-trigger` or a frozen PID 1 resets the box in about 30 s; `ras-mc-ctl --status` shows the EDAC driver loaded, and `ras-mc-ctl --summary` works; `systemctl start fstrim.service` reports trimmed bytes on the real SSD.

## Next step (not done here)

Surface these in the check-up (#505): temperature already exists, `ras-mc-ctl --summary` and `fwupdmgr get-updates --json` need a read-only action in the host helper (`internal/host`) so the gateway can show "firmware update available" as an approval request. Until then they are CLI-only over SSH.
