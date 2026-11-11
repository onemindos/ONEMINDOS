# REF3 · W19 · E10 boot-stage overlays (01 §4.8) · technical lens

**Refuter:** independent, technical lens, 2026-11-11. Existing adversarial files not read.

## Target
E10 (new, Frozen v1): device-tree overlays and early-boot drivers ship **only** through the OneMind release pipeline, inside the RAUC bundle or boot slot, selected by profile; a vendor whose overlay cannot ship this way is the DC-16 flip case.

## Strongest counter-argument
On both reference SoCs, overlay selection is partly **outside** the OneMind image and the profile:
1. **Raspberry Pi: hardware chooses the overlay.** For HAT+ boards "the firmware loads the Device Tree overlay named in the EEPROM", from `/boot/firmware/overlays` through `overlay_map`, and new HAT+ overlays are added by pull request to the Raspberry Pi Linux repository [C-REF3-W19-technical-014]. Original-spec HATs go further: "the firmware will read the overlay directly from the EEPROM and apply it" before Linux runs [C-REF3-W19-technical-015], i.e. vendor bytes from the board, unsigned and unseen by RAUC. `camera_auto_detect`/`display_auto_detect` also auto-load overlays (on by default in Raspberry Pi OS) [C-REF3-W19-technical-016]. So "selected by profile" is false by default; E10 must set `force_eeprom_read=0` and disable auto-detect (then re-enable deliberately per profile), or accept vendor-chosen overlays. And because HAT+ overlays live in the Raspberry Pi kernel tree, the overlay set is **per-kernel**, coupling E10 to E4's per-kernel pipeline.
2. **Jetson: two boot stages, two update channels.** Kernel DTB comes from the `extlinux.conf` FDT tag in the rootfs (RAUC slot: fine), else the A/B `kernel-dtb` partition; but UEFI-stage overlays are selected by board/fuse criteria and added via `OVERLAY_DTB_FILE` in the flashing `<board>.conf` [C-REF3-W19-technical-017]. Pinmux/camera overlays that must apply at the UEFI stage ship in the bootloader partitions, which RAUC's rootfs slot does not carry; they need NVIDIA's bootloader (capsule) update path, which is a second update channel with its own A/B and rollback semantics. The r36.2 page says nothing about signing DTBs or overlays.

E10 is therefore not one socket but three mechanisms (Pi firmware overlays, Jetson rootfs DTB/overlays, Jetson bootloader overlays), at least one outside RAUC's current scope.

## New sources (opened)
Raspberry Pi HAT+ specification (build 2024-12-05) [C-REF3-W19-technical-014]; Raspberry Pi hats devicetree guide [C-REF3-W19-technical-015]; Raspberry Pi `config.txt` documentation [C-REF3-W19-technical-016]; NVIDIA Jetson Linux r36.2 UEFI Adaptation [C-REF3-W19-technical-017].

## Verdict: **weakened**
The E10 socket is needed and the "release pipeline only" rule is right, but as written it is not enforceable on Pi (firmware honours EEPROM/auto-detect overlays) and not reachable on Jetson for UEFI-stage overlays without a bootloader-capsule path in the update design.

## What would flip it
- **→ upheld:** a lab image with `force_eeprom_read=0` and auto-detect off, overlays selected by profile from the RAUC boot slot, plus a Jetson RAUC bundle that updates the bootloader/`kernel-dtb` partitions (or proof that every day-one Jetson overlay can apply at kernel stage from the rootfs `extlinux.conf`).
- **→ refuted:** a day-one HAT or Jetson carrier whose overlay must come from its EEPROM or the UEFI stage and cannot be rebuilt into the OneMind boot slot (this is also the DC-16 flip case 01 names).
