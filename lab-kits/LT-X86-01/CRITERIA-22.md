<!-- Copied verbatim from research-output/22-HARDWARE-LAB-TEST-PLAN.md (LT-X86-01), 2026-11-11. Do not edit: if 22 changes, re-copy. -->

### LT-X86-01 · RAUC 1.15.2 + fresh-signal k3s gate on real x86 · **G**
**Aliases:** rauc-k3s-gate F1, rauc F1, rauc-1152 x86 leg on hardware, T-W3-01 (RAUC half) · **Prerequisite:** LT-X86-00; spare USB SSD; the Mac Lima setup from `evidence/lab/rauc-1152/README.md` · **Time:** about 1 hour
The kit is `evidence/lab/rauc-1152/` (RAUC built from the upstream v1.15.2 tag, verity-only bundles: the exact configuration REC-DEC-05/31 requires). In emulation it passed every test in run 2 [C-LAB-rauc-1152-011].
```sh
# Mac, inside the disposable Lima VM created as in rauc-1152/README.md §12:
#  1. For hardware: in scripts/guest/grub.cfg.in add console=tty0 before console=ttyS0;
#     add a getty@tty1 autologin drop-in (lab only); replace i6300esb in
#     /etc/initramfs-tools/modules with the watchdog driver found in LT-X86-00 (e.g. iTCO_wdt).
sudo OUT=/var/lab/r1152-out DL=<k3s download dir> bash scripts/build.sh
# Mac host:
limactl copy <vm-name>:/var/lab/r1152-out/disk.img ./disk.img
diskutil list                                    # find the SPARE USB SSD; check its size twice
diskutil unmountDisk /dev/diskN
sudo dd if=disk.img of=/dev/rdiskN bs=4m
# Boot the box from the USB SSD in UEFI mode, Secure Boot OFF. Then on the box:
rauc status
sudo rauc install /data/bundles/good.raucb && sudo systemctl reboot        # expect mark-good
sudo cat /data/onemind/gate.log
sudo rauc install /data/bundles/bad-k3s.raucb && sudo systemctl reboot     # expect mark-bad, back to old slot
sudo rauc install /data/bundles/bad-noagent.raucb && sudo systemctl reboot # stale-Ready trap; expect mark-bad
sudo rauc install /data/bundles/bad-boot.raucb && sudo systemctl reboot    # expect 3 attempts, then fell-back
sudo rauc install /data/bundles/bad-hang.raucb && sudo systemctl reboot    # watchdog reset; 3 attempts, fell-back
sudo rauc install /data/bundles/wrong-key.raucb    # must be refused
sudo rauc install /data/bundles/plain-good.raucb   # must be refused: plain format not allowed
```
- **Pass:** every step ends as expected with **no keyboard input after any reboot**; no slot is committed while `curl -s localhost:10248/healthz` fails. Record the good-commit time and the bad-k3s decision time; set the production gate deadline to about 3× the good-commit time.
- **Fail → consequence:** a commit of a broken k3s, or any boot needing a keyboard → **S2 re-opens** (01 §3.2). If Mender passes LT-X86-08 where RAUC failed, the engine changes (Z-03).
- **Feeds:** REC-DEC-05, -07, -23, -31, -34; DC-12; Z-03. Lab baseline: [C-LAB-rauc-k3s-gate-008] (naive gate commits a broken kubelet), [C-LAB-rauc-k3s-gate-004] (k3s bind-mounts on a read-only root).
