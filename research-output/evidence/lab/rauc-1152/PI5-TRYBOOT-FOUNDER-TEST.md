# Founder test F-PI5: RAUC 1.15.2 + Raspberry Pi 5 `tryboot` + the k3s health gate

**Why this is a founder test:** QEMU cannot emulate the Raspberry Pi 5 boot firmware, and `tryboot` lives in that firmware. Our emulated labs proved the update logic on x86 (GRUB, 3 tries). This test proves it on the real Pi 5 boot path. Status: **blocked: founder-hardware**. The scripts were exercised as far as a VM allows (the "desk pre-flight", §7). Time needed: about 3 hours, including about 30 minutes of unattended preparation.

> **Explain it like I'm the founder.** On a PC, the bootloader (GRUB) keeps a counter and gives a new version three chances to boot. On a Raspberry Pi 5 there is no GRUB. The Pi's own firmware has one trick called **tryboot**: "boot the *other* copy of the OS once; if anything goes wrong, come back to the old one next time". It gives the new version **one** chance, not three. This test checks five things on a real Pi 5. (1) Good updates become permanent only after Kubernetes proves itself on that boot. (2) Bad updates (broken Kubernetes, a crash, a freeze) go back to the old version with nobody touching the box. (3) Unsafe update files are refused. (4) Pulling the power cord at the worst moments never bricks the Pi. (5) What happens when the power is pulled during the new version's one chance. We expect the update to be abandoned (safe, but it needs a reinstall). That is a real difference from x86 that OneMind's update service must handle.

## 1. What is being tested, and the expected answer

