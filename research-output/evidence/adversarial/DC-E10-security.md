# DC-16 / E10 refuter: security lens (REF4)

**Target:** extension point E10, boot-stage hardware enablement (device-tree overlays and early-boot drivers), `01` §4.8 and `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`. **Lens:** security. **Date:** 2026-11-11. **Protocol:** RESEARCH-MISSION.md §2 rule 7; read only the E10 row, the E10 enforcement and upkeep text in `01` §4.8 and their cited claims (C-REF3-W19-technical-014…017, C-REF-W19-longevity-010/011). No earlier adversarial file was read first (the two existing E10 files are technical and longevity).

## Claim under test

E10 overlays ship only through the OneMind release pipeline, inside the RAUC bundle or boot slot; on Pi, images set `force_eeprom_read=0`, turn camera/display auto-detect off, and take overlays only from the RAUC boot slot.

## Strongest counter-argument

E10's enforcement is a **configuration**, not an **integrity control**, on every Pi that is not fused.

1. **The settings live in the thing they protect.** `force_eeprom_read=0`, `camera_auto_detect=0`, the `dtoverlay=` lines and `cmdline.txt` (which carries `module.sig_enforce=1`) are all read by the Pi firmware from the FAT boot partition. Without Raspberry Pi signed boot nothing verifies them. Root on the device, or one minute with the SD card or NVMe, can re-enable EEPROM overlays, add any overlay (a device tree can remap GPIO, enable DMA-capable peripherals, or disable a security block), or drop `module.sig_enforce=1` and add `init=`. That undoes E10 **and** E4's module enforcement, and it persists across RAUC slot switches if the attacker edits both boot slots. `01` §4.3 keeps Pi fusing "irreversible and only for OneMind-built hardware", so every bring-your-own Pi runs E10 unverified.
2. **Signed boot changes the format, not just a flag.** With signed boot, config.txt, device tree **and overlay files** must be inside one signed `boot.img`, and OTP programming "cannot be disabled and a different key cannot be programmed" [C-REF4-DC-security-007]. Neither Raspberry Pi document describes anti-rollback or revocation for signed boot images, or A/B tryboot with `boot.img` [C-REF4-DC-security-007, C-REF4-DC-security-008]. So on fused OneMind hardware an old, validly signed `boot.img` carrying a vulnerable overlay or kernel stays bootable forever, and the tryboot RAUC backend (`01` §4.2 item 1) is untested with signed images.
3. **Jetson has the same gap one stage earlier.** Overlays are applied by UEFI from board-id criteria and the kernel DTB can come from `extlinux.conf` in the rootfs [C-REF3-W19-technical-017]; NVIDIA's own docs cited there do not discuss signing DTBs or overlays, and NVIDIA has already shipped a UEFI flaw that lets a privileged user corrupt the Linux device tree (already in the ledger as C-REF3-DC-security-002).

## Verdict: **weakened**

The rule (overlays only via the release pipeline) is right, and nothing here favours sysext or a different base, so DC-16 and D1 stand. But E10 as written gives no protection against a local or physical attacker on unfused Pi hardware, and on fused hardware it has no rollback protection. `01` should say so in the threat model and stop listing E10 enforcement as a security control on unfused boards.

## What would flip it

- **To upheld:** a Pi 5 lab (a fused test board, or an unfused board running the signed-boot path in a mode that verifies `boot.img`) showing: a modified `config.txt`/overlay/`cmdline.txt` refused; a tryboot A/B swap between two signed `boot.img` images working with RAUC; and an older signed `boot.img` refused after commit (a version check in the initramfs, or EEPROM `boot.img` hash pinning through `/proc/device-tree/chosen/bootloader/boot_img_sha256`). On unfused boards, a measured-boot alternative (the gate or the remote attestation refusing a boot partition whose hash differs from the release manifest) would also do.
- **To refuted:** a day-one board or HAT whose overlay cannot go into a signed `boot.img` (size, firmware or vendor licence), forcing unsigned overlays on the boot partition for that product, which is the DC-16 flip case with a security cause.

## Sources (new, opened)

- raspberrypi/usbboot `docs/secure-boot.md`: https://github.com/raspberrypi/usbboot/blob/master/docs/secure-boot.md [C-REF4-DC-security-007]
- Raspberry Pi security architecture: https://www.raspberrypi.com/documentation/security/security-architecture.html [C-REF4-DC-security-008]
