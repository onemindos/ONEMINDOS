<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-X86-07459 · Hardware test checklist for the Dell all-in-one (after install)

**Serves:** #234 (M-LIVE), the daily hub. **Run after:** [the install guide](../../docs/learning/dell-aio-install-guide.md). **Script:** [`scripts/hw-check.sh`](../../scripts/hw-check.sh) (read-only; proven only against stubs in `test/unit/test_hw_check.py`, **not yet run on the Dell**).
**Then:** the [file-system conditions](../../docs/learning/dell-aio-file-conditions.md) before real files go on the box.

> **In plain words.** This is the "does every part of the Dell work" list. One script asks the box about each part and prints a short report. It only looks: it never changes a setting, mounts a disk, scans for devices, pairs anything, updates firmware or prints your secrets. You then do the few things only a person can (plug a stick in, speak into the room, press a key) and write down what happened.

## 1. Run the script
From the Mac, as the owner (not root; no files are copied to the box):
```bash
ssh <owner>@onemind.local 'sh -s' < scripts/hw-check.sh | tee hw-check.txt
```
- It ends `N checks: ... passed, ... need a look (WARN), ... failed, ... could not be checked (SKIP)`. Exit code 1 means at least one FAIL.
- **SKIP** means the script could not look: a tool is not on this image yet, or it needs root. Re-run with passwordless sudo for the root-only reads (SMART, btrfs, snapper): `ssh <owner>@onemind.local 'HW_CHECK_SUDO=1 sh -s' < scripts/hw-check.sh`. It uses `sudo -n` and never asks for a password.
- **PASS** needs positive evidence: a line in the tool's real output that shows the good state. Empty output, an error or a sudo password prompt gives SKIP or WARN with the first line of what the tool said, never PASS.
- Serial numbers, MAC and IP addresses, e-mail addresses, home paths and network names are masked before anything prints. Still read `hw-check.txt` once by eye before filing it.
- If the image has no `sh -s` over SSH for your user, run it on the Dell's own console instead: `sh scripts/hw-check.sh`.

## 2. What each line means and the human step that goes with it
| Check (script line) | What the script reads (no changes) | Pass looks like | Human step and what to write down |
|---|---|---|---|
| Wi-Fi | `nmcli` device list and radio state, no network names | adapter found, state shown | Join a network from the dashboard or `nmtui`, note whether it stays up after a restart. Wired is the supported path for now |
| Firmware devices | `fwupdmgr get-devices` (lists only) | N devices | Note which parts have updates; do not apply any until an update plan exists |
| Sensors | `/sys/class/hwmon` names and the hottest temperature | chips found, hottest under 90 C | Note idle and busy temperature; an all-in-one runs hot in a closed space |
| USB stick | `lsblk`: a USB disk seen and **not mounted** | `1 seen and not mounted` | Plug in a stick, run again. The box must not auto-mount strangers' drives |
| Watchdog | the device file **exists** (it is never opened, opening would arm it) | `/dev/watchdog present` | WARN here is a real finding for the hang-recovery story |
| Sound | PipeWire sinks (`wpctl`), or `pactl` | at least one output | Play a sound if a tool exists; note speakers and headphone jack. SKIP means the image ships no audio stack yet |
| Bluetooth | `/sys/class/bluetooth`, `rfkill` state | controller present and not blocked | Nothing is scanned or paired. Pair a device by hand and note it |
| Printers | `lpstat -v` (existing printers only), CUPS state | printer(s) with an IPP or dnssd address | A WARN with no printer is fine if you own none. Print a test page driverless if you do |
| Video (VA-API) | `vainfo` profiles | H.264 supported | Play a video if a player exists; note any tearing on the built-in panel |
| Console keyboard | keyboard devices with a console handler, console keymap | at least one keyboard, keymap shown | Type at the Dell's own screen; check special keys and the layout |
| TPM 2.0 | `/sys/class/tpm/tpm0` version | present | WARN: turn the TPM on in the BIOS (D-020) |
| Disk health | `smartctl -H` per internal disk (verdict only) | SMART says healthy | A FAIL here means stop and replace the disk |
| /data filesystem, Snapshots (snapper), btrfs error counters | `findmnt`, `snapper --no-dbus list-configs`, `btrfs device stats` | btrfs, encrypted, config `storage`, counters zero | See conditions 1, 6, 7 |
| Boot slot | `rauc status` (booted slot and its status) | booted from A or B, status good | Note the slot before and after a test update |

## 3. Extras the script cannot do for you
- **Wi-Fi after restart, a mounted-by-mistake stick, speaker sound, a real print** need a person.
- **Console keyboard before login:** unplug and replug the USB keyboard at the box's own screen and check it still types.
- **Power button and lid-less behaviour:** press the power button once and note whether the box shuts down cleanly (UNVERIFIED how the image handles it).

## 4. Record
File `hw-check.txt` next to the install results, `research-output/evidence/lab/founder-hardware/LT-X86-07459-hw-check.txt`, after `sh lab-kits/common/redact.sh` and `make hygiene`. Add one line per WARN or SKIP saying whether it is a missing part, a missing tool on the image (a build finding) or a setting to fix. The script never decides that the Dell is ready: that is the founder's call.

## 5. What the script deliberately does not do
It does not run `fwupdmgr update`, `nmcli connection up`, `bluetoothctl scan` or `pair`, `snapper create`, `btrfs scrub`, `rauc mark` or `install`, `mount`, `lpadmin`, or anything that writes. `test/unit/test_hw_check.py` fails the build if a write command, a file redirect or a call outside a read-only allowlist ever appears in it.
