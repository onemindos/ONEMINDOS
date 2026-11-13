# LT-PI5-01 · RAUC 1.15.2 + Pi firmware `tryboot` + k3s gate (Raspberry Pi 5)

**Status:** kit-ready (blocked: founder-hardware) · **Time:** about 3 hours · **Milestone:** BM1 (brief 30 §7, never-cut list) · **Serves:** DC-19, DC-07, REC-DEC-05, -07, -32, -34; P-1, R-1
**Criteria:** [CRITERIA-22.md](CRITERIA-22.md), copied verbatim from `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §4. They are not edited here.
**Kit and full steps:** [`research-output/evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`](../../research-output/evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md) and its `scripts/pi5/` (desk pre-flight done in a VM, [C-LAB-rauc-1152-017]). This kit is the runbook around them.

> **Explain it like I'm the founder.** A Raspberry Pi 5 does not use GRUB. Its own firmware can boot "the other copy" exactly **once** (`tryboot`); if that boot is not confirmed, the next power-on goes back to the old copy. QEMU cannot pretend to be that firmware, so the only proof is a real Pi 5. The research run wrote and desk-checked the full test; you run it on the Pi with an NVMe or USB SSD as the target disk. A power pull in the middle of a trial is *expected* to abandon that update (one chance only), and the box must still come back working.

## Two ways to run it
**Route P (pipeline, preferred, 2026-11-12):** the `rpi5` board now exists (`os/boards/rpi5/`, brief 30 D-B2.2 with BD-07's layout, explained in `docs/leap/core/IMAGES.md` §8). It is the image OneMind ships: Debian 13 arm64 + Raspberry Pi's kernel, read-only root, RAUC 1.15.2 with the `tryboot` backend ported from the research kit, the same health gate as x86, and OneMind itself. `make fixtures … HW=1` builds the test disk and **the same 8 test bundles** the research kit made, so every F-P step below runs unchanged. Steps: "Route P" below.
**Route R (research scripts):** 22's command block (section "Route R steps" below), which builds a writable-root test disk from Raspberry Pi OS. Use it if route P fails to boot, to tell a pipeline problem from a firmware problem. Known difference: the research backend commits with `sync` on the directory only, which on vfat can leave `autoboot.txt` pointing at a freed cluster for up to the kernel's writeback delay; route P's backend fsyncs the renamed file (found by `os/boards/rpi5/desk-check.sh`, IMAGES.md §8). Expect route R's F-P11c to be weaker for that reason.

## Route P: build, flash, run (about 3 hours, plus about 40 min of build)
### P1. Build (in the Lima build VM, arm64 native; never Docker on the Mac)
```sh
make rootfs BOARD=rpi5                         # Debian 13 + Raspberry Pi kernel 6.18.60 (pinned debs) + OneMind
make fixtures BOARD=rpi5 UPTO=T10 HW=1         # out/fx-rpi5/: disk.img (20 GiB), bundles.img, t0.json, SHA256SUMS
make image BOARD=rpi5 && make convert BOARD=rpi5 && make rpi5-check && make imager-json   # the product image (P4)
```
PASS: `t0.json` says `"pass": true`, and `make rpi5-check` ends `rpi5 image structure: PASS`. Copy `out/fx-rpi5/` and `out/image-rpi5/` to the Mac (`limactl copy`), and check them there with `shasum -a 256 -c SHA256SUMS`. The throwaway signing keys were destroyed inside the container; only the public `dev-ca.cert.pem` is kept.

### P2. Flash (Mac)
- **Target (NVMe in a USB enclosure, or a USB 3 SSD, ≥ 32 GB):** `sh lab-kits/common/check-target-disk.sh /dev/diskN`, type the size twice, then
  `diskutil unmountDisk /dev/diskN && sudo dd if=out/fx-rpi5/disk.img of=/dev/rdiskN bs=4m status=progress`.
  Raspberry Pi Imager works too: **Choose OS → Use custom → `disk.img`**, and answer **No** to "apply OS customisation".
- **Bundles stick (≥ 8 GB):** the same two commands with `if=out/fx-rpi5/bundles.img` (ext4, label `onemind-test`).
- The Pi needs **no workbench card** on this route. Only its EEPROM must boot from the target: `BOOT_ORDER` must include 6 (NVMe) or 4 (USB). The default `0xf461` does (research kit §3); otherwise set it once with Imager → Misc utility images → Bootloader → NVMe/USB Boot (a card you then remove).

### P3. Run (on the Pi: HDMI monitor + keyboard, Ethernet, the stick plugged in)
The console logs in as root by itself (test disk only). The first boot grows `/data` to the disk and prints the bootloader date (`ONEMIND-RPI5: bootloader …`). Then:
```sh
mkdir -p /run/onemind-test && mount -o ro /dev/disk/by-label/onemind-test /run/onemind-test
/usr/lib/onemind/rpi5-status                 # firmware: tryboot=0 partition=2; page size; gate log
getconf PAGESIZE                             # step A1: expect 16384 (kernel_2712.img)
k3s check-config | tail -5; KUBECONFIG=/run/k3s/k3s.yaml k3s kubectl -n kube-system get pods   # CoreDNS Running?
```
Then F-P1 … F-P11c from `PI5-TRYBOOT-FOUNDER-TEST.md` §4, one line at a time, with two path changes: bundles are `/run/onemind-test/bundles/<name>.raucb` (mount the stick again after each reboot), and the status command is `/usr/lib/onemind/rpi5-status`. Run every install as `rauc install … && systemctl reboot` (the backend arms the one-shot `tryboot` through `/run/systemd/reboot-param`, which `systemctl reboot` reads). For F-P11c: `echo 30 > /data/onemind/lab-commit-delay` and afterwards `fsck.vfat -n /dev/disk/by-partuuid/4f4d5035-01`.

**A1 fallback (k3s or a pod fails on 16 KiB pages):** set `kernel: "v8"` in `os/boards/rpi5/board.yaml`, rebuild (P1), reflash, repeat A1 and F-P1; record both results. Both kernels are in every boot slot; the setting only changes `config.txt`.

### P4. First boot into OneMind (the product image, about 15 min)
Flash `out/image-rpi5/onemind-rpi5-<version>.img.xz` with Imager (**Use custom**, or `rpi-imager --repo out/image-rpi5/os_list.json`, which lists it as "OneMind OS … (Raspberry Pi 5)"; answer **No** to OS customisation) or with `xzcat … | sudo dd of=/dev/rdiskN bs=4m`. Before ejecting, open the **ONEMIND** partition the Mac shows, and in `onemind.conf` uncomment `role = hub` (or leave it, to use the wizard). Boot the Pi from it (a hub belongs on NVMe or a USB SSD, BD-07; a worker or leaf may run from SD). PASS: the console prints `ONEMIND-FIRSTBOOT: configured role=hub source=…` and the owner token once, and `http://onemind.local:8080/` shows the dashboard from the Mac on the same LAN.

### P5. Record and wipe
As in "Record" below; also paste `/usr/lib/onemind/rpi5-status`, `cat /data/onemind/rpi5-eeprom` and `cat /usr/lib/onemind/build-info.txt` (through `redact.sh`). Wipe the target and the stick afterwards (`diskutil eraseDisk` or `sudo wipefs -a`): the test disk has root autologin.

## What you need (22 §2.3)
- **A Raspberry Pi 5** (a Pi 4 is not a v0 board), the official 27 W PSU, an NVMe HAT + NVMe SSD (or a USB 3 SSD) as the **target**, and a microSD card for the **workbench** system.
- Workbench card: Raspberry Pi OS Lite 64-bit 2026-10-06 (trixie); check the `.img.xz` sha256 starts `483db18a` and ends `2843` before flashing [C-LAB-rauc-1152-016].
- A way to pull power by hand (or a switched outlet) for the power-pull steps (PP-10, [`../common/PP-10.md`](../common/PP-10.md)).

## Route R steps (22's command block, unchanged)
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
