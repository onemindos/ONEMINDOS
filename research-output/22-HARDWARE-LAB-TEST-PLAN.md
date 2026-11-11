# 22 · Hardware lab test plan (founder-runnable)

**Date:** 2026-11-11 · **Owner of the tests:** Zeus · **Status:** plan complete; **no test in this file has been run on real hardware yet** · **Synced to `01` revision 4** (2026-11-11): two new emulated results (§1.1), W2-HW-3 before gate G1, the S1 decision map, and the founder tests rev. 4 asks for (LT-PI5-14, LT-VM-20, extended LT-JET-01, LT-VM-03, LT-VM-04, LT-VM-13, LT-X86-12) · **Read with:** [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) §10 and §12 (what the VM lab proved and what it left open), [`evidence/decision-critical.md`](evidence/decision-critical.md) (each DC's Result block names its founder test), [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)
**Serves requirements:** R-1, R-2, R-3, M-2, M-6, P-1, P-7, P-9, H-3, N-2, N-7, U-4, F-11, F-12, F-14, AI-9, D-002, D-004
**Claim IDs** resolve in `evidence/claims/*.csv`; this file's new rows are `C-LABPLAN-###` (sources in `evidence/sources/LABPLAN.md`).

> ### Explain it like I'm the founder
> Everything we tested so far ran inside **virtual machines** on a Mac. A virtual machine is very good at checking *logic* ("does a bad update roll back?"), but it cannot tell you what a **real** power cord, a **real** PC's firmware, a **real** Raspberry Pi 5 boot chip or a **real** Jetson does. Those are exactly the places where update systems brick devices in the field.
> This file collects **every test that only you can run**, because only you have (or will buy) the hardware and the access to your live cluster. There were about 150 of them scattered across 20 files under different names. Here each one gets **one stable ID**, the device, the **exact commands**, what counts as **pass or fail**, **which decision it changes**, and **what must be true before you start**.
> They are sorted so that the tests that could **change the foundation decision** come first. Run the first 12 rows of §1 in the first six weeks and you will know whether the plan (a OneMind image on Ubuntu 26.04 or Debian 13 + RAUC A/B + k3s) holds on real metal. One Pi 5 test, bootc on a real Pi (LT-PI5-02), can change which base wins, so it runs before week 4. Everything else refines settings or validates product features. One rule above all: **on your live cluster you only look, never touch** (§9).

---

## Contents

1. [The critical path: the 16 tests that matter most](#1-the-critical-path-the-16-tests-that-matter-most)
2. [How to use this file (IDs, impact levels, recording, safety)](#2-how-to-use-this-file)
3. [x86 box: Dell Latitude 5540 and Beelink U55](#3-x86-box-dell-latitude-5540-and-beelink-u55)
4. [Raspberry Pi 5](#4-raspberry-pi-5)
5. [Jetson Orin Nano Super](#5-jetson-orin-nano-super)
6. [Mac + disposable VMs + CI (no extra hardware)](#6-mac--disposable-vms--ci-no-extra-hardware)
7. [Cloud or local NVIDIA RTX GPU](#7-cloud-or-local-nvidia-rtx-gpu)
8. [Phones, tablets, XR headsets and desktop clients (incl. GrapheneOS + ATAK)](#8-phones-tablets-xr-headsets-and-desktop-clients)
9. [Live cluster: read-only checks on the founder's DOKS cluster](#9-live-cluster-read-only-checks)
10. [Founder actions that are not lab tests](#10-founder-actions-that-are-not-lab-tests)
11. [What competitors do (how they test on hardware)](#11-what-competitors-do)
12. [Recommendations (with requirement IDs)](#12-recommendations)
13. [Alias index: old ID → new ID](#13-alias-index)
14. [Glossary](#14-glossary)
15. [Gaps, assumptions and what this file does not do](#15-gaps-assumptions-and-limits)

---

## 1. The critical path: the 16 tests that matter most

Ordered by **decision impact**, then by how early they can run. "Flips" means a failure changes a decision in `01-…`, not just a setting.

| # | ID | Device | What it settles | If it fails | Earliest |
|---|---|---|---|---|---|
| 1 | **LT-X86-00** | Dell + Beelink + Mac | Which machines can run which tests (TPM, Secure Boot, CPU level) | Re-plan the x86 rows; nothing flips | Week 1 |
| 2 | **LT-X86-01** | Dell or Beelink | RAUC 1.15.2 + fresh-signal k3s gate on real x86 (REC-DEC-05/07/34) | **Flips S2** toward Mender if Mender passes LT-X86-08 | Week 2 |
| 3 | **LT-X86-02** | same | 10 real power pulls under RAUC (DC-12, REC-DEC-34) | Corrupt grubenv/ESP → **flips S2** or forces a layout change | Week 2 |
| 4 | **LT-PI5-01** | Pi 5 | RAUC + Pi firmware `tryboot` (F-PI5; DC-19, REC-DEC-32) | Pi 5 tier "not proven"; Rugix (proven tryboot path) re-opens for Pi | Week 3 |
| 5 | **LT-PI5-02** | Pi 5 | bootc on a real Pi 5 (W2-HW-3; REC-DEC-33, REC-DEC-44) | **Fail → S1 result becomes Debian 13** (6–5); pass with #219 fixed and an automatic Pi commit → bootc vs Ubuntu re-count (`01` §3.1.6 h) | Week 3–4, **before G1** |
| 6 | **LT-X86-03** | Dell | Secure Boot A/B + TPM unlock on real firmware with RAUC 1.15.2 (F-SB-1; DC-18) | **Re-opens DC-18** (boot route REC-DEC-20) | Week 3 |
| 7 | **LT-X86-04** | Dell | Power pull under Secure Boot (F-SB-3) | Same as #6 | Week 3 |
| 8 | **LT-VM-01** | VM, then x86/Pi | Unsigned plugins refused across a slot switch (T-W19-01 security variant) | **D3 changes**: extensions only inside the RAUC bundle (01 §4.8) | Week 2 |
| 9 | **LT-X86-12** | Dell | OneMind-signed kernel module loads under Secure Boot (T-W19-03): first arm, a OneMind shim with its own `vendor_cert` on the stock kernel (REC-DEC-48) | Both arms fail → REC-DEC-25 (OneMind-built kernel for the Secure Boot release) | Week 4 |
| 10 | **LT-PI5-03** | Pi 5 4 GB | Hardened k3s fits 4 GB over 30 days (DC-10, REC-DEC-22) | Platform-node floor rises to **8 GB** | Week 3 start |
| 11 | **LT-PI5-04** | Pi 5 8 GB + x86 | etcd vs SQLite write volume, corrected (T-W5-03; REC-DEC-38) | Servers stay on SQLite | Week 3 |
| 12 | **LT-JET-01** | Orin Nano | NVIDIA A/B + OneMind gate + OTA power cut (T-W3-06; DC-07, REC-DEC-35) | "One release contract" fails for Jetson; beta slips | Week 4 |
| 13 | **LT-VM-03** | VM, then x86 | In-place major rebase on both legs, founder-hours, then N → N+2 updates (T-W3-04; DC-05, REC-DEC-16) | Old-slot RAUC cannot install N+1/N+2 → DC-05 re-opens; > 4–6 founder-weeks weakens the Debian leg | Week 4 |
| 14 | **LT-GPU-01** | RTX (cloud) | NVIDIA driver on the core leg + k3s, upgrade survival (DC-13, REC-DEC-19/37) | On the Debian leg: Pro/Omni GPU tiers move to the Ubuntu flavor | Week 6 |
| 15 | **LT-VM-05** | VM | Mender 3-try boot script (Mender F3) | Pass removes RAUC's "boot tries" tie-break row (01 §3.2) | Week 2 |
| 16 | **LT-JET-06** | Build VM + Orin | meta-tegra + 6.18 LTS kernel on Jetson (LAB-W7-6; DC-09, REC-DEC-18) | Jetson stays on L4T Ubuntu (needs Canonical's answer, Z-01) | Week 8–12 |

Two founder actions outrank every lab test: **send the Canonical/counsel questions (LT-BIZ-01, Z-01)**, because under `01` rev. 4 Canonical's answer is the condition on the base-OS decision of record and can move S1 to bootc on its own (§3.1.6 h), and **decide where the Dell's OneMind tests boot from** (a spare USB SSD, so the Omarchy pilot install is never wiped; 11 §10).

**Rev. 4 order note.** LT-PI5-02 (W2-HW-3) runs **before gate G1 (week 4)**, after LT-PI5-01 on the same Pi with a separate card or SSD (REC-DEC-44). Its outcome is read against the decision map in `01` §3.1.6 (h), which was written on 2026-11-11, before the test or Canonical's answer exists. A box shipped on Ubuntu or Debian + RAUC cannot move to bootc without a reflash [C-STEEL4-bootc-025], so the test must come before anything ships. Founder decisions **Z-39 and Z-40** (`26-…`) should be logged in `evidence/scorecard-weights.md` §8 **before** LT-PI5-02 runs; otherwise a "pass" can end in a 4–4 draw with no written rule.

### 1.1 What the newest emulated labs already showed (rev. 4)

Two labs ran on 2026-11-11 after this file was first written. Both **passed**. They do not replace any hardware test below, but they narrow what the hardware tests have to find.

| Lab | Result | What it changes in this file | Still needs real hardware |
|---|---|---|---|
| **aarch64-gate** ([`evidence/lab/aarch64-gate/`](evidence/lab/aarch64-gate/)): RAUC 1.15.2 + k3s v1.37.2+k3s1 arm64 + the unchanged fresh-signal gate, Debian 13 arm64 guest under native Arm virtualisation (QEMU + HVF), GRUB arm64-efi | **PASS, two full runs (T1–T11)** [C-LAB-aarch64-gate-004]: a good update committed 31 s after the trial gate started [C-LAB-aarch64-gate-005]; k3s-broken and stale-Ready updates rolled back at 300 s with no input; a kernel panic and a hang were each tried 3 times, then dropped; power cuts mid-install and in the commit window recovered; the 9 gate files ran **byte-identical** on x86_64 and arm64 [C-LAB-aarch64-gate-009]; the naive gate again committed a k3s with no kubelet [C-LAB-aarch64-gate-010]. The arm64 RAUC build is reproducible (same hash as rev. 3) [C-LAB-aarch64-gate-001] | LT-VM-08's aarch64 part is **done**. LT-PI5-01 now tests only what an emulator cannot: Pi firmware `tryboot`, the Pi kernel, SD/NVMe and real power. Two lessons enter the tests: (1) the gate deadline is wall-clock time, so a slow host can turn a good trial into a rollback (nested KVM stretched a 300 s window to 411 s) [C-LAB-aarch64-gate-006]; set the production deadline from real timings with ≥ 3× margin, and never run timing-sensitive gate tests on nested virtualisation in CI; (2) the Pi 5 firmware loads `kernel_2712.img` with **16 KiB pages** by default [C-LAB-aarch64-gate-007], while the lab used a 4 KiB generic kernel, so LT-PI5-01 adds step A1 | Pi `tryboot` and `autoboot.txt` writes; the 16 KiB-page kernel with k3s and containerd; one-shot `tryboot` under a power pull during the trial (inferred, not tested: the update is lost and marked bad [C-LAB-aarch64-gate-011]); real power loss on SD/NVMe |
| **secureboot-1152** ([`evidence/lab/secureboot-1152/`](evidence/lab/secureboot-1152/)): the X-2R Secure Boot suite re-run with RAUC 1.15.2 (`efi` backend, one signed UKI per slot, `bundle-formats=verity`), OVMF with only lab keys + swtpm, x86_64 | **PASS, two runs** [C-LAB-secureboot-1152-005]: enforced Secure Boot with TPM (PCR 7) data unlock; A → B via BootNext; health-gated rollback; the firmware refused a tampered and an unsigned UKI and fell through to the committed slot in the same power-on; data stayed locked with Secure Boot off. EFI variable effects matched RAUC 1.13 step for step [C-LAB-secureboot-1152-006]; a validly signed **plain** bundle was refused under verity-only [C-LAB-secureboot-1152-007]. RAUC 1.15 also finds the booted slot from EFI `BootCurrent` [C-LAB-secureboot-1152-002, C-LAB-secureboot-1152-008]. **The downgrade gap persists:** an old, validly signed factory UKI booted on a newer root and the gate committed it [C-LAB-secureboot-1152-009] | LT-X86-03 and LT-X86-04 now use this kit, so the Dell runs the exact configuration `01` recommends. Every shipped UKI carries `rauc.slot=<bootname>` on its signed command line, so slot detection never depends on a firmware auto-entry (the lab's SB-2′). LT-X86-03 adds an `efibootmgr` + `rauc status` check. The anti-downgrade fixes (recovery-only factory UKI, kernel/root version match before `mark-good`, SBAT or db rotation) stay required; `prevent-late-fallback` (RAUC ≥ 1.14) is documented but untested [C-LAB-secureboot-1152-010] and is tested in LT-VM-04 | Real PC firmware (auto-entries, option ROMs), a power pull under Secure Boot, and Secure Boot on the **Ubuntu** leg (both labs ran Debian guests; LT-VM-20) |

Both labs ran on Debian 13 guests. Under `01` rev. 4, that is why the Secure Boot cell of the Ubuntu, Yocto and Buildroot stacks is marked `doc-only` (S1-12), and why LT-VM-20 repeats the Secure Boot suite on the Ubuntu 26.04 leg. **FIX5 (2026-11-11):** the research run pre-registered LT-VM-20 as spike [`evidence/lab/ubuntu-secureboot/`](evidence/lab/ubuntu-secureboot/) and tried to run it. It is **BLOCKED (environment)**: the Ubuntu archive does not resolve from the research environment, and the run did not bypass that [C-FIX5-001, C-FIX5-002]. The kit is published and ready, but it has never been executed [C-FIX5-003].

---

## 2. How to use this file

### 2.1 IDs

- **New stable IDs:** `LT-<DEVICE>-NN`. Devices: `X86`, `PI5`, `JET`, `VM`, `GPU`, `EUD` (phones, tablets, XR, desktop clients), `CLU` (live cluster), `BIZ` (non-lab actions). Numbers are ordered by impact inside each device and will not be reused.
- **Old IDs keep working.** Each test lists its aliases (T-W3-04, F-PI5, LAB-W7-1, W10-T1, …), and §13 maps every old ID to its new one.

### 2.2 Impact levels

| Level | Meaning |
|---|---|
| **G (gate)** | A release gate in `01-…` (REC-DEC-34 names F1/F2, F-PI5, F-SB-1…3), or a failure re-opens a scorecard decision (S1–S5) or a DC |
| **P (parameter)** | Sets a number or default (gate deadline, RAM floor, RT profile, datastore) without changing the architecture |
| **V (validate)** | Checks a Tier B product feature (dashboard, apps, family, AI tools) |

### 2.3 Before any hardware test

1. **Buy by 2026-11-16** (11 §10.1): Pi 5 8 GB + M.2 NVMe HAT + NVMe SSD + official 27 W PSU; Jetson Orin Nano Super dev kit. Also: one **spare USB 3 SSD (≥ 64 GB)** for the x86 boxes, a microSD card (≥ 16 GB), a USB-C/AC **power meter**, and (optional, saves hours) a switched outlet you can toggle by hand or by script for power pulls.
2. **Never write test images to a disk you care about.** Every x86 test boots from the spare USB SSD with the internal disk untouched. Run `diskutil list` (Mac) or `lsblk -o NAME,SIZE,MODEL` (Linux) and check the target's size **twice** before any `dd`.
3. **Lab-only shortcuts** in the kits (fixed machine-id, autologin on the console, lab keys) must never reach a shipped image. Wipe the test SSD afterwards (`sudo wipefs -a /dev/sdX`).
4. **Irreversible steps are excluded.** No Raspberry Pi OTP writes, no Jetson fuse burning, no Samsung bootloader unlock. Where a test touches Secure Boot keys, back up the firmware's current keys first and know how to "Restore factory keys".

### 2.4 The shared power-pull protocol (PP-10)

Used by LT-X86-02/-04/-08/-09/-10/-11, LT-PI5-01 and LT-JET-01. Pull the **power cord** (not a soft power-off) **10 times**: (1) start of the write, (2) middle, (3) the second the write says `done`, (4) during the reboot, (5) during the first (trial) boot of the new slot before the gate decides, then (6–10) spread randomly across the same phases. After each pull: power on, touch nothing for 10 minutes, then record which slot booted, the bootloader state, a read-only filesystem check of the boot partition, and the last health-gate line. **Pass:** 10/10 end on a working, committed slot with no keyboard input, and a re-run of the install succeeds. Why real pulls: QEMU's kill cannot drop the disk's own write cache, and the FAT `grubenv`/ESP write is the classic weak point (`evidence/lab/rauc/README.md` §8).

### 2.5 Recording results (and keeping the public repo clean)

- One file per test: `research-output/evidence/lab/founder-hardware/<LT-ID>.md` (W10-T1 already reserved this folder). Copy the template below. The build session then turns each result into a claim row.
- **Never commit:** serial numbers, MAC addresses, IP addresses, hostnames, tailnet names, usernames, home paths, Android tombstones or bug reports (GrapheneOS warns they can hold personal data [C-W14-006]), kubeconfig contents, Secret values, or raw `doctl`/`kubectl` output from the live cluster. Summarise counts and versions instead. Run `gitleaks dir` before committing.

```markdown
# <LT-ID> result
- Date / tester: <date> / founder
- Device: <model>, firmware/BIOS <version>, RAM <GB>, disk <type/size>   (no serial numbers)
- Software: image or kit commit <sha>, kernel <version>, k3s <version>, engine <name version>
- Criteria (copied from 22-… before running): <pass/fail text>
- Result: PASS / FAIL / BLOCKED (<exact reason>)
- Numbers: <timings, MiB, MiB/day, µs, W>
- Notes / surprises:
- Decision consequence applied: <DC / REC / Z id, or "none">
```

---

## 3. x86 box: Dell Latitude 5540 and Beelink U55

**What each can prove** (11 §10): the **Dell** (i5-1345U, TPM 2.0, Secure Boot with a custom key mode in its BIOS [C-W10-043]) carries the whole x86 Lite path including Secure Boot; it is also the Omarchy pilot, so OneMind tests boot from the spare USB SSD. The **Beelink U55** (likely i3-5005U; Intel servicing ended 2021-06-30 [C-W10-041]; TPM and Secure Boot unknown [C-W10-044]) is the "old bring-your-own PC" and the second node, never a recommended target.

### LT-X86-00 · Inventory of the founder machines · **G (enabler)**
**Aliases:** W10-T1, X-1, X-3, W2-HW-5, Q290 · **Prerequisite:** a live USB of Debian 13 (boot it; nothing is installed) · **Time:** 30 min per machine
```sh
# On the Dell and on the Beelink (booted from a Debian 13 live USB):
lscpu | grep -E 'Model name|^CPU\(s\)'
sudo dmidecode -t system -t bios | grep -E 'Product Name|Version|Release Date'   # do NOT record the serial number
ls /sys/class/tpm; systemd-analyze has-tpm2
mokutil --sb-state
mokutil --db | grep -i "UEFI CA 2023"          # Microsoft 2023 CA present?
grep MemTotal /proc/meminfo
lsblk -d -o NAME,ROTA,TRAN,SIZE
/lib64/ld-linux-x86-64.so.2 --help | grep -E 'x86-64-v[234]'   # "x86-64-v3 (supported)" = RHEL 10 floor [C-W2-011]
sudo dmesg | grep -i watchdog                   # which hardware watchdog driver (e.g. iTCO_wdt) the image needs
fwupdmgr get-devices                            # LVFS firmware support
# On the Mac:
sysctl -n machdep.cpu.brand_string hw.memsize; sw_vers -productVersion
```
- **Pass:** every field of the W10-T1 template filled (device, CPU, RAM, disk type, TPM yes/no, Secure Boot state, BIOS version, LVFS yes/no, x86-64 level, watchdog driver); no "unknown". U55 CPU confirmed.
- **Fail → consequence:** none on the architecture. U55 without TPM → it is marked "encryption with recovery key, no TPM" in the install matrix (X-3). A CPU below x86-64-v3 is excluded from the bootc Industrial profile (W2-HW-5).
- **Feeds:** Q290, 26 §B "Dell 5540's state", the x86 rows below.

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

### LT-X86-02 · Ten real power pulls under RAUC · **G**
**Aliases:** rauc-k3s-gate F2, rauc F2 (+F2b sweep), T-W3-01, Q58 · **Prerequisite:** LT-X86-01 passed on the same box · **Time:** about 1.5 hours
Follow PP-10 (§2.4) during `sudo rauc install /data/bundles/good.raucb` and the trial boot. After each pull:
```sh
rauc status
sudo grub-editenv /boot/efi/EFI/BOOT/grubenv list
sudo fsck.vfat -n /dev/disk/by-partlabel/esp
sudo tail -1 /data/onemind/gate.log
```
- **Pass:** 10/10 end on a working slot without a keyboard; every half-written slot ends `OK=0`; a pull during the trial gate ends with the new slot committed on a later try (the 3-try design; emulated test T9).
- **Fail → consequence:** a corrupt grubenv or ESP, or a box that does not boot → stop; S2 and the boot layout re-open (01 §4.3).
- **Feeds:** REC-DEC-34 (release gate), DC-12, Q58. Repeat once on the Beelink (old firmware, different disk) after the Dell passes.

### LT-X86-03 · Secure Boot A/B with OneMind keys + TPM-sealed data on real firmware · **G**
**Aliases:** F-SB-1, X-2, W10-T2, Q206/Q207 · **Prerequisite:** LT-X86-00 shows TPM 2.0 and a custom-key mode (Dell); spare USB SSD; **backup of the firmware's current keys** · **Time:** about 2 hours
Kit: **`evidence/lab/secureboot-1152/`** (rev. 4: RAUC 1.15.2 with `bundle-formats=verity`, passed twice in OVMF + swtpm [C-LAB-secureboot-1152-005]); it reuses `evidence/lab/secureboot-rauc/` (RAUC `efi` backend, one signed UKI per slot, data key on PCR 7 + signed PCR 11; build steps in its README §13).
```sh
# Lima VM: build, then create the enrolment files with efitools
bash scripts/build.sh            # secureboot-1152/scripts (see its README §R.7 and secureboot-rauc/README.md §13)
cert-to-efi-sig-list -g <guid> db.crt db.esl && sign-efi-sig-list -k KEK.key -c KEK.crt db db.esl db.auth
#   (same for KEK signed by PK, and PK self-signed); copy disk.img, *.crt, *.auth out with limactl copy
# Firmware setup on the Dell: back up current keys -> clear keys (setup mode) -> enroll db, KEK, then PK last
#   (or boot once with Secure Boot off and run: sudo efi-updatevar -f db.auth db ; ... KEK ; ... PK)
# Enable Secure Boot, boot the USB SSD, then for each test bundle:
sudo rauc install /mnt/bundles/<bundle>.raucb && sudo systemctl reboot
efibootmgr; rauc status; mokutil --sb-state
sudo journalctl -b | grep -E 'DATA:|HEALTH-GATE'
# rev. 4, after the first boot: rauc status must say "Booted from: rootfs.0 (OneMind-A)";
# efibootmgr -v shows whether the firmware created its own auto-entries (the downgrade path E1)
```
- **Pass:** the same outcomes as the emulated T1–T5 (A → B, rollback, unhealthy slot rejected) with no keyboard input; the data partition unlocks without a prompt on A, on B and after rollback; the firmware refuses the tampered and unsigned UKIs (v4/v5); the signed plain bundle is refused; `Booted from` names `OneMind-A`.
- **Fail → consequence:** any difference → record firmware model and BIOS version; **DC-18 re-opens**; fallback is a recovery-key prompt (07 X-2). **Undo:** restore the backed-up keys or "Restore factory keys".
- **Feeds:** DC-18, REC-DEC-08, -20, -21, -34; Z-18/Z-19. Known gap to watch: an old signed kernel can boot against a newer root, and this persists on RAUC 1.15.2 [C-LAB-secureboot-rauc-018, C-LAB-secureboot-1152-009]; check the version-match gate rule rejects it, and record any firmware auto-entry `efibootmgr -v` shows.

### LT-X86-04 · Power pull under Secure Boot · **G**
**Aliases:** F-SB-3 · **Prerequisite:** LT-X86-03 passed · **Time:** 1.5 hours
PP-10 (§2.4) during `rauc install` and the first boot of the new slot, on the LT-X86-03 (RAUC 1.15.2) image. After each pull: `efibootmgr -v | grep -i bootorder`, `rauc status`, `mokutil --sb-state`, `sudo journalctl -b | grep DATA:`.
- **Pass:** 10/10 end on a booting, Secure-Boot-verified, committed slot with data unlocked by the TPM.
- **Fail:** a corrupted EFI variable store, a refused boot with no fallback, or a recovery-key prompt → DC-18 re-opens. **Feeds:** REC-DEC-34.

### LT-X86-05 · Option ROMs with owner-only keys · **P**
**Aliases:** F-SB-2 · **Prerequisite:** LT-X86-03; ideally a discrete GPU or add-in NIC (the Dell has none; record "not applicable" and repeat on the first ODM box). Boot with only lab keys enrolled.
- **Pass:** display and network firmware work before the OS starts. **Fail:** no display or PXE before the OS → Microsoft's third-party UEFI CA must stay in db (decision for Z-19).

### LT-X86-06 · dbx update without a prompt + PCR 15 volume check · **G**
**Aliases:** SB-5b, DC-18 founder test · **Prerequisite:** LT-X86-03 image; can run first in the `secureboot-rauc` QEMU lab, then on the Dell
1. Apply a test **dbx** update between an A → B update after re-sealing the TPM policy first (01 §4.3 SB-5). **Pass:** no recovery-key prompt.
2. Replace the data partition with a **different LUKS2 volume carrying the same UUIDs** (the filesystem-confusion attack [C-REF3-DC-security-009]). **Pass:** the initrd measures the unlocked volume into PCR 15, detects the mismatch and **stops booting**; it never falls back to a passphrase and continues in the measured state.
- **Fail → consequence:** REC-DEC-21/36 are not met; Secure Boot release blocked. **Feeds:** DC-18, REC-DEC-21, -36.

### LT-X86-07 · Firmware key updates survive power loss (ODM qualification) · **P**
**Aliases:** "ODM db/KEK update test" (01 §4.3, REC-DEC-36) · **Prerequisite:** LT-X86-03; run on the Dell as the reference, then on each ODM candidate (Intel N150 box, 11 §10.1)
1. From the OS, apply an authenticated **db** append (`sudo efi-updatevar -a -f db-new.auth db`) and pull the power mid-write (3 times). 2. In setup mode, enrol PK and pull the power during enrolment (3 times). 3. Check the shipped PK is not a known test key (PKfail-class): `mokutil --pk | grep -iE 'DO NOT TRUST|DO NOT SHIP'`.
- **Pass:** the variable store stays consistent and the box boots every time; no test PK. **Fail:** reject that firmware/ODM. **Feeds:** REC-DEC-36, W10-R9.

### LT-X86-08 · Mender on the same hardware (runner-up) · **P** (G if LT-X86-01 fails)
**Aliases:** mender F1, F2 · **Prerequisite:** LT-X86-00; spare USB SSD · **Time:** about 2.5 hours
```sh
# Lima VM (kit: evidence/lab/mender/); for hardware add console=tty0 in scripts/guest/11_bootargs_grub.cfg,
# a getty@tty1 autologin drop-in (lab only) and the box's watchdog driver
sudo OUT=/var/lab/mender-out DL=<k3s dir> GE=<grub-mender-grubenv@d7c3ec2 dir> bash scripts/build.sh
# write disk.img to the spare SSD as in LT-X86-01; on the box:
sudo mender-update install /data/artifacts/good.mender && sudo systemctl reboot   # then bad-k3s, bad-noagent, bad-boot, bad-hang
sudo grub-mender-grubenv-print; sudo mender-update show-artifact
```
- **Pass (F1):** same verdicts as RAUC with no keyboard, `GATE-SCRIPT-RAN yes` on every commit. **F2 (PP-10):** 10/10 working slot, both env copies agree; a pull during the trial gate is **expected** to abandon the update (stock Mender allows one trial boot [C-LAB-mender-003]).
- **Consequence:** with LT-VM-05, decides whether Mender can meet 01 §4.2 item 3. **Feeds:** S2, REC-DEC-26, Z-03.

### LT-X86-09 · Rugix on hardware with power pulls · **P**
**Aliases:** debian-rugix §6 "on real hardware", T-W3-01 (Rugix half) · **Prerequisite:** LT-X86-00
Build with `evidence/lab/debian-rugix/scripts/10-build.sh amd64`, write `build/v1-amd64/system.img` to the spare SSD, repeat its T1–T3, then PP-10 during `rugix-ctrl update install`.
- **Pass:** every boot comes up on the old release, and the update reinstalls and commits. **Consequence:** keeps Rugix as the documented alternative (W3-REC-01); feeds the Rugix steelman's exit conditions (01 §6.7).

### LT-X86-10 · Same RAUC suite on both bases (Debian 13 and Ubuntu 26.04) · **P**
**Aliases:** ubuntu-2604-leg §10 hardware row · **Prerequisite:** LT-X86-01 passed
Build `scripts/build-ubuntu.sh RAUC_MODE=src RAUC_SRC=<v1.15.2 checkout>` (the version OneMind ships; `RAUC_MODE=archive` only as a reference) in `evidence/lab/ubuntu-2604-leg/`; run LT-X86-01 and PP-10 on each image.
- **Pass:** identical verdicts on both bases. **Consequence (rev. 4):** both legs build until the G6 base lock (REC-DEC-17, REC-DEC-42), and the Ubuntu leg is the decision-of-record leg. A difference is recorded for the lock gate; it can become an S1 tie-break row only through a `scorecard-weights.md` §8 entry logged **before** the run (`01` §3.1.6 h).

### LT-X86-11 · Fedora/AlmaLinux bootc + greenboot on x86 hardware · **P**
**Aliases:** fedora-bootc H1–H5 · **Prerequisite:** LT-X86-00; build `evidence/lab/fedora-bootc/scripts/Containerfile` with `--platform linux/amd64` in a Linux VM, write the disk with bootc-image-builder `--type raw`

| Step | Commands | Pass |
|---|---|---|
| H1 | flash, boot, `sudo bootc status`; `journalctl -u greenboot-healthcheck` | booted ref = your registry ref; health check "passed" |
| H2 | push v3-bad to `:stable`; `sudo bootc upgrade && sudo reboot`; touch nothing 5 min | `cat /usr/share/onemind/version` = previous good; boot −1 journal shows "Rollback successful" |
| H3 | large update; `sudo bootc upgrade`; pull the cord during layer progress | old version boots; `sudo ostree fsck` clean |
| H4 | `sudo bootc upgrade` (staged), `sudo reboot`, pull the cord 1–2 s after the screen goes dark; power on; `sudo ostree admin status`; reboot again | same version after the second reboot. **Expected FAIL** with stock greenboot 0.16.4/0.16.5 (silent downgrade, #219 [C-LAB-fedora-bootc-011, C-LAB-fedora-bootc-013]) |
| H5 | `sudo bootc switch <registry>/onemind/lab-alt:latest && sudo reboot` | marker = `alt`; `/var` data intact |

- **Consequence:** H4 failing confirms #219 on hardware; while #219 is open, a LT-PI5-02 pass does not trigger the bootc re-count in `01` §3.1.6 (h). **Feeds:** S1, REC-DEC-33, DC-01.

### LT-X86-12 · Signed driver-pack module under Secure Boot · **G**
**Aliases:** T-W19-03 · **Prerequisite:** LT-X86-03 image with `module.sig_enforce=1` (lockdown on); the stock kernel of each core leg (Debian 13, Ubuntu 26.04)
**Arm 0 (baseline, db key only):**
```sh
sudo modprobe <onemind-signed-test-module>     # built and signed with the OneMind module key
sudo insmod ./unsigned-test.ko                 # must be refused
sudo dmesg | grep -iE 'module verification|Lockdown|Key was rejected'
cat /proc/keys | grep -i asymmetri             # which keyrings hold which keys
```
**Expected:** refused. A key in UEFI db lands in the platform keyring, which is not trusted for modules [C-DEC-008].
**Arm 1 (rev. 4, REC-DEC-48: the first arm of T-W19-03):** boot through a **OneMind-built shim** whose embedded `vendor_cert` is the OneMind module key, the shim signed with the factory db key. The DC-21 technical refuter found in the source that shim publishes `vendor_cert` in MokListRT and that Linux 6.12 loads it into the `.machine` keyring, which is trusted for modules ([`evidence/adversarial/DC-21-technical.md`](evidence/adversarial/DC-21-technical.md); its sources are cited there under colliding REF4 IDs and are not ledgered, so treat this as **untested**). Repeat the Arm 0 commands, plus `sudo keyctl show %:.machine` and `mokutil --list-enrolled`.
- **Pass:** on the stock kernel, **without any console (MOK) step**: the OneMind-signed module loads, the unsigned one is refused, and the OneMind key appears in `.machine`. Run on both legs' kernels and record each.
- **Consequence:** Arm 1 passes → the Secure Boot release keeps the stock kernel (K1), with a OneMind shim fork and its SBAT upkeep as a recurring cost. Arm 1 fails → **Arm 2: K2-hybrid** (a OneMind-built LTS kernel with the module key built in) for the Secure Boot release (REC-DEC-25; Z-18/Z-19).

### LT-X86-13 · Real-time latency on x86 under k3s · **P**
**Aliases:** T-W18-7, LAB-W7-1 (x86 part), Q11 · **Prerequisite:** Debian 13 with `linux-image-rt-amd64` and stock kernels; k3s + 10 pods
```sh
sudo apt install rt-tests stress-ng linux-image-rt-amd64
stress-ng --cpu 4 --io 2 --vm 2 --vm-bytes 50% -t 1h &      # load
sudo cyclictest -m -Sp90 -i200 -h400 -D1h -q > ct-<kernel>-load.txt
# repeat idle, then with isolcpus=2,3 nohz_full=2,3 on the kernel command line and the kubelet static CPU manager
```
- **Pass:** RT kernel, isolated cores, under load: **max < 250 µs**; report p99.9 and max for every case. **Fail:** investigate SMIs/firmware before blaming the OS. **Feeds:** DC-14, REC-DEC-29 (RT profile), robot-rt default.

### LT-X86-14 · Whole-box restore and backup power cut · **G** (for M4)
**Aliases:** T-W5-02, T-W5-05, Q136 · **Prerequisite:** OneMind prototype with 10 apps on the Beelink; restic repos on a USB disk and an append-only rest-server
1. **T-W5-02:** wipe the Beelink → portable restore onto the Dell (x86 → x86) → exact restore onto a re-imaged Beelink; time each step. **Pass:** all apps and data back; RTO ≤ 4 h; the dashboard shows "last verified restore".
2. **T-W5-05:** pull the plug mid-upload (USB and rest-server), then `restic -r <repo> check` and run the next backup. **Pass:** repository consistent; next backup succeeds.
3. **Rev. 4 (DC-11 refuters, REC-DEC-49):** before a backup is reported as verified, check the datastore's health (state.db within its size budget, no kine compaction lag), not only `integrity_check`; read the same repository once with an independent implementation (rustic or Kopia) as a CI-style check. On a `restic check` failure, retry and run a memory test before reporting damage.
- **Fail →** restore design changes before M4; backup engine C3 stays below 5. **Feeds:** DC-11, REC-DEC-11, -28, -49.

### LT-X86-15 · Offline USB update with a wrong clock · **P**
**Aliases:** T-W3-07 · Set the RTC to 2020, install a signed bundle from USB; repeat with 2040 (`sudo date -s 2040-01-01 && sudo hwclock -w`, then reboot).
- **Pass:** installs with signing-time validation; an expiry prompt is shown. **Fail:** refused outright, or installed silently past expiry → fix 04 §8.

### LT-X86-16 · Product checks on x86 (Tier B) · **V**

| ID | Aliases | Test | Pass |
|---|---|---|---|
| LT-X86-16a | T-W9-01 | Deploy a prototype MCP gateway (SDK release that passes the 2026-07-28 conformance) projecting `onemind-mcp`'s 4 tools; connect Claude Desktop with CIMD and a 2025-11-25-only client | Both list the same 4 tools; a token for another resource gets `401`; every call is in the audit stream with a trace ID |
| LT-X86-16b | T-W13-1 | Jellyfin + Immich + Nextcloud with 3 OIDC users, then 3 per-user instances; `ps -o rss` totals | Shared ≤ 1.5× single-user RAM; per-user ≥ 2.5× |
| LT-X86-16c | T-W11-01 | Time first boot → first app installed: umbrelOS VM vs OneMind prototype | OneMind ≤ Umbrel + 2 min; ≤ 6 user steps |
| LT-X86-16d | T-W11-02 | Inject full disk, image-pull failure, OOM, node offline; screenshot household and operator views | No k8s term in the household view; each failure has a plain message and an action |
| LT-X86-16e | T-W11-07 | `sudo systemctl stop k3s`; open `/rescue`; roll back the slot | Rescue page ≤ 3 s; rollback works without k3s |
| LT-X86-16f | T-W12-3 | OSINT ingest at the founder's feed rate into ClickHouse vs a light store on an 8 GB box | < 2 GiB RSS, else the module is Omni-only |

---

## 4. Raspberry Pi 5

**Prerequisite for all:** Pi 5 8 GB (4 GB for LT-PI5-03) + NVMe HAT + SSD + official PSU (11 §10.1). QEMU cannot emulate the Pi 5 firmware, so these are the only proof of the Lite tier.

### LT-PI5-01 · RAUC 1.15.2 + Pi firmware `tryboot` + k3s gate · **G**
**Aliases:** F-PI5, T-W3-02 (NVMe part), critic N8, Q9, Q-P2-4 (partly) · **Kit and full steps:** [`evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`](evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md) (desk pre-flight done in a VM) · **Time:** about 3 hours
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

### LT-PI5-02 · bootc on a real Pi 5 · **G** · **run before gate G1 (week 4)**
**Aliases:** W2-HW-3, DC-01 founder test, REC-DEC-33, REC-DEC-44 · **Prerequisite:** a spare SSD or card; the lab Containerfile rebuilt for aarch64; **Z-39 and Z-40 logged** in `scorecard-weights.md` §8 before the run (`26-…`)
1. Write the **AlmaLinux bootc Raspberry Pi image** (documented as experimental [C-SCORE-025]) or the Fedora IoT 45 raw image; boot; `sudo bootc status`.
2. `sudo bootc switch <registry>/onemind/lab:aarch64` (the lab Containerfile with greenboot + k3s check); reboot; confirm healthy.
3. Push a broken image (k3s fails) and `sudo bootc upgrade && sudo reboot`; touch nothing for 10 minutes.
4. **(STEEL4 conditions)** Pull the power during the staged update's finalize, as in LT-X86-11 H4, and record whether the Pi commit happens automatically after a power pull.
- **Pass:** automatic return to the good image **with no console and no manual commit step**. Record whether greenboot #219 is fixed in the version used [C-STEEL4-bootc-024].
- **Consequence (the pre-registered map, `01` §3.1.6 h, written 2026-11-11):** **Fail** → bootc's Pi 5 cell drops (C·C2 3 → 2) and the S1 result becomes **Debian 13** (Ubuntu 65 · Debian 63 · bootc 60; Debian wins the tie-break 6–5) [C-DEC4-007]; bootc stays the Industrial profile only (REC-DEC-04). **Pass with #219 open or a manual commit step** → no cell or row moves; S1 stays Ubuntu 26.04. **Pass with #219 fixed and an automatic commit** → the DC-19 and lab rows are re-counted for Ubuntu vs bootc: bootc wins 6–4, or a 4–4 draw goes to Zeus under Z-40.

### LT-PI5-03 · Hardened k3s footprint and 30-day soak on 4 GB · **G**
**Aliases:** "T-W4 soak" (DC-10), k3s-footprint-restore T2/T3, W4-1 on silicon, Q125, Q154, Q334, DC-17 (part) · **Prerequisite:** Pi 5 **4 GB** + NVMe; the pinned hardened k3s config (REC-DEC-22; CIS hardening adds audit logging and load [C-REF-W4-security-004])
```sh
# copy evidence/lab/k3s-footprint-restore/scripts/ to /tmp/kfr on the Pi
sudo /tmp/kfr/guest-measure.sh baseline 120
sudo /tmp/kfr/guest-install.sh sqlite start          # with the hardened config in /etc/rancher/k3s/config.yaml
sleep 300; sudo /tmp/kfr/guest-measure.sh idle 120
# Lite variant (T3): add  disable: [traefik, metrics-server, servicelb]  and repeat
# Soak: once a day for 30 days, record
grep MemAvailable /proc/meminfo
awk '$3=="nvme0n1"{printf "%.0f MiB written\n", $10*512/1048576}' /proc/diskstats   # field 10 = sectors written
sudo smartctl -a /dev/nvme0 | grep -E 'Data Units Written|Percentage Used'
```
- **Pass:** idle increase ≤ 1.2 GiB (default) / ≤ 700 MiB (Lite); over 30 days ≥ 2.0 GiB free with the minimum OneMind stack and ≤ 5 GB/day written. VM baseline: 2.50 GiB free, 2.75 GB/day unhardened [C-W4-078].
- **Rev. 4 extension (DC-10 refuters, REC-DEC-49):** pin kine ≥ v0.13.10; run the real minimum stack with the hardened profile; record `state.db` size daily; once, inject a compaction failure and check that the compaction-lag alert fires and the database stops growing after recovery.
- **Fail → consequence:** < 2.0 GiB free or > 5 GB/day → the platform-node floor becomes **8 GB** (REC-DEC-09/22); 4 GB boards become NATS leaves. An unrecovered compaction stall → SQLite is not shipped on that tier until fixed. Also run once on an SD card to show why NVMe is required [C-W4-002].

### LT-PI5-04 · Datastore write volume: SQLite vs embedded etcd (corrected protocol) · **G**
**Aliases:** T-W5-03 (corrected, 01 §4.6 and steelman-etcd-every-box), Q129 · **Prerequisite:** Pi 5 8 GB + NVMe, then an x86 mini PC (Beelink); hardened k3s
1. Fresh install with `--cluster-init` (etcd) on one box; wait ≥ 1 hour (not a conversion). 2. Measure 72 h idle + light load on the **datastore device** (or a dedicated partition) with the `/proc/diskstats` line above, before and after. 3. Repeat with SQLite.
- **Pass (for etcd on servers):** etcd ≤ 2× SQLite **and** ≤ 5 GB/day. **Consequence:** pass → hub/Pro/Omni servers start on embedded etcd (REC-DEC-38); fail → SQLite stays the default everywhere.

### LT-PI5-05 · restic (and Kopia) memory on a 4 GB Pi · **P**
**Aliases:** T-W5-01, Q136 · **Prerequisite:** Pi 5 4 GB + NVMe with k3s + 5 apps; ~200 GB to back up to USB
```sh
/usr/bin/time -v restic -r /mnt/usb/repo backup /data 2> restic-time.txt   # read "Maximum resident set size"
restic -r /mnt/usb/repo check --read-data-subset=1/30
/usr/bin/time -v kopia snapshot create /data 2> kopia-time.txt             # same data, second engine
```
- **Pass:** restic peak RSS < 1 GB, completes, no OOM. **Consequence:** restic over 1 GB or OOM while Kopia stays under → S4 flips to Kopia (steelman: Kopia 75 vs restic 71); otherwise cap repository size on Lite. Known risk: index memory grows with repo size [C-W5-026].

### LT-PI5-06 · Base comparison on the Pi: Ubuntu 26.04 vs Debian trixie + Raspberry Pi kernel · **P**
**Aliases:** W2-HW-1, W2-HW-2 · Each image + k3s: `free -m` after 5 min idle; reboot × 20; power-cut × 10.
- **Pass:** k3s Ready after every boot; used RAM < 1.5 GiB. Record the EEPROM version: Ubuntu 26.04's Pi kernel stalls on EEPROMs older than 2025-02 (LP #2170238, open) [C-DEC-006, C-PLAN180-004]. **Consequence (rev. 4):** a difference is recorded for the G6 base lock; it becomes an S1 tie-break row only through a §8 entry logged before the run (`01` §3.1.6 h).

### LT-PI5-07 · Gate on SD card vs NVMe · **P**
**Aliases:** T-W3-02 (SD part), debian-rugix L-3 · Repeat LT-PI5-01's F-P4 and F-P5 with the target on a microSD card. **Pass:** bad update rolls back within the deadline + 1 boot; record commit time. **Consequence:** sets the per-tier gate deadline; a timeout on SD confirms "no SD for platform nodes".

### LT-PI5-08 · Real-time latency on the Pi 5 · **G** (robot-rt tier)
**Aliases:** LAB-W7-1 (Pi part), DC-14 founder test, Q48 · Run LT-X86-13's commands for **12 hours** with k3s + 10 pods and a memory stressor, stock vs RT kernel (Raspberry Pi publishes RT builds but no 2712 RT build, and states no support for it [C-REF-DC-technical-001]).
- **Pass:** max < 250 µs under load with isolated cores. **Fail:** build a `2712` RT kernel in CI or drop Pi 5 from the robot-rt profile; MCU for loops under ~1 ms either way (REC-DEC-29).

### LT-PI5-09 · ROS 2 in containers on the core leg + k3s · **G**
**Aliases:** LAB-W7-2, DC-15 founder test, Q43, Q75 · **Prerequisite:** Pi 5 and x86; one USB depth camera (RealSense UVC) and one USB-CAN adapter
Talker/listener over Fast DDS shared memory with `hostIPC`; rmw_zenoh with a router pod; ros2_control demo with `SYS_NICE` + SCHED_FIFO; camera and CAN via device plugin. Check SHM is used (no UDP fallback): `ss -u -a | grep -c 7400` stays flat while topics flow.
- **Pass:** all four work; camera at nominal FPS. Run on the leg S1 selects (both legs until the G6 lock). **On the Debian leg: a fail that works on an Ubuntu host → DC-15 flips for that tier.** Robot pods need host network/IPC and `SYS_NICE` [C-W7-033] (REC-DEC-13/36 exception profile).

### LT-PI5-10 · One OS from Pi to x86 to Orin, and cross-arch restore · **G**
**Aliases:** DC-17 founder test ("minimum OneMind stack on a real 4 GB Pi 5" + "one-cluster test"), T-W5-04 · **Prerequisite:** LT-PI5-03, LT-JET-02
1. Join Pi 5, Beelink and Orin into one k3s cluster; install the same Helm set on all three. **Pass:** each node runs it, or the capability check says why not. 2. Back up the Pi 5 box, portable-restore onto x86, and the reverse. **Pass:** apps reinstall with the right-arch images; data intact.
- **Fail →** that app gets a manifest fix or a non-portable flag; a platform failure re-opens F-14 (DC-17).

### LT-PI5-11 · Signed boot image in developer mode (no OTP) · **P**
**Aliases:** P-1 (07 §12), Q208 · Sign `boot.img` with a **test key in unlocked dev mode only. Never write OTP.** Run one A/B update and one rollback with signed images.
- **Pass:** A/B works with signed boot images. **Fail:** raise upstream; consider a U-Boot flow. **Feeds:** DC-18 (Pi), REC-DEC-40 (E10).

### LT-PI5-12 · Plugins across a slot switch on the Pi · **G**
**Aliases:** T-W19-01 (Pi half) · **Prerequisite:** LT-VM-01 passed and LT-PI5-01's disk. Repeat LT-VM-01 on the Pi. **Consequence:** as LT-VM-01.

### LT-PI5-13 · Field and profile tests on the Pi · **P / V**

| ID | Aliases | Test (commands in the source section) | Pass | Feeds |
|---|---|---|---|---|
| LT-PI5-13a | LAB-W8-2 | NATS leaf: `tc qdisc add dev eth0 root netem loss 30%`; 72 h outage; leaf disk full; power cut during write (NVMe) | No loss within stream limits; clear error at the limit; no corruption | 09 P0-5 (VM baseline 600/600) |
| LT-PI5-13b | LAB-W8-1 | `tak-node` acceptance on Pi 5 16 GB and 8 GB: 10 ATAK/iTAK clients on the local AP; Meshtastic-only phone on the map; 24 h uplink cut then reconnect (stream lag 0); update + rollback with TAK healthy as the gate (RAUC, per REC-DEC-05; 09 §8.2 predates this and says Rugix); cold boot to TAK ready < 3 min | All five; RAM headroom ≥ 20% | 09 P0-8, W8-R8 |
| LT-PI5-13c | LAB-W8-8 | `greenhouse` acceptance: kill the Pi 30 min (nodes keep local behaviour, none reboots); hub gets all 30 min of readings; out-of-bounds AI setpoint rejected and logged; rollback with HA healthy; idle RAM on 4 GB < 50% | All five | 09 P0-9 |
| LT-PI5-13d | LAB-W8-6 | HAOS as a VM on Pi 5 8 GB and x86 under k3s with a Thread border router | Matter device commissions; Thread OTA works | W8-R3 |
| LT-PI5-13e | W10-T5, LAB-W8-7, Q304 | Watts at idle and load with the meter: Pi 5, Jetson (7/15/25 W), U55, Dell (lid closed) | Recorded (expected: Pi 5 + NVMe > 2× HA Green's ~1.7 W [C-W10-021]) | 11, Q304 |
| LT-PI5-13f | W10-T3, W10-T6 | NFD v0.20.1 + OneMind probe on Dell, U55, Pi 5; three sample manifests; hot-plug a Zigbee dongle and USB-CAN | Verdicts match a hand-made table; unknown = "?"; superpower → "Sensor gateway" within 60 s | N-3, A-8 |
| LT-PI5-13g | T-W9-02 (Pi), T-W9-03, T-W9-04 | gVisor `runsc` + agent-sandbox; llama.cpp 1B/3B/8B Q4 (tok/s, TTFT, MemAvailable); 10,000 audit decisions | Sandbox starts; Lite ≥ 1 GiB free and ≥ 5 tok/s with 1B; audit < 1 GiB/year, 10k verify < 10 s | Q90, Q91, Q98 |
| LT-PI5-13h | T-W13-4, T-W12-2 | kiwix-serve (Wikipedia mini) + Kolibri (one Khan channel), 5 clients; Pro launch set on Pi 5 8 GB | Pages < 2 s, RAM < 2 GB; all Running, ≥ 1 GiB free, restore drill passes | Q268, 13 |
| LT-PI5-13i | T-W11-08 | QR join: a second Pi scans the box QR; reuse the token after 1 h | First join works; reuse refused | UX |
| LT-PI5-13j | T-W19-05, Q329 | Plug an SO-101 / TurtleBot 4 into a Pi 5 box with no internet, offline `.ompkg` | 29 §11 flow completes; motion blocked until safety settings confirmed | F-3 (needs the robot) |
| LT-PI5-13k | 05 §14 item 2 | Argo CD Core vs Flux on a Pi 5: RSS after 1 h with 10 apps | Record; the lighter one is the on-box GitOps default | DC-10, P-9 |
| LT-PI5-13l | DC-21 founder test | Boot a mainline 6.18.y kernel (K2 route) on the Pi 5 | Boots with NVMe, Ethernet, USB | DC-21, REC-DEC-25 |

### LT-PI5-14 · Kernel × firmware matrix and the overlay check (E10) · **G** *(rev. 4)*
**Aliases:** E10 founder test, REC-DEC-47 · **Prerequisite:** LT-PI5-01's disk; two EEPROM bootloader versions (the pinned one and the newest); two kernels (the shipped one and the next candidate); one HAT or camera that needs an overlay. Why: the Pi 5 EEPROM loads overlays outside the A/B slot, and Home Assistant OS 18 had to revert the Pi 5 over a kernel/EEPROM mismatch (DC-E10 technical refuter, [`evidence/adversarial/DC-E10-technical.md`](evidence/adversarial/DC-E10-technical.md); its sources are not ledgered)
```sh
sudo rpi-eeprom-update                            # record the current bootloader version
vcgencmd bootloader_version
# for each EEPROM x kernel pair: install the RAUC bundle, reboot, then
ls -l /dev/<device-node-the-overlay-should-create>  # e.g. the camera or HAT device
dmesg | grep -iE 'overlay|dtoverlay'
sudo cat /data/onemind/gate.log | tail -3
```
- **Pass:** for every pair, either the overlay's device nodes exist and the gate commits, or they are missing and the gate **refuses** the commit. The EEPROM version is written into the release manifest and checked before an OS update (pin, gate and record). `force_eeprom_read=0` and camera/display auto-detect off stay in effect after each update (01 §4.8).
- **Fail → consequence:** a pair that boots "healthy" without its overlay devices is barred from release, and the gate's device-node check becomes mandatory (REC-DEC-47). **Limit stated by `01`:** on an unfused Pi, E10 is a configuration control, not an integrity control (anyone with the SD card can change it) [C-REF4-DC-security-007, C-REF4-DC-security-008]. The Jetson half (QSPI version pinned and recorded) is step 6 of LT-JET-01.

---

## 5. Jetson Orin Nano Super

**Prerequisite for all:** the dev kit (order by 2026-11-16; dev use only [C-W10-027]); for full flashing an **x86 Ubuntu host** (the Dell booted from USB), because SDK Manager does not support macOS [C-W18-021, C-W18-022]. The USB installer ISO can be written from the Mac [C-W18-023]. NVIDIA's software can end before the hardware does [C-REF-W7-T-001]: record every L4T version.

### LT-JET-01 · NVIDIA A/B with the OneMind gate, OTA and power cuts · **G**
**Aliases:** T-W3-06 (extended, DC-07 Result block), LAB-W7-4, Q6, Q47, Q58 · **Time:** about 1 day
1. Flash JetPack 6.2.x with the **redundant (A/B) rootfs layout** (A/B is set at the factory flash, REC-DEC-18 `ROOTFS_AB=1`). Record `cat /etc/nv_tegra_release` and `sudo nvbootctrl dump-slots-info`.
2. Put the OneMind gate in `l4t-rootfs-validation-config`; install a bad update → **Pass:** gate failure falls back to the good slot.
3. Image-based OTA from JetPack 6.2.x (r36) to JetPack 7.2.x (r39); **cut power during the capsule/OTA update** → **Pass:** OTA resumes or falls back; no reflash. **Rev. 4 (DC-08 refuters):** the same r36 → r39 step must also run **unattended, with no console, with `/data` kept**, and record the QSPI bootloader version before and after. The DC-08 refuter found no documented console-free r36 → r39 path that also moves QSPI on production modules. The claim needs a **production Orin NX module** (not in the Day-1 order); the dev kit run is a rehearsal and is recorded as such.
4. Corrupt slot B → **Pass:** boots A; `nvbootctrl dump-slots-info` shows the expected slot.
5. Extensions from the refuters: **cold power cycle after a hang** (NVIDIA's retry counter ignores cold resets [C-REF3-DC-technical-001]); a root mount failure with the watchdog armed; after OTA, assert the running version equals the bundle's.
6. *(rev. 4, E10)* Record the QSPI firmware version in the release manifest and refuse an OS bundle built for another QSPI version (REC-DEC-47).
- **Fail → consequence:** hook cannot block the commit, or a USB reflash is needed → **DC-07 flip condition**: Jetson SKUs need NVIDIA's recovery process or a CRA period limited to one branch; REC-DEC-35 items become release blockers. **Until step 3's r36 → r39 run passes on a production module, every Jetson SKU declares its support period from its current branch only** (DC-08, REC-DEC-49).

### LT-JET-02 · Jetson baseline: JetPack + k3s + GPU · **G**
**Aliases:** W2-HW-4, W10-T4 · **Prerequisite:** LT-JET-01 step 1
```sh
curl -sfL https://get.k3s.io -o k3s-install.sh; sha256sum k3s-install.sh; less k3s-install.sh   # read before running
# install k3s pinned to the release used in the labs, then the NVIDIA device plugin and GFD:
#   GFD with --device-discovery-strategy=tegra
kubectl get node -o json | grep -E 'nvidia.com/gpu.(product|family|memory)'
kubectl run cuda-test --image=<pinned L4T CUDA sample image> --restart=Never -- ./deviceQuery
```
- **Pass:** a GPU pod runs; L4T version recorded; GFD labels `gpu.product`, `.family`, `.memory` present; the probe sets `memory.unified=true`. **Fail:** the Jetson flavor's k3s story re-opens (DC-09).

### LT-JET-03 · Flashing without an Ubuntu PC · **P**
**Aliases:** T-W18-5, T-W18-6 · (a) Write the JetPack 7.2.1 USB installer ISO on the Mac (Balena Etcher or `dd`), install, record the firmware path. **Pass:** installs without an Ubuntu host. (b) Ubuntu 24.04 arm64 VM on the Mac with USB pass-through (QEMU, not vz) + SDK Manager flashing the kit in recovery mode. **Pass:** flash completes. **Consequence:** whether a separate Linux host is needed at all (28 §9).

### LT-JET-04 · Real-time kernel on Orin · **P**
**Aliases:** LAB-W7-5, LAB-W7-1 (Orin) · Install `nvidia-l4t-rt-kernel*` via OTA packages; repeat LT-X86-13's commands for 12 h with a GPU stressor. **Pass:** boots RT; latency reported as-is (NVIDIA calls it a preview). **Fail to boot:** Jetson not offered for robot-rt.

### LT-JET-05 · Secure Boot without fusing · **P**
**Aliases:** J-1 · Follow NVIDIA's r36.4.4 SecureBoot steps **with `--test` only (no fuses)**; build db-signed kernels for both A/B slots. **Pass:** signed A/B boots without fusing. **Fail:** keep the Jetson flavor unfused until resolved (07 SEC-04).

### LT-JET-06 · meta-tegra + 6.18 LTS kernel (and Canonical's image) · **G**
**Aliases:** LAB-W7-6, DC-09 founder test, REC-DEC-18/35 · **Prerequisite:** a Linux build VM or cloud builder (not hardware-blocked for the build) + the Orin for the run
Build meta-tegra `wrynose` `demo-image-base` + nvidia-container runtime + k3s agent; flash; then CUDA/TensorRT benchmark vs L4T, a CSI camera, NVENC, two 6.18.y bumps, A/B with the gate. Third arm: Canonical's Jetson image (REC-DEC-35).
- **Pass:** builds in < 4 h on cache; CUDA/TensorRT within 10% of L4T; camera and NVENC work; A/B gate works. **Consequence:** pass → meta-tegra becomes the Jetson target (no Canonical dependency for Jetson); fail → L4T Ubuntu stays and Z-01 becomes critical.

### LT-JET-07 · Mender on stock L4T (runner-up E3) · **P**
**Aliases:** Mender steelman E3 · Integrate Mender with stock L4T's A/B (not Yocto). **Pass:** gate-blocked commit and rollback as in LT-JET-01 steps 2–4. **Feeds:** S2 tie-break row DC-09/Jetson.

### LT-JET-08 · gVisor + CUDA on L4T · **V**
**Aliases:** T-W9-02 (Jetson) · Run a `Sandbox` with `runtimeClassName: gvisor`, then `nvidia-smi` or a CUDA sample inside. **Pass:** sandbox starts; record whether CUDA works (Q90).

---

## 6. Mac + disposable VMs + CI (no extra hardware)

These need only the Mac's Lima VMs (the W18 setup: `limactl start --name=onemind-dev --vm-type=vz --nested-virt … template:debian-13`, with `--mount-none` for third-party code). Several **can and should run before the hardware arrives**.

| ID | Aliases | Level | Test and commands | Pass | Fail → consequence | Feeds |
|---|---|---|---|---|---|---|
| **LT-VM-01** | T-W19-01 + security variant | **G** | On the RAUC image (x86 VM): install a verity-signed sysext + confext + driver pack; switch slots with the same `SYSEXT_LEVEL`, then a new level. Security variant: drop an **unsigned image**, a **plain directory** and a **tampered image** into the extension paths on the data partition, reboot and switch slots; `systemd-sysext status`, `systemd-dissect --validate <image>` | Extensions re-merge; a level change refuses old ones with a message the gate reports; nothing written to root; **all three bad extensions refused** after reboot and slot switch | **D3 changes:** extensions only inside the RAUC bundle; no runtime host plugins (systemd's default admits unsigned images [C-REF-W19-security-004]) | DC-16, REC-DEC-24, Z-22 |
| LT-VM-02 | T-W19-02 | P | Two driver-pack sysexts, each with `modules.dep`; `modinfo` modules from both | Expected: only the top pack's modules resolve | Confirms the per-vendor packs + depmod-at-merge rule | E4, REC-DEC-24 |
| **LT-VM-03** | T-W3-04, DC-05 / DC-03 founder test | **G** | Build a major-rebase bundle for the x86 layout of 04 §11 on **both legs** (rev. 4: Debian 13 → 14 testing; Ubuntu 26.04 → the current development series as the closest proxy); install, boot, commit; **log founder-hours** for the whole rebase. **Rev. 4 (DC-05 refuters):** the **old slot's RAUC** must install the new release's bundle, then N+1 and N+2; repeat once with `/data` on an external disk. Then on the Pi 5 and x86 hardware | Fits the 10 GiB slot, boots, commits, data intact; N+1 and N+2 install from the rebased slot; hours recorded | Doesn't fit, needs a bootloader change, or old-slot RAUC cannot read the next bundles (the umbrelOS stranding pattern [C-REF4-DC-longevity-006]) → DC-05 flips; > 4–6 founder-weeks weakens the Debian leg (DC-05's Debian–Ubuntu row is already ≈ in `01` §3.1.6 f) | DC-05, DC-03, REC-DEC-16 |
| **LT-VM-04** | T-W3-03, DC-12 | **G** | (a) **One box (SQLite):** release N (k3s 1.N) → N+1 (k3s 1.N+1) that fails the gate → fallback. (b) **Rev. 4: three-server embedded-etcd cluster:** the same, where rollback across a k3s minor goes only through `k3s etcd-snapshot` restore, never a per-node slot fallback. (c) Rev. 4 (REC-DEC-45): an app that migrates its data during the trial must hold the migration until commit; turn on RAUC `prevent-late-fallback` and a version floor and check that a committed release cannot fall back to the old slot; starve a core pod for 300 s and check that the gate reports "environment bad" (bounded re-offer plus an alert), not "image bad" for good | (a) Old slot's k3s starts on the untouched datastore; workloads intact. (b) Snapshot restore brings all three servers back on 1.N, objects counted. (c) No migrated app data after a rollback; no post-commit fallback; the starved release is re-offered | k3s refuses to start or datastore corrupt → DC-12 flip; REC-DEC-28 restore drill. (b) fails → multi-server boxes cannot take a k3s minor inside an A/B release until fixed | DC-12, REC-DEC-45 |
| **LT-VM-05** | Mender F3 | **G** | In a copy of grub-mender-grubenv, allow `bootcount` 0–3 and roll back only at 3; rebuild; `python3 -I run-tests.py` with T6/T7 expecting 3 attempts | T9 commits B v2 on the retry; all else passes | Pass → Mender meets 01 §4.2 item 3 and RAUC loses its "boot tries" tie-break row | S2, REC-DEC-26, Z-03 |
| LT-VM-06 | Mender F4 | P | mender-convert 5.3.0 (`generic_x86-64_hdd_config`, Docker in Lima) on the same rootfs; embed the gate; rerun T1–T8 | Same results as the hand-built lab | The supported path differs → note in 04 | S2 |
| LT-VM-07 | F-U1, F-U2 | P | Debian build with `-t trixie-backports linux-image-amd64` + Debian RAUC 1.13, `--upto T3`; Ubuntu leg with dracut instead of initramfs-tools | F-U1 **expected to fail** with `Unexpected dm-verity status 'V -'` [C-LAB-ubuntu-2604-leg-004]; F-U2 same verdicts | F-U1 passing means that claim is wrong | REC-DEC-31 |
| LT-VM-08 | ubuntu-2604-leg 1.15.2 row; critic N8; DC20-R6; aarch64-gate A3 | P | **Rev. 4: the aarch64 UEFI RAUC + k3s-gate run is done** (PASS, two runs [C-LAB-aarch64-gate-004], §1.1). Remaining: RAUC 1.15.2 on the Ubuntu leg (`RAUC_MODE=src`); the aarch64 leg of the minimal-image scripts; the aarch64 suite as a CI job on bare-metal KVM or HVF (`LAB_ACCEL=kvm`), never nested virtualisation [C-LAB-aarch64-gate-006] | Same verdicts as x86 | Fix before LT-PI5-01 | REC-DEC-05, -31, DC-20 |
| LT-VM-09 | T-W18-1, T-W18-2 | P | `sysctl -n machdep.cpu.brand_string; sw_vers -productVersion`; in Lima `ls /dev/kvm`; full core image rebuild (amd64 + Pi) in Lima and CI, timed | M3+ and macOS 15+ → `/dev/kvm`; < 30 min each | Builds only in CI; K1-C5 stays 4 | 28 §9 |
| **LT-VM-10** | T-W18-4 | **G** | "HAOS route" dry run: weekly 6.18.y bump + boot test for 4 weeks; record hours per bump | < 1 h per bump | ≥ 1 h → the K2 kernel cost estimate (REC-DEC-25) rises; re-plan Secure Boot release | DC-21, S5 |
| LT-VM-11 | T-W3-05 | P | Delta update over `tc qdisc add dev eth0 root netem rate 64kbit loss 10%` | Completes or resumes; size and time recorded | Hangs without timeout → fix 04 Q5 | 04 |
| LT-VM-12 | k3s-footprint-restore T1, T4, T5, T6 | P | `scripts/run-all.sh` end to end; naive `cp -a` SQLite copy while running; restore under a different node name; x86_64 | `IDENTICAL` and 32/32 pods; T4 tells if `.backup` is required; **T5 expected to fail** for local-path pods | Confirms REC-K3S-2/3 (token and stable node name in the recovery kit) [C-LAB-k3s-footprint-restore-013] | DC-11 |
| LT-VM-13 | DC-20 re-run (`minimal-image-dc20` §7.13) | P | The §7.13 command block on any Debian 13 VM. **Rev. 4 (DC-20 refuters, REC-DEC-46):** re-measure with a **compiled-source kernel filter** (count only CVEs in code the kernel config actually builds), on **both legs**, with a **second scanner**, and a VEX pass for triaged IDs | Same as its §3; filtered counts recorded per leg and scanner | DC-20 is no longer decided on CVE counts: D1 stands on the NVIDIA/CUDA path and one-developer maintainability. A filtered gap ≥ 50% is recorded and re-read by the DEC owner, not an automatic flip | DC-20 |
| **LT-VM-14** | T-W15-01, W15-N4 | **G** | Air-gapped rebuild: unplug the build VM's network; build from the local forge mirror, Debian snapshot and local registry; sign with the offline key; install from USB; compare SBOM | Builds, boots, passes the k3s gate; package list = online build's | Any step needs the internet → **release blocker** for the first sold image | REC-W15-11 |
| **LT-VM-15** | LAB-W8-3 | **G** | Sparkplug TCK against the NATS MQTT listener and Mosquitto | TCK "compliant" (and NATS "aware") profiles pass | NATS cannot be the Sparkplug broker → Mosquitto in the IIoT profile | 09 P0-4, DC-02 |
| **LT-VM-16** | LAB-W8-4, Z-27 | **G** | go-fdo client: DI → TO0/1/2 against a self-hosted owner, on the core legs **and** EL10 bootc (VMs first, then the Dell's TPM and a Pi 5 without TPM). Rev. 4: go-fdo has no release and no FIDO interop yet [C-REF4-DC-longevity-005], so also run the **day-one fallback**: IDevID plus a manual claim | Enrols and receives NATS creds and a WireGuard key with no keyboard; the fallback enrols with one owner action | Zero-touch onboarding blocked on the core legs → DC-02 (F-11) re-opens; EL10 steelman gains. FDO stays "experimental" either way (REC-DEC-49) | DC-02, REC-DEC-27, -49 |
| **LT-VM-17** | LAB-W8-5, Flight Control simulation (Z-27) | **G** | 100 simulated sites (k3s + NATS leaf + update agent in VMs) against one hub; staged OTA wave with 5% injected failures; then Flight Control's `devicesimulator` at 1k+ | Hub CPU/RAM linear; wave completes with gate-driven rollback | Fleet scale fails → DC-02 G4(e) re-opens | DC-02 |
| LT-VM-18 | S-1, S-2 = T-W9-05, T-W19-04 | G (AI actuation) | Market app with `hostNetwork`, privileged and a hostPath in `market-*` (PSA Restricted); planted email asks the agent to install an OS update, actuate a simulated valve and read Strava; revoke an installed adapter while a sim robot moves | Rejected with a clear error; gateway blocks until phone approval, Strava not listed; robot reaches safe state within its stop time, plugin disabled, audited | **Block release of AI actuation** and any `actuate` plugin | REC-DEC-13, -40, AI-5 |
| **LT-VM-20** *(rev. 4; FIX5: kit ready, research attempt BLOCKED)* | Ubuntu Secure Boot leg (`01` §10 "not proven"; S1 variant V3; U-SB in `01` §3.1.6 h) | **G**, **week 1**, no hardware: about 1.5–2 h unattended on any machine that reaches `archive.ubuntu.com` | Run the pre-registered kit in [`evidence/lab/ubuntu-secureboot/`](evidence/lab/ubuntu-secureboot/) (README §R.3 has the commands; criteria frozen at 2026-11-11T15:51Z, sha256 `c98a09d1…f8db`) [C-FIX5-002, C-FIX5-003]. It does this: build the `secureboot-1152` kit (RAUC 1.15.2, `efi` backend, signed per-slot UKIs with `rauc.slot=` on the command line, verity-only) from the **Ubuntu 26.04** leg (`ubuntu-2604-leg`), and run the same suite T0–T9 + E1 in OVMF + swtpm | Same verdicts as the Debian run [C-LAB-secureboot-1152-005]; the downgrade gap E1 recorded as it is | Any difference → a rule-6 re-score request for D·C3 goes to the DEC owner (variant V3 in `01` §3.1.6 g: bootc 6–5). Pass → D·C3's `doc-only` mark can be dropped | S1, DC-18, REC-DEC-08 |
| LT-VM-19 | T-W12-1, T-W12-4, T-W11-05 | V | Import the top 50 CasaOS apps with `onemind app import` (disposable VM); licence linter vs the 70 hand-classified seed repos; axe-core on OneMind/Umbrel/HA/Olares screens | ≥ 80% reach Listed; 100% class match; 0 serious/critical violations | Importer "assistive"; fix linter before public listing | 13, 12 |

---

## 7. Cloud or local NVIDIA RTX GPU

No founder GPU exists today (11 §10); rent an Ampere-or-newer x86 instance by the hour, using an image you build, with no founder credentials on it. **Rev. 4:** run LT-GPU-01/02 on the core leg S1 selects. Under the decision of record (Ubuntu 26.04) the GPU-server flavor is already Ubuntu LTS (`01` §1), so the Debian runs below decide the GPU tier only if the base lock gives Debian.

### LT-GPU-01 · NVIDIA on Debian 13 + k3s, and surviving upgrades · **G**
**Aliases:** LAB-W7-3, DC-13 "Pro-box GPU lab", 05 §14 item 5, Q16 · **Time:** half a day
1. Driver from NVIDIA's `debian13` repository + NVIDIA container toolkit + device plugin on k3s; run a CUDA sample pod and one Isaac ROS dev-container sample.
2. Enable time-slicing; run two GPU pods.
3. Upgrade the driver one minor; then apply a Debian **point-release kernel** update; reboot; re-run step 1 (NVIDIA's DKMS module has broken on routine Debian kernels before [C-REF-DC-cost-009]).
4. With Secure Boot on (if the instance allows): sign the module in the image pipeline and load it.
- **Pass:** all steps pass with GPU acceleration, with no manual rebuild. **Fail on Debian, pass on Ubuntu 24.04 → Pro/Omni GPU tier gets the Ubuntu flavor** (REC-DEC-19); > 1 release-blocking module failure in 6 months triggers REC-DEC-37.

### LT-GPU-02 · Isaac Sim headless on Debian · **G**
**Aliases:** Z-17, REC-DEC-19 · Isaac Sim headless container on the LT-GPU-01 host; run one sample scene. **Pass:** runs on Debian. **Fail (expected, NVIDIA lists Ubuntu and Windows hosts [C-REF-DC-robotics-013]):** robotics-simulation boxes use the Ubuntu GPU flavor.

### LT-GPU-03 · Local AI tier table on RTX · **V**
**Aliases:** T-W9-03 (RTX) · llama.cpp/Ollama/vLLM with 8B–70B models; tokens/s, TTFT, VRAM. **Pass:** recorded into 11's tier table.

---

## 8. Phones, tablets, XR headsets and desktop clients

### 8.1 GrapheneOS + ATAK (the full test from `15-…` Appendix A)
**Owner:** Zeus · **Time:** about 3 h on one phone + 1 h per extra device · **Hardware:** a Pixel 8 or later (9a/10a preferred), the Pixel Tablet if available, the S24 Ultra as a stock control, a laptop with `adb`, optionally a Meshtastic radio and a Bluetooth GPS · **Prerequisite:** the Pixel must be carrier-unlocked ("OEM unlocking" available) · **Decision:** LT-EUD-01…05 pass on the Pixel phone → GrapheneOS becomes the OneMind-recommended EUD (REC-W14-01); any unexplained fail → stock Pixel/Samsung for ATAK, GrapheneOS for non-TAK users. Background: no public ATAK-on-Pixel-Tablet crash trace exists; five hypotheses H1–H5 (15 §4).

**LT-EUD-00 · Inventory and install** (A.0, A.1, Q290 phone rows)
```sh
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.build.fingerprint            # grapheneos/… or google/…
adb shell pm list packages | grep -i atak
adb shell dumpsys package com.atakmap.app.civ | grep -E "versionName|primaryCpuAbi"
```
Install GrapheneOS with the official web installer; **relock the bootloader**; check the boot-key fingerprint against the install page; install ATAK-CIV from the source you will use in the field (record which). **Pass:** locked bootloader; ATAK reaches the map.

| ID | Aliases | Steps | Pass | Fail → |
|---|---|---|---|---|
| LT-EUD-01 | T-W14-01 | Owner profile, no Play; location "Allow all the time"; battery "Unrestricted"; outdoors | Self position < 2 min; 60 min in background, screen off, track keeps updating | H3 or battery policy; document settings |
| LT-EUD-02 | T-W14-02 | (a) network location indoors; (b) location off at launch, then on; (c) Tablet: no GPS, then Bluetooth GPS via a mock-location app | No crash; (a) indoor fix; (c) "no GPS" hint, then a position | H3 confirmed |
| LT-EUD-03 | T-W14-03 | 30 min of normal use (imagery, offline maps, every tool, video). On a "memory corruption detected" notice: save it, take a bug report (keep local), enable **Exploit protection compatibility mode** for ATAK [C-W14-005], repeat | No crash, or the crash disappears with compatibility mode (H1 confirmed → documented exception, report upstream privately) | Persists → LT-EUD-04/05 |
| LT-EUD-04 | T-W14-04 | Enable "Notify about system process crashes"; ATAK in Owner then a second profile, switch 3×; start voice/video; `adb logcat -b crash -d > atak-crash-buffer.txt` (**keep local, never commit**) | No system_server or audio HAL crash | H2/H5 (GrapheneOS #6727 [C-W14-013]); Pixel Tablet stays off the EUD list |
| LT-EUD-05 | T-W14-05 | Remove all plugins, 15 min; add back one at a time, 10 min each | No crash | Last plugin added is the cause; record its target ATAK version |
| LT-EUD-06 | T-W14-06 | GrapheneOS phone + S24U: (1) mesh SA multicast, no VPN; (2) Tailscale on the GrapheneOS phone; (3) both to TAK Server over TLS 8089; (4) Meshtastic plugin PLI + chat, then change hop limit | (1) and (3) both ways < 60 s; (2) documented (expected to fail [C-W14-010]); (4) documented | Keep "prefer TAK Server when a VPN is on" |
| LT-EUD-07 | T-W14-07 | Second profile with sandboxed Google Play; repeat LT-EUD-01 and LT-EUD-06 step 3 | Same as without Play; list Play-only plugins | — |
| LT-EUD-08 | A.2 (S24U control) | `adb shell getprop ro.boot.warranty_bit`; `… ro.boot.flash.locked`; `… sys.oem_unlock_allowed` | Values recorded. **Never attempt an unlock** [C-W14-021] | — |

### 8.2 Children's devices, desktop clients and XR

| ID | Aliases | Device | Test | Pass | Feeds |
|---|---|---|---|---|---|
| LT-EUD-09 | T-W13-2, W13-N2 | Android tablet (factory reset) | Provision Headwind MDM as device owner by QR; kiosk + DNS policy | Works without Google EMM registration; child cannot remove the policy without a reset | Go/no-go for the L4 "kids' tablet" |
| LT-EUD-10 | T-W13-3 | Child's phone (unmanaged) | Encrypted DNS with a per-child ClientID, at home and over the tailnet; try to bypass (remove profile, change DNS, other VPN) | Filtering on both paths; bypasses recorded | L2 wording in the UI |
| LT-EUD-11 | T-W11-03 | iPhone | Push relay sends only `{opaque_id}`; the extension fetches over LAN and over Tailscale | Full alert ≤ 5 s; relay log holds no content | D-005, UX-4 |
| LT-EUD-12 | T-W11-04, Q322 | Windows 11 PC + Mac | Tauri app discovers the box; SMB and Time Machine to a `vfs_fruit` share | Discovery ≤ 10 s on both; a Time Machine backup completes | UX-8 |
| LT-EUD-13 | T-W11-06, Q283 | Galaxy XR or Quest | Dashboard over local-CA HTTPS and Tailscale HTTPS; a WebXR sample | 2D panel works; immersive session only over HTTPS | UX-9 |
| LT-EUD-14 | T-W13-5 | Any browser | "Open in OneMind": static page → box redirect → consent screen; watch the network log | No box address leaves the browser; a Child account gets "ask a parent" | W-8 |

---

## 9. Live cluster: read-only checks

**What this is.** The founder runs one managed Kubernetes cluster on DigitalOcean (DOKS) with Argo CD, NATS JetStream, Backstage, Hermes agents, an internal MCP server, TAK Server, Authentik, Tailscale, CloudNativePG, VolSync, Velero, Kyverno and Falco (`context/01` §2–§3, reported state). This research had no access to it, so every `blocked: live-cluster` item becomes a check below. **No hostnames, IPs or account IDs appear here or may be committed.**

### 9.1 Rules (read before running anything)

1. **Only `get`, `describe` and `list` verbs** (`kubectl get|describe`, `doctl … get|list`, `argocd app list|get`). Never `apply`, `edit`, `patch`, `delete`, `scale`, `rollout`, `exec`, `port-forward`, `cordon`, `drain`, `sync`, `create` or `helm upgrade`.
2. **Never pass `--refresh` or `--hard-refresh` to `argocd app get`**: they make Argo CD re-read Git and refresh its cache [C-LABPLAN-008].
3. **Never print Secret data.** `kubectl get secrets` without `-o yaml/json` shows names only; never use `-o yaml`, `-o json` or `describe` on Secrets or SealedSecrets.
4. **Hide addresses.** `doctl kubernetes cluster get` shows the API server's public IPv4 by default [C-LABPLAN-006], so always pass `--format`. For Services use custom columns that leave out IPs [C-LABPLAN-009].
5. **Check the context first**, every session: `kubectl config get-contexts` and confirm the `*` is on the intended cluster. Use `--context <ctx>` on every command.
6. **Record summaries, not output:** counts, versions, yes/no. Raw output stays on the founder's machine.

### 9.2 The checks

`<ctx>` = your kubeconfig context name; `<cluster>` = your cluster's name. Both stay off the repo.

**LT-CLU-01 · Cluster shape** · Feeds: Q155, P-9, 05 §9 · Level P
```sh
doctl kubernetes cluster list --format Name,Region,Version,Status          # [C-LABPLAN-007]
doctl kubernetes cluster get <cluster> --format Name,Version,AutoUpgrade,HAControlPlane,Status,NodePools,NvidiaGpuDevicePlugin
kubectl --context <ctx> get nodes -o custom-columns=CPU:.status.capacity.cpu,MEM:.status.capacity.memory,KUBELET:.status.nodeInfo.kubeletVersion,ARCH:.status.nodeInfo.architecture
kubectl --context <ctx> get ns --no-headers | wc -l
kubectl --context <ctx> get pods -A --no-headers | wc -l
```
Pass: matches `context/01` §2 (version 1.36.x, HA control plane, 3 + 1 nodes, ~250 pods, 43–49 namespaces). Record differences.

**LT-CLU-02 · Storage lock-in** · Feeds: Q140, P-9, conversion phase 0 · Level G (for the conversion plan)
```sh
kubectl --context <ctx> get storageclass
kubectl --context <ctx> get pv -o custom-columns=CLASS:.spec.storageClassName,SIZE:.spec.capacity.storage,RECLAIM:.spec.persistentVolumeReclaimPolicy --no-headers | sort | uniq -c
kubectl --context <ctx> get volumesnapshotclass
kubectl --context <ctx> get pvc -A -o custom-columns=NS:.metadata.namespace,CLASS:.spec.storageClassName --no-headers | awk '$2=="<none>"'   # claims with no explicit class
```
Pass: ~95 PVs, ~1.2 TiB, a retain and a delete class [C-W4-063]. Any stateful claim on the delete class → flag for owner review (do not change it here).

**LT-CLU-03 · Public exposure and ingress-nginx** · Feeds: Q140, 05 §9.2 phase 0 · Level G
```sh
kubectl --context <ctx> get svc -A --field-selector spec.type=LoadBalancer -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,LBCLASS:.spec.loadBalancerClass
kubectl --context <ctx> get ingress -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,CLASS:.spec.ingressClassName
kubectl --context <ctx> get ingressclass
kubectl --context <ctx> get gatewayclass,gateway -A
kubectl --context <ctx> get pods -A -l app.kubernetes.io/name=ingress-nginx -o custom-columns=NS:.metadata.namespace,IMAGE:.spec.containers[*].image
```
Pass: record how many public ingresses still use the `nginx` class and the controller image version. **Any public ingress-nginx is a phase-0 item** (it is unmaintained [C-W4-016]).

**LT-CLU-04 · GitOps ownership (Argo vs hand-installed Helm)** · Feeds: Q140 dependency list, 05 §9.2 · Level P
```sh
argocd app list                                  # [C-LABPLAN-008]; count apps; note OutOfSync / Degraded
argocd app get <app-of-apps-root>                # read-only; NO --refresh
kubectl --context <ctx> get applications.argoproj.io -A --no-headers | wc -l
kubectl --context <ctx> get secrets -A -l owner=helm -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name   # names only; Helm 3 release records [label UNVERIFIED here]
```
Pass: the Helm releases not adopted by Argo are exactly the ones `context/01` lists (NATS, TAK Server core, Argo CD itself). Any other one is a new conversion item.

**LT-CLU-05 · Backups as deployed** · Feeds: T-W5-06, Q136, 06 · Level P
```sh
kubectl --context <ctx> get replicationsources.volsync.backube -A --no-headers | wc -l
kubectl --context <ctx> get replicationsources.volsync.backube -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,LAST:.status.lastSyncTime
kubectl --context <ctx> get backups.velero.io -A --sort-by=.metadata.creationTimestamp | tail -5
kubectl --context <ctx> get backups.postgresql.cnpg.io,scheduledbackups.postgresql.cnpg.io -A
kubectl --context <ctx> get cronjobs -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,SCHEDULE:.spec.schedule,LAST:.status.lastSuccessfulTime | grep -i backup
```
Pass: matches `context/01` §10 (46 VolSync sources, recent successful runs, CNPG continuous backup). Record any source with no sync in the last 48 h.

**LT-CLU-06 · Security baseline today** · Feeds: Q220, 07 · Level P
```sh
kubectl --context <ctx> get ns -L pod-security.kubernetes.io/enforce,pod-security.kubernetes.io/audit,pod-security.kubernetes.io/warn   # [C-LABPLAN-010]
kubectl --context <ctx> get networkpolicies -A --no-headers | wc -l
kubectl --context <ctx> get ciliumnetworkpolicies,ciliumclusterwidenetworkpolicies -A --no-headers | wc -l
kubectl --context <ctx> get clusterpolicies.kyverno.io
kubectl --context <ctx> describe clusterpolicies.kyverno.io | grep -iE '^Name:|failureAction|validationFailureAction|verifyImages'
kubectl --context <ctx> get pods -A -l app.kubernetes.io/name=falco --no-headers | wc -l
kubectl --context <ctx> get pods -A -o custom-columns=NS:.metadata.namespace,PRIV:.spec.containers[*].securityContext.privileged,HOSTNET:.spec.hostNetwork --no-headers | grep -c true
```
Record: namespaces with no PSA label; namespaces with no NetworkPolicy; Kyverno policies in Audit vs Enforce; whether any image-verification policy exists; count of privileged or host-network pods. **Not visible read-only** (managed control plane): secrets encryption at rest and API audit logging. Mark them "provider-managed, not verified" rather than guessing. Pass = a filled gap table for 07's baseline.

**LT-CLU-07 · AI layer inventory** · Feeds: Q120, AI-9, 10 · Level P
```sh
kubectl --context <ctx> get deploy,sts -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image | grep -iE 'hermes|mcp|litellm|ollama|agent'
kubectl --context <ctx> get pods -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,LAST:.status.containerStatuses[*].lastState.terminated.reason | grep -iE 'oom|error'
kubectl --context <ctx> get nodes -o custom-columns=ARCH:.status.nodeInfo.architecture --no-headers | sort | uniq -c
```
Record: which agent components run, their image tags, whether each image is published for **arm64** (needed before the first ARM box, 05 §11), and recent OOM/error restarts.

**LT-CLU-08 · NATS bus contract** · Feeds: AI-9, Q80, 09 · Level P
```sh
kubectl --context <ctx> get streams.jetstream.nats.io -A --no-headers | wc -l
kubectl --context <ctx> get keyvalues.jetstream.nats.io -A --no-headers | wc -l
kubectl --context <ctx> get streams.jetstream.nats.io -A -o custom-columns=NAME:.spec.name,SUBJECTS:.spec.subjects,REPLICAS:.spec.replicas,STORAGE:.spec.storage
```
Pass: ~38–39 CRs, R3 file storage (`context/01` §3). Record any subject outside the locked grammar (`context/01` §5): it must be fixed before the grammar becomes the OS bus contract.

**LT-CLU-09 · Fleet-ops readiness for robots** · Feeds: Q80 · Level V
```sh
kubectl --context <ctx> get applicationsets.argoproj.io -A
kubectl --context <ctx> get applications.argoproj.io -A -o custom-columns=NAME:.metadata.name,DEST:.spec.destination.name --no-headers | awk '{print $2}' | sort | uniq -c
```
Record how many destination clusters Argo CD manages (expected: only itself). Q80's answer: one cluster today; fleet GitOps to offline robots is new work (05 §9, 08 §11.3).

**LT-CLU-10 · Live feed sources and licences** · Feeds: T-W12-5, W12-N3 · Level V
```sh
kubectl --context <ctx> get deploy,cronjob -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name --no-headers | grep -iE 'feed|adsb|ais|aircraft|ship|hazard|fire|conflict'
```
Then, by hand, list each feed's data source and its terms. Pass: every feed has a recorded licence; non-commercial feeds are disabled or relicensed before any sale.

**LT-CLU-11 · Cost** · Feeds: Q155 · Level P · In the cluster's cost dashboard (OpenCost, tailnet-only) and the provider's billing page, record the monthly total and the top five namespaces by cost. Console reads only. Pass: a number exists for 05 §9's "cost within budget" exit test.

**LT-CLU-12 · Infrastructure-map export** · Feeds: Q271, UX-7 · Level V · The counts from LT-CLU-01, -04 and -09 plus `kubectl --context <ctx> get nodes,ns --no-headers | wc -l` are the input for the Nodes-app prototype. Pass: one anonymised JSON of counts exists for the dashboard team.

---

## 10. Founder actions that are not lab tests

Listed so nothing named elsewhere is lost. They have no hardware pass/fail.

| ID | Aliases | Action | Done when | Feeds |
|---|---|---|---|---|
| **LT-BIZ-01** | T-W16-4, Z-01, O-1 | Send the Canonical, NVIDIA, Raspberry Pi and MHS questions (drafts in `evidence/outreach-drafts.md`, `outreach-drafts-W16.md`); get counsel's view on modified-Ubuntu redistribution; ask Canonical for a **written price** (REC-DEC-43) | Written answers recorded as claims | **S1** (rev. 4: Z-01 is the condition on the decision of record; the map in `01` §3.1.6 h gives Ubuntu outright if granted with a price, bootc if refused and a debranded rebuild is rejected), RR-09's cost, Jetson flavor, DC-03 |
| LT-BIZ-02 | T-W16-1 | Trademark clearance for "OneMind"/"OneMind OS" (classes 9, 42) by an attorney | Written opinion | 17 |
| LT-BIZ-03 | T-W16-2 | Incorporate; landing page; NVIDIA Inception | Inception acceptance | 11 §10.1 |
| LT-BIZ-04 | T-W16-3, T-W16-5 | 30 discovery interviews; then a pre-order test | ≥ 30% would pre-order; > 100 paid pre-orders | 17 |
| LT-BIZ-05 | T-W18-3 | For 6 months, log each Debian `linux` DSA date, and (rev. 4, both legs) each Ubuntu `linux` USN date, vs the upstream stable release with the same fix | Median ≤ 7 days; no "high" CVE > 14 days, per leg | S5 trigger 2 (K1 → K2) |

---

## 11. What competitors do

How the proven products test their OS images, and whether that fits a solo founder.

| Product | How it tests images | Real hardware in the loop? | Constraints | Constraint fit for OneMind |
|---|---|---|---|---|
| **Home Assistant OS** | pytest + labgrid 26.0.1 boot the x86 image in QEMU/OVMF with `-snapshot` [C-LABPLAN-001]; smoke tests include an OS update and booting the other slot, in GitHub Actions on every change [C-LABPLAN-002] | Not in the public CI found here | Large community team; Buildroot + RAUC; Docker, no k3s | **High** for the CI pattern: the same RAUC A/B checks in QEMU on every PR. OneMind's lab already does this by hand; make it CI (REC-LABPLAN-02) |
| **umbrelOS** | 116 VM test files; Pi tests boot the production Pi image in an **emulated Raspberry Pi 4** (TCG only, slow, run on main branches or labelled PRs), including release-signing and OS-update tests [C-LABPLAN-003] | Not in the public CI found here | Small team; Debian + Rugix; Docker | **High:** closest constraints (Debian, Pi, small team). Note even Umbrel emulates a Pi 4, because no Pi 5 machine exists in QEMU; that is why LT-PI5-01 must be on real hardware |
| **balenaOS** | Same suites on QEMU aarch64/amd64 per PR, then **on the physical device type before release** [C-LABPLAN-004], using AutoKit rigs that switch SD cards, cut power, capture video and serial [C-LABPLAN-005] | **Yes**, automated rigs in several locations | Funded company, ~100 device types, Yocto | **Medium:** the right end state, too heavy for year 1. Borrow the idea of a **scripted power switch + serial console** for PP-10 (REC-LABPLAN-03) |
| **Olares** | Per-module build and test workflows; no installed-system boot or update test visible from workflow names [C-LABPLAN-011, partial] | Not found | Installer on a stock distro; k3s; no OS A/B | **Low:** no OS image to test, which is exactly what OneMind adds |
| **RAUC's maintainers (Pengutronix)** | Maintain **labgrid**, the hardware-in-the-loop library HAOS uses, and fund RAUC/labgrid through consulting and sponsorship [C-REF-W3-longevity-006] | Yes (the tool's purpose) | Consultancy | **High** as a tool: labgrid can drive both the QEMU tests and, later, a power relay on real boards |

**Lesson:** every serious competitor tests updates **automatically in QEMU on every change**, and the one with the most hardware (balena) also runs the same tests on physical boards before release. Nobody can skip real hardware for the Pi boot firmware or power loss. OneMind should do the QEMU part in CI now and the physical part by hand (this file) until volume justifies a rig.

---

## 12. Recommendations

| ID | Recommendation | Requirement IDs |
|---|---|---|
| **REC-LABPLAN-01** | Run §1's critical path in its order; `20-PLAN-180-DAYS.md` makes LT-X86-01/02, LT-PI5-01, LT-X86-03/04 and LT-VM-01 the **week-4 to week-6 update-engine gate**, and (rev. 4) LT-PI5-02 the S1 check **before G1 (week 4)**, read against `01` §3.1.6 (h) | R-1, R-3, M-6, F-14 |
| **REC-LABPLAN-02** | Turn every passed emulated lab (rauc-1152, secureboot-rauc, mender, ubuntu-2604-leg, k3s-footprint-restore, w19-sysext) into a **CI job** on every image change, the HAOS/umbrelOS pattern [C-LABPLAN-001…003] | R-1, M-6, P-4, RS-4 |
| **REC-LABPLAN-03** | By month 3, build a minimal **power-pull rig** (switched outlet + USB serial console, scripted with labgrid) so PP-10 runs unattended on x86 and Pi 5; balena's AutoKit is the reference [C-LABPLAN-005] | R-1, R-2, H-3, M-6 |
| **REC-LABPLAN-04** | Record every result with the §2.5 template in `evidence/lab/founder-hardware/`, under the redaction rules; each result becomes a claim row | RS-6, M-6 |
| **REC-LABPLAN-05** | Run the §9 live-cluster checks in week 1 (about 1 hour); they feed the DOKS conversion plan (05 §9), the Hermes/NATS migration and the security baseline | P-9, AI-9, M-2 |
| **REC-LABPLAN-07** *(rev. 4)* | From the two new labs (§1.1): set every gate deadline from measured good-commit times with ≥ 3× margin and log wall-clock time per check; run timing-sensitive gate jobs only on bare-metal KVM/HVF or real arm64 runners; put `rauc.slot=<bootname>` inside every signed UKI command line; keep the Secure Boot anti-downgrade fixes as release blockers, because RAUC 1.15.2 does not close the gap [C-LAB-aarch64-gate-006, C-LAB-secureboot-1152-008, C-LAB-secureboot-1152-009] | R-1, R-2, R-3, M-2, M-6 |
| **REC-LABPLAN-06** | Buy the Pi 5 8 GB (+ a 4 GB for LT-PI5-03), NVMe kit, Jetson Orin Nano Super, a spare USB SSD and a power meter by 2026-11-16 | D-004, D-006, H-3, N-2 |

---

## 13. Alias index

| Old ID(s) | New ID | Source file |
|---|---|---|
| W10-T1, X-1, X-3, W2-HW-5, Q290 | LT-X86-00 | 11 §11, 07 §12, 03 §13 |
| rauc-k3s-gate F1, rauc F1, T-W3-01 (RAUC) | LT-X86-01 | `lab/rauc-k3s-gate`, `lab/rauc`, 04 §15 |
| rauc-k3s-gate F2/F2b, rauc F2/F2b, T-W3-01, Q58 | LT-X86-02 | same |
| F-SB-1, X-2, W10-T2 | LT-X86-03 | `lab/secureboot-rauc` §11, 07, 11 |
| F-SB-3 | LT-X86-04 | `lab/secureboot-rauc` |
| F-SB-2 | LT-X86-05 | `lab/secureboot-rauc` |
| SB-5b | LT-X86-06 | 01 §4.3, decision-critical DC-18 |
| ODM db/KEK update test | LT-X86-07 | 01 §4.3, REC-DEC-36 |
| mender F1, F2 | LT-X86-08 | `lab/mender` §8 |
| debian-rugix "on real hardware", T-W3-01 (Rugix) | LT-X86-09 | `lab/debian-rugix` §6 |
| ubuntu-2604-leg hardware row | LT-X86-10 | `lab/ubuntu-2604-leg` §10 |
| fedora-bootc H1–H5 | LT-X86-11 | `lab/fedora-bootc` |
| T-W19-03 (arm 1: shim `vendor_cert`, REC-DEC-48; arm 2: K2-hybrid) | LT-X86-12 | 29 §16, 01 §5.9.2 |
| T-W18-7, LAB-W7-1 (x86) | LT-X86-13 | 28 §9.4, 08 §10 |
| T-W5-02, T-W5-05 | LT-X86-14 | 06 §14 |
| T-W3-07 | LT-X86-15 | 04 §15 |
| T-W9-01, T-W13-1, T-W11-01/02/07, T-W12-3 | LT-X86-16a–f | 10, 14, 12, 13 |
| F-PI5 (F-P1…F-P11c), T-W3-02 (NVMe) | LT-PI5-01 | `lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md` |
| W2-HW-3 | LT-PI5-02 | 03 §13, 01 §3.1.6 (h) (rev. 4: before G1) |
| T-W4 soak, k3s-footprint-restore T2/T3 | LT-PI5-03 | decision-critical DC-10, `lab/k3s-footprint-restore` |
| T-W5-03 (corrected) | LT-PI5-04 | 06 §14, 01 §4.6 |
| T-W5-01 | LT-PI5-05 | 06 §14 |
| W2-HW-1, W2-HW-2 | LT-PI5-06 | 03 §13 |
| T-W3-02 (SD) | LT-PI5-07 | 04 §15 |
| LAB-W7-1 (Pi) | LT-PI5-08 | 08 §10 |
| LAB-W7-2 | LT-PI5-09 | 08 §10 |
| DC-17 founder test, T-W5-04 | LT-PI5-10 | decision-critical, 06 §14 |
| P-1 (07) | LT-PI5-11 | 07 §12 |
| T-W19-01 (Pi half) | LT-PI5-12 | 29 §16 |
| LAB-W8-1/2/6/7/8, W10-T3/T5/T6, T-W9-02/03/04, T-W13-4, T-W12-2, T-W11-08, T-W19-05, Argo vs Flux, Pi 5 mainline boot | LT-PI5-13a–l | 09 §11, 11 §11, 10 §13, 14, 13, 12, 29, 05 §14 |
| E10 kernel × EEPROM matrix (rev. 4) | LT-PI5-14 | 01 §5.9.2, REC-DEC-47 |
| aarch64-gate A1 (16 KiB pages), A2 (Pi trial-boot power pull) | LT-PI5-01 (step A1; A2 = F-P11) | `lab/aarch64-gate` §9 |
| DC-08 r36 → r39 OTA (rev. 4) | LT-JET-01 step 3 | 01 §5.9.2, decision-critical DC-08 |
| T-W3-06, LAB-W7-4 | LT-JET-01 | 04 §15, 08 §10 |
| W2-HW-4, W10-T4 | LT-JET-02 | 03, 11 |
| T-W18-5, T-W18-6 | LT-JET-03 | 28 §9.4 |
| LAB-W7-5, LAB-W7-1 (Orin) | LT-JET-04 | 08 §10 |
| J-1 | LT-JET-05 | 07 §12 |
| LAB-W7-6 | LT-JET-06 | 08 §10 |
| Mender E3 | LT-JET-07 | steelman-updates-mender |
| T-W9-02 (Jetson) | LT-JET-08 | 10 §13 |
| T-W19-01, T-W19-02, T-W3-04, T-W3-03, mender F3/F4, F-U1/F-U2, N8 aarch64, T-W18-1/2/4, T-W3-05, k3s T1/T4/T5/T6, DC-20 re-run, T-W15-01, LAB-W8-3/4/5, Z-27, S-1, S-2, T-W9-05, T-W19-04, T-W12-1/4, T-W11-05 | LT-VM-01…19 | 29, 04, `lab/*`, 28, 16, 09, 07, 10, 13, 12 |
| rauc-k3s-gate F3 (RAUC 1.15.x) | **done** by `lab/rauc-1152` [C-LAB-rauc-1152-011] | — |
| N8 aarch64 RAUC + k3s gate in QEMU | **done** by `lab/aarch64-gate` [C-LAB-aarch64-gate-004]; the rest of LT-VM-08 remains | — |
| Secure Boot on RAUC 1.15.2 (critic N8) | **done** by `lab/secureboot-1152` [C-LAB-secureboot-1152-005]; hardware stays LT-X86-03/04 | — |
| T-W3-03 cluster variant (rev. 4) | LT-VM-04 (b) | 01 REC-DEC-45 |
| Secure Boot on the Ubuntu leg (rev. 4) | LT-VM-20 | 01 §10 |
| LAB-W7-3, DC-13 GPU lab | LT-GPU-01 | 08, decision-critical |
| Isaac Sim on Debian (Z-17) | LT-GPU-02 | 26 |
| T-W9-03 (RTX) | LT-GPU-03 | 10 |
| A.0/A.1, T-W14-01…07, A.2 | LT-EUD-00…08 | 15 Appendix A |
| T-W13-2, T-W13-3, T-W11-03, T-W11-04, T-W11-06, T-W13-5 | LT-EUD-09…14 | 14, 12 |
| T-W5-06, T-W12-5, W12-N3, Q80, Q120, Q140, Q155, Q220, Q271, 05 §9.2 commands | LT-CLU-01…12 | 06, 13, qbank W4/W6/W7/W9/W11/W12, 05 |
| T-W16-1…5, T-W18-3 | LT-BIZ-01…05 | 17, 28 |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **A/B update** | Two copies of the OS (slots A and B). The update is written to the idle copy; if it fails, the box boots the old one |
| **Health gate** | A check after the first boot of a new version; only if it passes does the update become permanent ("commit" / "mark-good") |
| **Fresh signal** | A health signal produced *during this boot* (e.g. the kubelet answering now), not a stale "Ready" left over from before |
| **Power pull (PP-10)** | Pulling the power cord at chosen moments, 10 times, to prove an update can never brick the box |
| **RAUC / Rugix / Mender** | Open-source A/B update engines. RAUC is recommended; Mender is the runner-up; Rugix is what Umbrel uses |
| **tryboot** | The Raspberry Pi 5 firmware's "boot the other copy once" feature; any failure returns to the old copy |
| **UKI** | Unified kernel image: kernel + initrd + command line in one signed file |
| **Secure Boot / PK, KEK, db, dbx** | Firmware checks that boot files are signed. PK is the owner key, KEK the key-exchange key, db the allowed signers, dbx the revoked ones |
| **TPM / PCR** | A security chip that can keep a disk key and release it only when measurements (PCRs) match the expected boot |
| **OTP / fuses** | One-time-programmable bits on the Pi or Jetson. Writing them is irreversible; this plan never does |
| **k3s / SQLite / etcd** | Small Kubernetes; its database is SQLite (one box) or embedded etcd (several servers) |
| **cyclictest** | A tool that measures how late the system wakes a high-priority task (latency) |
| **L4T / JetPack** | NVIDIA's Linux for Jetson and its SDK |
| **meta-tegra** | The community Yocto layer for building Jetson images from source |
| **Core leg** | One of the two base versions the same image recipe builds until the base is locked: Ubuntu 26.04 (the decision of record) and Debian 13 |
| **Decision map** | `01` §3.1.6 (h): what each result of LT-PI5-02 and of Canonical's answer does to the base-OS choice, written before either exists |
| **shim / `vendor_cert`** | shim is the small signed first-stage loader many distributions use for Secure Boot; `vendor_cert` is a key built into it, which can let the kernel trust modules signed with that key |
| **Page size (4 KiB / 16 KiB)** | The unit the kernel manages memory in. The Pi 5's default kernel uses 16 KiB; some software assumes 4 KiB |
| **QSPI** | The flash chip on a Jetson module that holds its boot firmware, outside the A/B root filesystem |
| **sysext / confext** | systemd features that add files to `/usr` or `/etc` from a separate image without changing the OS copy |
| **GrapheneOS / EUD** | A hardened Android for Pixels; EUD = end-user device (a phone or tablet running ATAK) |
| **Read-only check** | A command that only looks at the cluster (get, describe, list) and changes nothing |
| **PSA** | Pod Security Admission: Kubernetes namespace labels that block unsafe pods (privileged, baseline, restricted) |
| **labgrid / AutoKit** | Tools that automate tests on real boards (power, serial, SD switching) |

---

## 15. Gaps, assumptions and limits

- **Nothing here has run on hardware yet.** Every expectation comes from emulated labs (00 §6) and documentation. Results must be written before they are claimed.
- **Assumption (rule 8):** the Dell's OneMind tests boot from a spare USB SSD so the Omarchy pilot install survives; if the founder prefers to wipe the Dell, LT-X86 time drops but the Omarchy pilot is lost (11 §10).
- **Assumption:** a second Pi 5 with **4 GB** is bought for LT-PI5-03 (the 4 GB floor test); with only an 8 GB board, cap usable RAM with `mem=4G` on the kernel command line and say so in the result.
- **Not covered:** Pi 5 OTP secure boot combined with tryboot, and an EEPROM update in the same release (critic Q-P2-4; needs a dedicated Pi and irreversible steps); drones (year 2+, 08 §11.2); radio certification.
- **Live cluster:** secrets encryption at rest and API audit logging are provider-managed and cannot be seen with read-only verbs; LT-CLU-04's `owner=helm` label filter is UNVERIFIED in this pass (if it returns nothing, the founder's existing Helm inventory in `context/01` stands).
- **Commands from other files** were consolidated, not re-run: their correctness rests on each lab's own desk pre-flight (rauc-1152 §7.4 for the Pi kit) or on the cited docs. The `argocd`, `doctl`, `kubectl` and PSA forms here were checked against current primary docs [C-LABPLAN-006…010].
- **Rev. 4 sync (2026-11-11):** this file follows `01` revision 4. Base-OS wording now reads "the core leg S1 selects" (Ubuntu 26.04 under the decision of record; Debian 13 is the pre-registered result if LT-PI5-02 fails); LT-PI5-02 runs before G1; LT-PI5-14 and LT-VM-20 are new; LT-X86-03/04 use the RAUC 1.15.2 Secure Boot kit; LT-JET-01, LT-VM-03, LT-VM-04, LT-VM-13, LT-VM-16, LT-X86-12, LT-X86-14 and LT-PI5-03 carry the round-4 refuters' extensions. The two new labs ran on Debian guests under emulation only (§1.1). The DC-21, DC-E10 and DC-08 technical refuters' sources are not ledgered (01 §12), so the shim, overlay and r36 → r39 rationales here cite those files by name. **LT-JET-01's r36 → r39 claim needs a production Orin NX module**, which is not in the Day-1 order.
- **Status sync for other owners:** each DC Result block in `decision-critical.md` can now point to the LT IDs in §13 (01 §12 already notes that 22 exists); the qbank `blocked: founder-hardware` / `live-cluster` rows can cite their LT ID. 09 §8.2/§8.3 acceptance tests still say "Rugix rollback"; under REC-DEC-05 they run on RAUC.