| Question | Expected answer (from the docs and HAOS's code) | Evidence |
|---|---|---|
| Does a failed trial return to the old OS by itself? | Yes. The firmware clears the tryboot flag *before* it starts, so a crash, reset or power cut loads the normal config next time | Raspberry Pi docs [C-LAB-rauc-1152-012] |
| How many chances does a new version get? | **One.** Retrying needs software help (not built here) | [C-LAB-rauc-1152-012], HAOS drops a missed tryboot and marks the slot bad [C-LAB-rauc-1152-014] |
| Can RAUC drive this? | Yes, through a "custom bootloader backend" script. HAOS does this on Pi 5 [C-W3-029]; ours switches whole partitions as the Pi docs describe [C-LAB-rauc-1152-013] | `scripts/pi5/rpi-tryboot-ab.sh` |
| Is the commit power-safe? | Unknown. The commit rewrites `autoboot.txt` on a FAT partition. This test measures it (F-P11c) | none yet |

## 2. What you need

- Raspberry Pi 5 (4 GB or 8 GB; OneMind's platform-node rule is at least 4 GB [01 §D4]), the official 27 W USB-C power supply, Ethernet, and a laptop for SSH.
- **Workbench card:** one microSD card (16 GB or more) with **Raspberry Pi OS Lite (64-bit), 2026-10-06 (trixie)** written by Raspberry Pi Imager. In Imager's settings, enable SSH and set a user. The image's published sha256 is `483db18a48da399b5b7022ffae9a07bc6d99daab30e593aedac09b69ff422843` (`.img.xz`) [C-LAB-rauc-1152-016].
- **Target disk (wiped):** a USB 3 SSD of **64 GB or more**, or an NVMe SSD on a Pi 5 M.2 HAT, or a second SD card in a USB reader.
- Optional but very useful: an HDMI monitor (the gate prints to the console), and a phone stopwatch.
- The kit from this folder: `scripts/pi5/` and `scripts/guest/` (copy both, keeping the folder names).

## 3. One-time setup (about 45 minutes, mostly unattended)

```bash
# On the laptop, from the repo root:
scp -r research-output/evidence/lab/rauc-1152/scripts <user>@<pi-address>:onemind-kit
ssh <user>@<pi-address>

# On the Pi (booted from the workbench card):
sudo apt update && sudo apt full-upgrade -y && sudo reboot          # then ssh back in
sudo rpi-eeprom-config | grep BOOT_ORDER      # must include 4 (USB) or 6 (NVMe); default 0xf461 does
sudo bash onemind-kit/pi5/build-rauc-pi.sh    # PASS: prints "rauc v1.15.2" and a sha256
lsblk -o NAME,SIZE,MODEL,MOUNTPOINTS          # find the TARGET disk; check the size twice
sudo TARGET=/dev/sda CONFIRM=/dev/sda bash onemind-kit/pi5/prepare-disk.sh   # use YOUR target name
```

`prepare-disk.sh` wipes the target. It then copies the running Raspberry Pi OS into the A/B layout below, adds RAUC 1.15.2, k3s v1.37.2+k3s1 (hash-checked), the OneMind health gate, and 8 test bundles, and makes slot A version 1 the committed system. **PASS:** it ends with `done`, prints 7 lines `Bundle Format: verity`, 1 line `Bundle Format: plain`, and `[wrong-key] rejected (expected)`. The lab signing keys stay on the workbench card (`/root/onemind-lab-keys`).

| Partition | Size | Holds |
|---|---|---|
| 1 FAT `AUTOBOOT` | 64 MiB | `autoboot.txt` (which slot boots) and `slot-A.good` / `slot-B.good` markers |
| 2 FAT | 512 MiB | Boot files, slot A |
| 3 FAT | 512 MiB | Boot files, slot B |
| 5 ext4 | 8 GiB | Root filesystem, slot A |
| 6 ext4 | 8 GiB | Root filesystem, slot B |
| 7 ext4 `data` | rest | k3s state, RAUC data, gate log, test bundles |

Then: `sudo poweroff`, **remove the workbench card**, and power on. The Pi now boots from the target disk. SSH in again (same user and host keys). From here on, every check is one command: `sudo onemind-status`.

## 4. The tests

Run them in order. After each `reboot`, **touch nothing** until the stated end state (wait up to 10 minutes), then SSH in and run `sudo onemind-status`. Write down the times. "Back on B" means `firmware: tryboot=0 partition=3` and `release: ONEMIND_VERSION=2`.

| ID | Do this | PASS if | FAIL if |
|---|---|---|---|
| F-P1 | First boot from the target | Gate: `RESULT committed-boot slot=A version=1`, then `K3S-FRESH ok`; `rauc: rauc v1.15.2`; `firmware: … partition=2`; `sudo k3s kubectl -n apps get pods` shows `broken-app 0/1` | No boot, or k3s never fresh-healthy |
| F-P2 | `sudo rauc install /data/bundles/wrong-key.raucb` | Refused with a signature error; `pending: none`; `autoboot.txt` unchanged | It installs |
| F-P3 | `sudo rauc install /data/bundles/plain-good.raucb` | Refused with `Bundle format 'plain' not allowed`; `pending: none` | It installs or writes a marker |
| F-P4 | `sudo rauc install /data/bundles/good.raucb && sudo systemctl reboot` | The Pi boots slot B through tryboot (`tryboot=1 partition=3` on that boot). The gate logs `CHECK pass 1/3 … 3/3`, then `RESULT mark-good slot=B version=2`; `autoboot.txt` now says `boot_partition=3` under `[all]`. After `sudo reboot`: `committed-boot slot=B version=2` with `tryboot=0 partition=3` | Commits without 3 passes, or ends anywhere but committed B v2 |
| F-P5 | `sudo rauc install /data/bundles/bad-k3s.raucb && sudo systemctl reboot` | Trial on A fails for 300 s, the gate logs `RESULT mark-bad slot=A version=3` and reboots, and the Pi is **back on B** (`committed-boot`, `K3S-FRESH ok`); `slot-A.good` absent | Commits v3, or needs input |
| F-P6 | Same with `bad-noagent.raucb` (stale-Ready trap) | Same as F-P5 with version 4; the last fails say `kubelet /healthz not answering` | Commits v4 |
| F-P7 | Same with `bad-boot.raucb` (kernel panic) | **Exactly one** panic (the console shows `BAD-BOOT`), a reboot about 10 s later (`panic=10`), then back on B; the gate logs `RESULT fell-back … slot A (v5) marked bad`. A further `sudo reboot` does not try A | More than one attempt on A, a boot loop, or a hang |
| F-P8 | Same with `bad-hang.raucb` (freeze, watchdog armed) | One `BAD-HANG` freeze, a watchdog reset within about 20 s, then back on B with `fell-back` | Pi stays frozen (needs a power cycle) |
| F-P9 | Observation: `naive-noagent.raucb` | Expect the naive gate to **commit the broken system** (as on x86 [C-LAB-rauc-k3s-gate-008]). Then `sudo rauc install /data/bundles/good.raucb && sudo systemctl reboot` must commit good again (**F-P9r**: PASS/FAIL) | F-P9r does not commit |
| F-P10 | Power pull during the write: start `sudo rauc install /data/bundles/good.raucb`; when the output shows `Copying image` (or after about 20 s), pull the USB-C cord. Power on | Back on the committed slot with `fell-back` (marker cleared, half-written slot not good); a reinstall of `good` then commits | No boot, or a half-written slot boots |
| F-P11a | Power pull during the trial boot: install `good`, reboot, and pull the cord when the HDMI console shows `HEALTH-GATE … mode=trial` (or 40 s after power-on). Power on | Back on the committed slot, `fell-back`, the new slot marked bad. **Record:** the update was abandoned and needs a reinstall (expected: one tryboot chance) | No boot, or an ungated boot of the new slot |
| F-P11b | Repeat F-P11a 4 more times (5 pulls in all) | 5/5 end on a working committed slot without a keyboard | Any boot needs a keyboard |
| F-P11c | Power pull in the commit window: `echo 30 \| sudo tee /data/onemind/lab-commit-delay`, install `good`, reboot. When the console prints `COMMIT-WINDOW open … pull power now`, pull the cord. Power on. Repeat 3 times, then `sudo rm /data/onemind/lab-commit-delay` | Each time, the Pi boots a working slot (old or new) without a keyboard; `sudo fsck.vfat -n /dev/disk/by-label/AUTOBOOT` reports no errors; `autoboot.txt` is complete (4 lines + header) | A missing or corrupt `autoboot.txt`, an unbootable Pi, or a FAT error |

**Overall PASS:** F-P1 to F-P8, F-P9r, F-P10 and F-P11a–c all pass, with no keyboard input after any `reboot`. Also record the good-commit time (F-P4) and the bad-k3s decision time (F-P5). The production gate deadline should then be set to about 3× the good-commit time, as for x86 (`../rauc-k3s-gate/` F1).

**If a step fails:** run `sudo onemind-status`, `sudo cat /data/onemind/gate.log`, `sudo journalctl -b -1 -u onemind-health-gate -u rauc --no-pager | tail -50` and, if the Pi will not boot, put the workbench card back in to read the target disk. Note the step and output in §8.

**Cleanup:** the target disk holds lab-only shortcuts (a fixed machine-id, lab keys' public certificate, a writable root). Wipe it after the test (`sudo wipefs -a /dev/sdX` from the workbench card) and delete `/root/onemind-lab-keys` on the workbench card.

## 5. Differences from the x86 lab, and why

| Item | x86 lab (`../rauc-k3s-gate/`, this spike) | Pi 5 test | Why |
|---|---|---|---|
| Slot switch | GRUB variables in `grubenv` | `autoboot.txt` + one-shot firmware `tryboot` [C-LAB-rauc-1152-013] | There is no GRUB on Pi 5 |
| Tries per update | 3 | **1** [C-LAB-rauc-1152-012] | Firmware feature. `boot_count` exists but is cleared on power loss [C-LAB-rauc-1152-015], so it cannot replace a try counter |
| Committing | RAUC `mark-good` resets `TRY` | RAUC `mark-good` → backend rewrites `autoboot.txt` | Pi docs' commit step [C-LAB-rauc-1152-013] |
| Gate | Same script | Same script; only the slot-state lookup and log text change (`scripts/pi5/onemind-health-gate`; diff in `scripts/CHANGES-vs-rauc-k3s-gate.md`) | Keeps one gate for every board |
| Root filesystem | Read-only (ext4 mounted `ro`) | **Writable** in this test (Raspberry Pi OS is not built for a read-only root); k3s state still bind-mounted from `data`, so the stale-Ready trap still applies | Keeps the test about the boot path. The read-only root is already proven on x86 [C-LAB-rauc-k3s-gate-004] |
| Watchdog | QEMU `i6300esb` | Pi 5's own (`bcm2835_wdt`) with systemd `RuntimeWatchdogSec=10s` | Real hardware |
| Kernel panic | Reboots via watchdog/GRUB | `panic=10` on the kernel command line | Without it, a panic before systemd starts would hang the Pi |

## 6. What competitors do

| Product | Pi 5 A/B mechanism | Tries | What commits | Constraint fit for OneMind |
|---|---|---|---|---|
| Home Assistant OS | RAUC custom backend + firmware tryboot, one boot partition with `slot-A/`/`slot-B/` folders (`os_prefix`) [C-W3-029, C-LAB-rauc-1152-014] | 1; a missed tryboot is dropped and the slot marked bad | Supervisor marks good on start | **High** for the mechanism (same engine, same firmware feature). **Low** for the gate (no k3s check) |
| Raspberry Pi's own reference | `autoboot.txt` + `tryboot_a_b=1`, whole boot partitions [C-LAB-rauc-1152-013] | 1 | "The update service" swaps `autoboot.txt` | **High**: the vendor-documented layout. This kit uses it |
| umbrelOS 2.0 (Rugix) | Rugix's Pi tryboot integration (not re-verified here; see `../debian-rugix/`) | n/a here | Rugix commit | Medium (same firmware feature, different engine) |
| OneMind (this kit) | RAUC 1.15.2 custom backend over the vendor layout, plus the fresh-signal k3s gate | 1 | Gate after 3 fresh passes | Target design; **unproven on hardware until this test runs** |

## 7. Desk pre-flight (what was checked without a Pi)

See README §7.4. Inside the disposable arm64 VM, the unchanged `build-rauc-pi.sh` and `prepare-disk.sh` ran against the real Raspberry Pi OS Lite 2026-10-06 image, with a loop device standing in for the SSD. Then a real `rauc install` of `good.raucb` and the backend's commit/rollback logic (with a faked firmware device tree) were exercised. This catches script, layout and configuration mistakes. **It does not test the firmware, the watchdog, panics or power loss.** Those are why this founder test exists.

## 8. Results (fill in)

| ID | PASS/FAIL | Time (s) | Notes |
|---|---|---|---|
| F-P1 | | | |
| F-P2 | | | |
| F-P3 | | | |
| F-P4 | | commit: | |
| F-P5 | | decision: | |
| F-P6 | | | |
| F-P7 | | | attempts on A: |
| F-P8 | | | |
| F-P9 / F-P9r | obs. / | | |
| F-P10 | | | |
| F-P11a | | | update abandoned? |
| F-P11b | /5 | | |
| F-P11c | /3 | | fsck output: |

## 9. Not covered here (open)

- **Pi 5 secure boot together with tryboot** (critic pass-2 Q-P2-4). The docs say that with secure boot, tryboot loads `tryboot.img` instead of `boot.img`, and that `tryboot_a_b` is implied inside a `boot.img` ramdisk [C-LAB-rauc-1152-012]. Testing that would mean burning OTP keys into a Pi, which cannot be undone. Use a dedicated Pi for it, as a separate test.
- **An EEPROM bootloader update in the same release** as an OS update. Not exercised.
- **A retry after a power cut during the trial** (x86 gets 3 tries). A software re-arm, where the gate re-arms tryboot once if a trial marker exists and the slot is not bad, is the same idea 01 proposes for the x86 `efi` backend. It is not built or tested here.

## 10. Glossary

| Term | Meaning |
|---|---|
| tryboot | Pi firmware flag: boot the alternative config or partition once; cleared before the firmware starts, so any failure returns to the normal one |
| `autoboot.txt` | A file on the Pi's first FAT partition that says which partition boots normally (`[all]`) and which one boots under tryboot (`[tryboot]`) |
| `tryboot_a_b=1` | Switches whole partitions under tryboot, instead of loading a different config file |
| Custom backend | A script RAUC calls to read or change "which slot is primary" and "is this slot good" on bootloaders RAUC does not know natively |
| `panic=10` | Kernel option: reboot 10 s after a kernel panic instead of hanging |
| Workbench card | The SD card used to build the test disk; it is not part of the test system |
| Others | See README §6 and `../rauc-k3s-gate/` §6 |

## Requirement IDs

R-1, R-2 (safe updates, self-healing), P-1/Lite-tier Pi 5 hardware, M-6. Feeds REC-DEC-05 (RAUC on Pi 5 via tryboot), REC-DEC-07 (gate), and critic pass-2 N8. Goes into `22-HARDWARE-LAB-TEST-PLAN.md` as F-PI5.
