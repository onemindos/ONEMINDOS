# LT-JET-01 · NVIDIA A/B with the OneMind gate, OTA and power cuts (Jetson Orin Nano)

**Status:** kit-ready for steps 1, 4 and 5 (blocked: founder-hardware); steps 2, 3 and 6 also need the Jetson backend B4.7 (BM2), so they are **not ready** · **Time:** about 1 day · **Milestone:** 22 schedules it in week 4; brief 30 lists the Jetson package under BM2 (D-B2.5) · **Serves:** DC-07, DC-08, REC-DEC-18, -35, -47, -49; F-14
**Criteria:** [CRITERIA-22.md](CRITERIA-22.md), copied verbatim from `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §5. They are not edited here.

> **Explain it like I'm the founder.** On a Jetson, NVIDIA's own boot chain owns A/B: the board has two root filesystems (`APP` and `APP_b`) when it is flashed with `ROOTFS_AB=1`, and NVIDIA's tools switch between them. OneMind does not replace that; it plugs its health gate into NVIDIA's "is this new root OK?" hook. This kit first proves NVIDIA's A/B works on your board at all (flash, corrupt one slot, cold power cycles). The second half, where our gate decides and an over-the-air update survives a power cut, needs the Jetson backend code that the build writes in BM2.

## What you need
- The Jetson Orin Nano (Super) dev kit, its PSU, a USB-C cable, and a way to pull power.
- **An x86-64 Linux machine** for flashing: NVIDIA's flash tools do not run on a Mac (brief 30 D-B1.8, [C-W18-021]). An Ubuntu 22.04 or 24.04 laptop or a spare PC works; the Beelink booted from a live USB does too if it has the disk space.
- NVIDIA SDK Manager or the L4T BSP + sample rootfs for **JetPack 6.2.x** (22's step 1). Record the BSP tarball names and their sha256 in the result.

## Steps you can run now (ready)
1. **Step 1, flash A/B.** Put the Jetson in recovery mode and flash JetPack 6.2.x with the redundant rootfs layout (`ROOTFS_AB=1`; NVIDIA's "Root File System Redundancy" section of the Jetson Linux Developer Guide for your L4T release describes the flash command; read it for your exact release, it changes between releases). Then record:
   ```bash
   cat /etc/nv_tegra_release
   sudo nvbootctrl dump-slots-info
   sudo nvbootctrl -t rootfs dump-slots-info
   ```
2. **Step 4, corrupt slot B → boots A.** Only after reading NVIDIA's guide for how your release marks a rootfs slot unbootable (`nvbootctrl -t rootfs set-slot-as-unbootable 1` exists on recent releases; **UNVERIFIED** for yours, check `nvbootctrl --help`). Pass: boots A; `nvbootctrl -t rootfs dump-slots-info` shows the expected slot.
3. **Step 5 (first part), cold power cycle after a hang.** NVIDIA's retry counter ignores cold resets [C-REF3-DC-technical-001]: freeze the board on the slot under test (`echo c | sudo tee /proc/sysrq-trigger` crashes it), pull power, and record which slot boots after power returns, three times.

## Steps that wait for BM2 (not ready)
- **Step 2** (OneMind gate in NVIDIA's validation hook), **step 3** (image-based OTA r36 → r39 with a power cut) and **step 6** (QSPI version pinned in the release manifest) need B4.7: OneMind's own payload verifier, the gate inside the hook with warm resets, and the release-manifest field. The build session writes those in BM2 and then adds their commands here.

## Record
Write `research-output/evidence/lab/founder-hardware/LT-JET-01.md` from [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md), marking steps 2, 3 and 6 `not-tested (needs B4.7)`. Pipe pasted output through `sh lab-kits/common/redact.sh`. Never run any fuse-burning command (`odmfuse`, SB-8; 22 §2.3 rule 4). Nothing Jetson-based is published (Z-01).

## Pass / fail
As in [CRITERIA-22.md](CRITERIA-22.md).
