<!-- Copied verbatim from research-output/22-HARDWARE-LAB-TEST-PLAN.md (LT-PI5-01), 2026-11-11. Do not edit: if 22 changes, re-copy. -->

### LT-PI5-01 · RAUC 1.15.2 + Pi firmware `tryboot` + k3s gate · **G**
**Aliases:** F-PI5, T-W3-02 (NVMe part), critic N8, Q9, Q-P2-4 (partly) · **Kit and full steps:** [`evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`](../../research-output/evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md) (desk pre-flight done in a VM) · **Time:** about 3 hours
```sh
# Workbench microSD: Raspberry Pi OS Lite 64-bit 2026-10-06 (trixie), .img.xz sha256 483db18a…2843 [C-LAB-rauc-1152-016]
scp -r research-output/evidence/lab/rauc-1152/scripts <user>@<pi-address>:onemind-kit
sudo apt update && sudo apt full-upgrade -y && sudo reboot
sudo rpi-eeprom-config | grep BOOT_ORDER          # must include 4 (USB) or 6 (NVMe)
sudo bash onemind-kit/pi5/build-rauc-pi.sh        # prints "rauc v1.15.2"
lsblk -o NAME,SIZE,MODEL,MOUNTPOINTS               # identify the TARGET disk; check size twice
sudo TARGET=/dev/<target> CONFIRM=/dev/<target> bash onemind-kit/pi5/prepare-disk.sh   # WIPES the target
# poweroff, remove the workbench card, boot from the target; then each step is one command:
sudo onemind-status
# rev. 4, step A1 before F-P1 (aarch64-gate §9): the Pi 5 default kernel uses 16 KiB pages
getconf PAGESIZE                                   # expect 16384 with kernel_2712.img
sudo k3s check-config; # then start k3s once and record whether CoreDNS reaches Ready
# if k3s or a pod fails: set kernel=kernel8.img (4 KiB pages) in config.txt, repeat, record both
```
Steps **F-P1 … F-P11c** (first boot; wrong-key and plain bundles refused; good update commits only after 3 fresh passes; bad-k3s, stale-Ready, kernel panic and hang each return to the committed slot; power pulls during the write, the trial and the commit window, 5 + 3 times).
- **Pass:** A1 shows k3s fresh-healthy on the kernel you will ship; F-P1–F-P8, F-P9r, F-P10, F-P11a–c all pass with no keyboard input. Record good-commit and bad-decision times and set the Pi gate deadline to ≥ 3× the good-commit time (aarch64-gate L-A2). The same RAUC 1.15.2 + k3s arm64 + gate already passed T1–T11 under emulation [C-LAB-aarch64-gate-004], so a failure here points at the Pi firmware, the Pi kernel or the storage, not the gate logic. **Expected and accepted:** a pull during the trial abandons that update (the firmware gives **one** chance [C-LAB-rauc-1152-012]).
- **Fail → consequence:** the Pi 5 tier stays "designed, not proven"; REC-DEC-32 (re-offer an abandoned trial) is needed regardless; a brick or a corrupt `autoboot.txt` sends Pi 5 to Rugix's proven tryboot integration (01 §6.7) or HAOS's single-partition variant [C-W3-029].
- **Feeds:** DC-19, DC-07, REC-DEC-05, -07, -32, -34. **Not covered:** Pi secure boot with tryboot (needs a dedicated Pi with irreversible OTP; out of scope) and an EEPROM update in the same release.
