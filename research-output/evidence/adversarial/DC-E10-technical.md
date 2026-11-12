# E10: refuter report on boot-stage overlays via the release pipeline, technical lens

- **Conclusion under test (01 §4.8 E10 row and "E10 enforcement"; 29-PLATFORM-ECOSYSTEM-MARKETPLACE.md):** device-tree overlays and early-boot drivers are **frozen v1** and ship only through the OneMind release pipeline, inside the RAUC bundle or boot slot, selected by profile. Enforcement on Pi: `force_eeprom_read=0`, camera/display auto-detect off, overlays only from the RAUC boot slot. On Jetson, UEFI-stage overlays need a bundle that updates the bootloader/`kernel-dtb` partitions or must be shown to apply at kernel stage. Upkeep: a per-kernel CI cell boots each certified overlay and checks its device nodes.
- **Flip case:** a day-one device whose overlay or early driver can't ship this way (DC-16 flip).
- **Lens:** technical. I read only the conclusion and its cited claims (C-REF3-W19-technical-014…017, C-REF-W19-longevity-010). I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened**

E10 controls *which overlay files* are in the image. It doesn't control the **firmware that applies them**, and its checks run in CI rather than in the boot that commits.

1. **On Pi 5 the overlay loader is outside the A/B slot.** The Pi 5 bootloader, which reads `config.txt` and applies overlays, lives in SPI EEPROM, not in the RAUC boot slot. In June 2026, HAOS 18 (Buildroot + RAUC, the reference appliance) had to **revert Pi 5 and Yellow to 17.3**. Its kernel 6.18.33 was incompatible with older EEPROM firmware: an unreadable EEPROM config then led an EEPROM update to apply the default boot order, and the incompatibility also caused a display problem. The fix was a kernel bump, 6.18.34 [C-REF4-DC-technical-006]. A kernel/DT change that passes a per-kernel CI cell on one EEPROM version can therefore break fielded units on another. EEPROM updates are themselves a non-A/B write. The CI cell has to be a **kernel × EEPROM-version** matrix, and the image has to pin, gate and record the EEPROM version. E10 says none of this.
2. **Base-DT changes break overlays before the kernel runs.** On CM4 in March 2026, a downstream kernel merge changed UART compatibles in the base DTB. `dtoverlay=disable-bt` then put the firmware into a reset loop before anything booted, and restoring the old DTB fixed it. The issue is open with no fix [C-REF4-DC-technical-007]. A RAUC trial boot would fall back here, which is good. But the overlay CI cell has to boot real firmware on real boards, not apply overlays with `dtoverlay` or in QEMU. QEMU doesn't run the VideoCore firmware stage, so it can't catch this class of failure.
3. **On Jetson, the "bundle updates `kernel-dtb`/bootloader" route rests on NVIDIA's capsule path, which is fragile on custom carriers, and overlays can silently stop applying.** On an Orin NX custom carrier with Secure Boot and ROOTFS_AB (R36.4), the A/B OTA capsule update failed with `LAS_ERROR_IMAGE_NOT_IN_PACKAGE` because of a TNSPEC/board-spec mismatch, and the slot didn't change. NVIDIA's advice was to patch `l4t_generate_ota_package.sh` and `ota_board_specs.conf` per board [C-REF4-DC-technical-008]. On an Orin Nano, a working jetson-io overlay stopped taking effect after an update. `extlinux.conf` still named it and the `.dtbo` was present, but no root cause was found and re-running jetson-io fixed it [C-REF4-DC-technical-009]. The second case **boots healthy with the overlay missing**. DC-12's fresh-signal gate (kubelet, core pods) would **commit** it.

None of this shows a day-one board whose overlay *can't* ship through the pipeline, so the verdict is not **refuted**. It shows that "ships through the pipeline" isn't enough for "applies correctly on the fielded unit".

## Strongest counter-argument

E10 treats the boot slot as the single authority for boot-stage hardware enablement. On both target SBC families, a component outside the slot applies the overlays: the Pi 5 SPI EEPROM bootloader, and Jetson QSPI UEFI with per-carrier capsule specs. That component can change independently of the kernel or break against it, and HAOS had to roll back a release over exactly this. The upkeep check is a CI cell, so a unit that boots with its CAN, camera or HAT overlay missing passes the commit gate and stays committed in the field.

## New sources (searched for regressions and failures)

- **N1.** home-assistant/operating-system #4811 (opened 2026-06-22, HAOS 18.0, Pi 5). Opened. Kernel 6.18.33 incompatible with old EEPROM firmware; HAOS 18 reverted to 17.3 for Pi 5/Yellow; fixed by kernel 6.18.34 (PR #4814). https://github.com/home-assistant/operating-system/issues/4811 [C-REF4-DC-technical-006]
- **N2.** raspberrypi/linux #7273, "dtoverlay=disable-bt is broken in the most current version of the kernel" (opened 2026-03-12, CM4, open). Opened. https://github.com/raspberrypi/linux/issues/7273 [C-REF4-DC-technical-007]
- **N3.** NVIDIA forum, "Unable to get capsule updates to work with A/B updates" (2026-03, Orin NX custom carrier, R36.4, Secure Boot, ROOTFS_AB/ENC). Opened. https://forums.developer.nvidia.com/t/unable-to-get-capsule-updates-to-work-with-a-b-updates/363263 [C-REF4-DC-technical-008]
- **N4.** NVIDIA forum, "Update stops overlay applying" (2025-11-12/13, Orin Nano, closed 2026-01-07). Opened. https://forums.developer.nvidia.com/t/update-stops-overlay-applying/351210 [C-REF4-DC-technical-009]
- (Checked, supports E10) raspberrypi/firmware #1879: a HAT+ EEPROM read broke a DSI overlay on Pi 5, and `force_eeprom_read=0` fixed it. This confirms the existing enforcement and adds nothing new against it.

## What would flip it

- **→ upheld:** E10 adds three things. (a) The EEPROM/QSPI firmware version is pinned and updated only through its own gated path, and is recorded in the release manifest. (b) The per-kernel CI cell is a kernel × firmware-version matrix booting real boards. (c) The DC-12 trial gate checks each profile's certified overlay device nodes, so a missing overlay fails the trial. A Pi 5 run in which an old EEPROM plus a new kernel is caught pre-release, and a Jetson custom-carrier capsule + `kernel-dtb` bundle that updates and rolls back cleanly (LAB-W7-6 / T-W3-06), would confirm it.
- **→ refuted:** a day-one board whose overlay is applied only by firmware that OneMind can't version or gate. Examples: a carrier whose capsule can't be built for OneMind's TNSPEC, or a Pi HAT that needs a newer EEPROM than the fleet can safely receive. That is the DC-16 flip case.
