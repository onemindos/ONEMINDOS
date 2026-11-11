# DC-19 refuter: the Pi 5 / CM5 pipeline on Debian (robotics lens)

| Field | Value |
|---|---|
| Target | DC-19. Current answer (01 §3.1.5): **favours A (Debian 13)**. umbrelOS ships Pi 5 in production on Debian with Raspberry Pi's kernel (C-W2-044). Ubuntu is certified (C-W2-057), but it has an open linux-raspi boot regression on older Pi 5 EEPROMs (C-DEC-006). Fedora bootc on Pi is experimental (C-W2-018). |
| Cited claims | C-W2-044, C-W2-057, C-DEC-006, C-W2-018, C-W2-043 |
| Lens | Robotics fit: Pi 5 / CM5 as a robot companion computer with USB sensors, patched for years |
| Protocol | RESEARCH-MISSION.md §2 rule 7. I read only the conclusion and its cited claims before forming this view. |
| Date | 2026-11-10. Re-check by 2027-05-10. |
| Verdict | **weakened** (A still leads, but the tie-break uses an asymmetric bug comparison, and the support-period half of the flip condition is unanswered) |

## 1. Cited sources re-checked

C-W2-044 holds: umbrelOS installs `linux-image-rpi-2712` and `raspi-firmware` from Raspberry Pi's trixie repo. C-DEC-006 is a real open Ubuntu bug. C-W2-018 holds.

## 2. Strongest counter-argument

1. **The Ubuntu bug used against D has a same-class twin on A's path.** The Pi 5's riskiest component is the boot EEPROM, and it comes from Raspberry Pi whichever distro is used. In 2026 alone, Raspberry Pi's **default-channel** bootloader regressed twice on Pi 5:
   - The 2026-09-25 release silently dropped `usb_max_current_enable=1`. USB-SATA disks then failed at boot and USB 3 ports disconnected; a Raspberry Pi engineer confirmed "a regression" and gave a workaround (`PSU_MAX_CURRENT=5000`) [C-REF-DC-robotics-007].
   - The 2026-05-11 release failed to boot one board revision with an SDRAM mismatch [C-REF-DC-robotics-008].

   For a robot, which runs USB cameras, LiDAR and serial adapters off the Pi's USB budget, the USB-power regression is worse than a boot stall that a newer EEPROM fixes. Counting C-DEC-006 against Ubuntu without counting these against the Raspberry Pi pipeline that A depends on is not like-for-like. The firmware risk is common to A and D, so it should cancel.
2. **"Maintainable for the support period without a fork" is untested.** A's Pi kernel is Raspberry Pi's, and Raspberry Pi gives no dated support period. A Raspberry Pi engineer says the previous release gets security-only updates "until we release Forky" [C-REF-DC-robotics-009]. A Debian-based Pi image is therefore on Raspberry Pi's roughly two-release window, not Debian's LTS. Ubuntu's Pi kernel, by contrast, is maintained by Canonical inside a published LTS (C-W2-005). On the flip condition's own wording ("can't be maintained for the support period without carrying a fork"), D has the documented support period and A does not. A's remedy is to rebase about every 2 years in step with Raspberry Pi OS, not to fork.

**Effect:** A's lead on DC-19 comes from evidence that it ships today (umbrelOS), which is real. But the tie-break's "**A**" should become "A ≥ D, conditional": conditional on OneMind pinning EEPROM releases rather than tracking `default`, and on a rebase-in-step policy (DC-05) for the Pi kernel.

## 3. New sources (searched for regressions and lifecycle limits)

- raspberrypi/rpi-eeprom issue #899 (closed 2026-10-21): https://github.com/raspberrypi/rpi-eeprom/issues/899 [C-REF-DC-robotics-007]
- raspberrypi/rpi-eeprom issue #861 (closed 2026-07-24): https://github.com/raspberrypi/rpi-eeprom/issues/861 [C-REF-DC-robotics-008]
- Raspberry Pi Forums, Bookworm security updates, a Raspberry Pi engineer's reply: https://forums.raspberrypi.com/viewtopic.php?t=391247 [C-REF-DC-robotics-009]
- Checked and **not** counted: raspberrypi/linux #7196 (Pi 5 boot failure on 6.18.4). The maintainers attributed it to Arch packaging (btrfs as a module, missing from the initramfs), not to Raspberry Pi's kernel: https://github.com/raspberrypi/linux/issues/7196

## 4. What would flip the decision

- **Toward D:** C-DEC-006 is fixed in 26.04 SRU **and** Raspberry Pi confirms no dated support for trixie's kernel past its next major release, so that Ubuntu offers the only Pi 5 kernel with a published window reaching 2031 or later.
- **Strengthens A:** Raspberry Pi publishes a dated support period for its trixie kernel and firmware packages, or umbrelOS (or another Debian-on-Pi appliance) shows an in-field rebase that followed a Raspberry Pi OS major release without a reflash.
- **Required regardless of base:** the Pi pipeline pins `rpi-eeprom` to a tested release (not `default`) and gates EEPROM updates on a USB-device and boot smoke test before rollout.
