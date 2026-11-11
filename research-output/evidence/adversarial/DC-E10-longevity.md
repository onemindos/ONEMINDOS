# E10 · Boot-stage hardware enablement through the release pipeline — longevity refuter (wave 4)

**Refuter:** REF4, lens **longevity and vendor risk** (RESEARCH-MISSION.md §2 rule 7) · **Date:** 2026-11-11 · **Target:** extension point E10 (`01` §4.8; `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`) · **Verdict: weakened**

File name note: the task asked for `DC-<id>-longevity.md`; E10 belongs to DC-16, so this file is `DC-E10-longevity.md`. It is independent of the earlier E10 longevity refuter (formed without reading it) and cites none of its sources.

## Conclusion under test

E10 is **Frozen v1**: device-tree overlays and early-boot drivers ship only through the OneMind release pipeline, inside the RAUC bundle or boot slot, selected by profile. Rev. 3 adds `force_eeprom_read=0`, camera/display auto-detect off, overlays only from the RAUC boot slot, a per-kernel overlay CI cell, and an upstreaming clause for "Works with OneMind" [C-REF3-W19-technical-014…017]. The Pi 5 update path uses tryboot with a HAOS-style custom backend (`04` §183).

## Strongest counter-argument

E10 assumes the boot stage *below* the overlays is stable and inside OneMind's control. On Pi it is neither: the closed VideoCore firmware decides how overlays are found, and the bootloader EEPROM is a separately updated, vendor-paced component outside the A/B slots.

1. **Slot-scoped overlays depend on undocumented firmware semantics.** HAOS, the project OneMind's Pi 5 backend copies, put overlays in a per-slot directory. On the Pi 5, overlays named in `config.txt` silently stopped loading (`dtoverlay=rpi-rf-mod`, `vc4-kms-v3d`) because the firmware ignores `os_prefix` for overlays "unless `${os_prefix}${overlay_prefix}README` exists"; the fix was an empty README file, called "Kind of strange" by the maintainer [C-REF4-DC-longevity-009]. "Overlays come only from the RAUC boot slot" is exactly this pattern, and its correctness rests on a firmware behaviour with no compatibility promise; `force_eeprom_read=0` and the auto-detect switches are the same kind of closed-firmware knob.
2. **The bootloader is outside RAUC and has bricked boards.** On a Pi 5 Rev 1.1, every 2025 EEPROM release tested (2025-05-08, 2025-11-05, 2025-12-08) failed to boot; only 2024-09-10 worked, and that file "is no longer in the APT package". The vendor's answer was a duplicate link and "You need to contact the reseller for a refund"; the user's question why `FREEZE_VERSION=1` does not hold the version on Trixie went unanswered [C-REF4-DC-longevity-010]. RAUC's A/B and the k3s gate cannot roll back an EEPROM change, so a fleet whose EEPROM is updated by the vendor's tool, or not updated at all, drifts out of what the per-kernel CI cell tested.
3. **Longevity consequence.** E10 makes OneMind the owner of the whole boot chain for every certified board revision for the support period: kernel, overlays, *and* the firmware/EEPROM version, and the mapping between them. The per-kernel CI cell tests overlays against kernels, not against firmware/EEPROM versions or board revisions. "Frozen v1" freezes a contract on top of a layer the vendor changes without notice.

## Verdict: weakened

E10 is the right socket (sysext cannot reach this stage, and shipping overlays through the release pipeline is better than letting the firmware choose). It is weakened because its enforcement and CI cover the overlay files but not the firmware and EEPROM layer that decides whether those files load, which is vendor-controlled, outside the A/B rollback, and has failed in the field.

**Proposed changes (for the owner, not applied):** make the Pi bootloader EEPROM version part of the release (pin it, ship approved EEPROM images in the bundle, disable the vendor auto-update service, and update the EEPROM only as a separately gated, non-rollback step); extend the E10 CI cell to a matrix of kernel x firmware (`start*.elf`) x EEPROM version x board revision, asserting each certified overlay's device nodes from the slot directory; record the README/`overlay_prefix` behaviour as a tested invariant; on Jetson, treat QSPI/UEFI firmware the same way.

## What would flip it

- **To upheld:** a lab image that boots per-slot overlays across two firmware releases and two EEPROM releases on two Pi 5 board revisions with the vendor updater disabled, plus a documented, gated EEPROM update step.
- **To refuted:** a certified day-one board on which a required EEPROM or firmware version cannot be pinned (forced by the vendor, or needed for new board revisions), so overlay loading cannot be kept inside the release pipeline.

## Sources (new in this refuter)

- home-assistant/operating-system #3079 (2024-01-16, closed 2024-01-25 via PR #3107): <https://github.com/home-assistant/operating-system/issues/3079>
- raspberrypi/rpi-eeprom #817 (2026-04-10): <https://github.com/raspberrypi/rpi-eeprom/issues/817>
