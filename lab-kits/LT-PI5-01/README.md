# LT-PI5-01 · RAUC 1.15.2 + Pi firmware `tryboot` + k3s gate (Raspberry Pi 5)

**Status:** kit-ready (blocked: founder-hardware) · **Time:** about 3 hours · **Milestone:** BM1 (brief 30 §7, never-cut list) · **Serves:** DC-19, DC-07, REC-DEC-05, -07, -32, -34; P-1, R-1
**Criteria:** [CRITERIA-22.md](CRITERIA-22.md), copied verbatim from `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §4. They are not edited here.
**Kit and full steps:** [`research-output/evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`](../../research-output/evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md) and its `scripts/pi5/` (desk pre-flight done in a VM, [C-LAB-rauc-1152-017]). This kit is the runbook around them.

> **Explain it like I'm the founder.** A Raspberry Pi 5 does not use GRUB. Its own firmware can boot "the other copy" exactly **once** (`tryboot`); if that boot is not confirmed, the next power-on goes back to the old copy. QEMU cannot pretend to be that firmware, so the only proof is a real Pi 5. The research run wrote and desk-checked the full test; you run it on the Pi with an NVMe or USB SSD as the target disk. A power pull in the middle of a trial is *expected* to abandon that update (one chance only), and the box must still come back working.

## Why this kit uses the research scripts, not the build pipeline
The build's `rpi5` board (`os/boards/rpi5/`, brief 30 D-B2.2 with BD-07's layout) is **not built yet** in this session; it is next after x86_64-efi, vm-do and arm64-efi. 22 names the research kit as the one to run, and LT-PI5-01 tests the Pi firmware path, which is the same either way. When the `rpi5` board lands, this README gains a "build from the pipeline" section like LT-X86-01's.

## What you need (22 §2.3)
- **A Raspberry Pi 5** (a Pi 4 is not a v0 board), the official 27 W PSU, an NVMe HAT + NVMe SSD (or a USB 3 SSD) as the **target**, and a microSD card for the **workbench** system.
- Workbench card: Raspberry Pi OS Lite 64-bit 2026-10-06 (trixie); check the `.img.xz` sha256 starts `483db18a` and ends `2843` before flashing [C-LAB-rauc-1152-016].
- A way to pull power by hand (or a switched outlet) for the power-pull steps (PP-10, [`../common/PP-10.md`](../common/PP-10.md)).

## Steps (22's command block, unchanged)
```sh
# Workbench microSD: Raspberry Pi OS Lite 64-bit 2026-10-06 (trixie)
scp -r research-output/evidence/lab/rauc-1152/scripts <user>@<pi-address>:onemind-kit
sudo apt update && sudo apt full-upgrade -y && sudo reboot
sudo rpi-eeprom-config | grep BOOT_ORDER          # must include 4 (USB) or 6 (NVMe)
sudo bash onemind-kit/pi5/build-rauc-pi.sh        # prints "rauc v1.15.2"
lsblk -o NAME,SIZE,MODEL,MOUNTPOINTS               # identify the TARGET disk; check size twice
sudo TARGET=/dev/<target> CONFIRM=/dev/<target> bash onemind-kit/pi5/prepare-disk.sh   # WIPES the target
# poweroff, remove the workbench card, boot from the target; then each step is one command:
sudo onemind-status
getconf PAGESIZE                                   # step A1: expect 16384 with kernel_2712.img
sudo k3s check-config                              # then start k3s once; record whether CoreDNS reaches Ready
# if k3s or a pod fails: set kernel=kernel8.img (4 KiB pages) in config.txt, repeat, record both
```
Before `prepare-disk.sh`, also run `sh lab-kits/common/check-target-disk.sh /dev/<target>` on the Pi (it asks for the size twice). Then follow steps **F-P1 … F-P11c** in `PI5-TRYBOOT-FOUNDER-TEST.md`.

## Record
Write `research-output/evidence/lab/founder-hardware/LT-PI5-01.md` from [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md); pipe pasted output through `sh lab-kits/common/redact.sh`. Record the EEPROM bootloader version (`rpi-eeprom-update`), the good-commit and bad-decision times, and set the Pi gate deadline to ≥ 3× the good-commit time (22). Never run any OTP or key-programming command (SB-8; 22 §2.3 rule 4).

## Pass / fail
As in [CRITERIA-22.md](CRITERIA-22.md). **LT-PI5-02 (bootc on a real Pi 5, W2-HW-3)** is a separate kit that 22 schedules after this one on the same Pi; the founder override (Z-38 = b) keeps it as a watched input only.
