<!-- SPDX-License-Identifier: Apache-2.0 -->
# Storage housekeeping: TRIM, disk warnings, safe removal (wave 2, P-10)

Build step: wave 2, P-10 of the native-features audit (`NATIVE-FEATURES-AUDIT.md` section 3), stacked on Step 2 (#1088, disk tools) and Step 2b (#1115, box care). Decisions D-027 and D-028: a change to the OS is an owner action through the approval queue; agents and the CLI only ask. Proof: first-boot checks F25, F25b, F25c (`test/qemu/CRITERIA-FIRSTBOOT.md` section 19).

## What the owner gets

| Where | What |
|---|---|
| Storage screen | "SSD housekeeping (TRIM)": weekly TRIM on or off, last TRIM, how much it freed, next TRIM. "Disk health warnings": what smartd said. "USB drives": a **Safely remove** button for each drive the box is not using. |
| Notifications | One alert per smartd warning (warning or critical), with a link to Storage. An owner clears it. |
| CLI | `onemind storage trim-status` (everything above), `onemind storage eject sdb` (files the request and prints the approval id). `--json` on both. |
| API | `GET /v1/storage/housekeeping` (owner), `POST /v1/storage/removable/{name}/eject` (files the `storage.eject` action). |

## How it works, in plain words

- **TRIM** tells an SSD which blocks are free, so it stays fast. `fstrim.timer` (from #1115) already runs it weekly on `/data`. The host service (it is root; the gateway is not) reads `systemctl show fstrim.timer` and `fstrim.service` and the service's own log line for the bytes. A box where TRIM never ran says so; nothing is invented.
- **smartd** is the disk watcher from the `smartmontools` package. #1088 masked it because nothing read its output. Now `/etc/smartd.conf` has one line: scan every disk, never wake a sleeping one, short self-test nightly, long on Saturdays, warn at 60 and 70 C (the limits the Storage screen already uses), and **mail nobody**. `/etc/default/smartmontools` adds `-q nodev0`, so on a box with no SMART disk (a virtual machine) smartd exits cleanly instead of showing `failed`. Instead smartd runs `/usr/lib/onemind/smartd-notify`, which appends one JSON line to `/var/lib/smartmontools/onemind-alerts.jsonl`. That directory is a bind mount from `/data/state/var-lib-smartmontools`, so warnings survive reboots and A/B updates (the root is read-only). The script folds smartd's daily reminders of one problem into one line (the id is first-seen time, device and kind).
- **Into Notifications.** The host service serves the feed on its local socket. The gateway's `storage-care` pass reads it every minute and raises one `storage.smart.warning` or `storage.smart.failing` event per new line, remembering what it told (the storage service's observation table), so a restart never repeats an alert.
- **Safely remove.** A drive is "removable" if `lsblk` says it is a whole disk on the USB bus or flagged removable. It is "in use" if anything on it is mounted at `/`, `/data`, `/boot`, `/usr`, `/var`, `/home`, `/etc`, `/opt`, `/srv` or under them, and then it has no button. The gateway checks, files a `storage.eject` action, an owner approves, and the host service checks **again** before it runs `udisksctl unmount` on each partition and `udisksctl power-off` on the disk. A passkey is not required: nothing about access changes, and the owner names the drive.

## What a VM cannot prove (the Dell all-in-one must)

- A real warning: `smartctl -s on -t short /dev/sdX` on the SSD, or a disk with a failing attribute; or run `smartd -q onecheck` with a `-M test` line to see smartd run the script. Check the line lands in the feed and the alert appears in Notifications.
- A real eject: plug in a USB stick, `onemind storage trim-status` lists it, `onemind storage eject sdX`, approve it, the stick's light goes out and `lsblk` no longer lists it. This also proves that `udisksctl` works from inside the host service's sandbox (`ProtectSystem=strict`, almost no capabilities); if it does not, the operation fails with a plain message and nothing is half-done.
- TRIM on the real SSD: `systemctl start fstrim.service`, then the Storage screen shows the bytes.
- Nothing in the QEMU battery attaches a USB device: F25 proves the plumbing (config parses, script, feed, bind, host socket answers, the root disk is refused), the Go and Python tests prove the rest with recorded tool output.

## Safety details added after review
- The eject request carries the drive's **serial number** (from `lsblk`) when it reports one. If another stick comes up as `/dev/sdb` between the request and the owner's approval, the gateway (at approve) and the host (twice) refuse with `drive_changed`. A drive that reports no serial is still bound to its kernel name only.
- A **swap area** on a USB disk (`lsblk` shows its mount as `[SWAP]`) counts as in use, like `/data`.
- Each `udisksctl` call has its own 30 s limit, so a hung udisks fails the eject instead of leaving it `running`.
- Still open, for the btrfs `/data` work: with a multi-device btrfs, `lsblk` shows the mount on only one member, so a USB member would look ejectable. That work must add a check on the filesystem's device list before a multi-device `/data` is allowed.
