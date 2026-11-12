# LT-X86-01 · RAUC 1.15.2 + fresh-signal k3s gate on real x86 (Beelink)

**Status:** kit-ready (blocked: founder-hardware) · **Time:** about 1 hour on the box, plus about 30 min of image build on the Mac · **Milestone:** BM1 (brief 30 §7, never-cut list) · **Serves:** REC-DEC-05, -07, -23, -31, -34; DC-12; Z-03; R-1, R-2, P-7
**Criteria:** [CRITERIA-22.md](CRITERIA-22.md), copied verbatim from `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §3. They are not edited here. **Prerequisite:** LT-X86-00 done on the same box.

> **Explain it like I'm the founder.** The QEMU battery already proves, inside a virtual machine, that a bad update rolls itself back. This kit proves the same on your **real Beelink**: real firmware, a real USB SSD, a real watchdog chip. You write a test image to a **spare** USB SSD and a stick of test updates to a second USB stick, boot the Beelink from the SSD, and run one command per test. After each reboot you touch nothing: the box must decide by itself whether the update is good (keep it) or bad (go back). Nothing on the Beelink's internal disk is touched.

## What changed from 22's command block (and why)
22's commands build the image with the research lab's script (`evidence/lab/rauc-1152/scripts/build.sh`). This kit builds the **same test design from the repo's own pipeline** (the Containerfile rootfs + `os/assemble/`), which is what the build ships. The steps, bundles and pass/fail rules are the same; only paths change:

| 22 says | This kit |
|---|---|
| `sudo OUT=… bash scripts/build.sh` in a Lima VM | `make fixtures BOARD=x86_64-efi UPTO=T10 HW=1` on the Mac (Docker) |
| add `console=tty0` to `grub.cfg.in` | already there: `os/boards/x86_64-efi/board.yaml` `console:` |
| add a `getty@tty1` autologin drop-in (lab only) | `HW=1` adds `test/qemu/overlay-hw/` (test fixtures only, never in `make image`) |
| replace `i6300esb` with the box's watchdog driver | the initramfs already lists `i6300esb iTCO_wdt sp5100_tco`; if LT-X86-00 found another driver, add it to `os/rootfs/layers/base/usr/share/initramfs-tools/modules.d/onemind-watchdog` before building |
| `/data/bundles/<name>.raucb` | `/run/onemind-test/bundles/<name>.raucb` on a second USB stick labelled `onemind-test` |

## What you need
- The Mac with Docker Desktop running, this repo checked out.
- A **spare USB 3 SSD** (≥ 64 GB) that you are happy to erase, and a **USB stick** (≥ 8 GB) for the test bundles, also erased.
- A monitor and keyboard on the Beelink. Secure Boot **off** for this test (it is LT-X86-03's job).

## Steps
### A. Build (Mac, about 30 min: x86 is emulated on Apple silicon)
```bash
make rootfs BOARD=x86_64-efi
```
```bash
make fixtures BOARD=x86_64-efi UPTO=T10 HW=1
```
Result in `out/fx-x86_64-efi/`: `disk.img` (24 GiB, mostly empty), `bundles.img`, `t0.json` (must say `"pass": true`), `SHA256SUMS`. The throwaway signing keys were destroyed inside the container; only the public `dev-ca.cert.pem` is kept.

### B. Write the SSD and the stick (Mac)
```bash
sh lab-kits/common/check-target-disk.sh /dev/diskN
```
Type the size twice; only then:
```bash
diskutil unmountDisk /dev/diskN && sudo dd if=out/fx-x86_64-efi/disk.img of=/dev/rdiskN bs=4m status=progress
```
Repeat both commands for the stick (`/dev/diskM`) with `if=out/fx-x86_64-efi/bundles.img`.

### C. Run (on the Beelink, booted from the SSD in UEFI mode, Secure Boot OFF, stick plugged in)
The console logs in as root by itself (test image only). First:
```bash
mkdir -p /run/onemind-test && mount -o ro /dev/disk/by-label/onemind-test /run/onemind-test
rauc status
cat /data/onemind/gate.log
```
Expect `RESULT committed-boot slot=A version=1` and `K3S-FRESH ok`. Then 22's sequence, one line at a time; after each reboot wait, touch nothing, then mount the stick again and read `/data/onemind/gate.log`:
```bash
rauc install /run/onemind-test/bundles/good.raucb && systemctl reboot          # expect mark-good slot=B version=2
rauc install /run/onemind-test/bundles/bad-k3s.raucb && systemctl reboot       # expect mark-bad verdict=image-bad, back to B
rauc install /run/onemind-test/bundles/bad-noagent.raucb && systemctl reboot   # stale-Ready trap; expect mark-bad
rauc install /run/onemind-test/bundles/bad-boot.raucb && systemctl reboot      # expect 3 attempts, then fell-back
rauc install /run/onemind-test/bundles/bad-hang.raucb && systemctl reboot      # watchdog reset x3, then fell-back
rauc install /run/onemind-test/bundles/wrong-key.raucb                          # must be refused
rauc install /run/onemind-test/bundles/plain-good.raucb                         # must be refused: plain not allowed
curl -s localhost:10248/healthz; echo                                          # "ok" on the committed slot
cat /data/onemind/gate.log /data/onemind/bad-releases
```
### D. Record
1. Copy the gate log off the box (the stick is read-only; use a third stick or a photo), run it through `sh lab-kits/common/redact.sh`, and write `research-output/evidence/lab/founder-hardware/LT-X86-01.md` from [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md).
2. Write down the **good-commit time** (`RESULT mark-good … after Ns`) and the **bad-k3s decision time**. 22 says: set the production gate deadline to about 3× the good-commit time (`ONEMIND_GATE_TIMEOUT` in `os/gate/onemind-health-gate.default`).
3. Wipe the SSD afterwards (22 §2.3 rule 3): `sudo wipefs -a /dev/sdX` on Linux, or erase it in Disk Utility.

## Expected output
Each gate line looks like the QEMU battery's (`test/qemu/CRITERIA.md`), for example
`HEALTH-GATE: 12:00:00 RESULT mark-bad slot=A version=3 verdict=image-bad after 300s (last: fail G1: …) -> reboot to B`.
On bad-boot and bad-hang the screen shows `BAD-BOOT` or `BAD-HANG` three times and GRUB's `GRUB-RAUC: … A_TRY=3`.

## Pass / fail
As in [CRITERIA-22.md](CRITERIA-22.md). In short: every step ends as expected with **no keyboard input after any reboot**, and no slot is committed while the kubelet `healthz` fails. A FAIL re-opens S2 (Mender, LT-X86-08).
