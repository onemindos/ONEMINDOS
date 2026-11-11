# Lab spike LAB-rauc: RAUC A/B image on x86_64 in QEMU

**Status:** COMPLETE: T0–T7 PASS in 2 full runs (results below). Pre-registered (goal, hypothesis and pass/fail criteria written 2026-11-11 01:04 UTC, before any build or test ran). The sections below the line "Results" are filled in after the run.

> **Explain it like I'm the founder.** A phone or a Home Assistant box never updates the system it is currently running on. It keeps two copies of the operating system, slot A and slot B. The update is written into the copy that is *not* running. On the next boot the machine tries the new copy once. If the new copy proves it is healthy, it is kept ("committed"). If it fails, the machine goes back to the old copy by itself. This spike builds exactly that, using **RAUC** (the update tool Home Assistant OS uses), on a Debian 13 image, inside a virtual PC on the Mac. Then it deliberately breaks things: an update that boots but is unhealthy, an update that cannot boot at all, and a power cut in the middle of writing the update. The question is simple: does the machine always come back on a working system without anyone touching it?

## 1. Goal

Build a minimal **Debian 13 (trixie) x86_64** disk image with a **RAUC A/B** layout (two root filesystem slots, GRUB on UEFI), boot it in QEMU, and prove three failure paths end on a working system with no human action:

1. **Forced bad update, health-gated commit.** A signed bundle installs and boots, but a core service fails. A health-gate service must refuse to commit the slot, mark it bad and reboot, and the machine must come back on the old slot.
2. **Forced bad update that cannot boot.** A signed bundle whose new root filesystem panics at boot. The bootloader's try counter must fall back to the old slot.
3. **Power cut mid-update.** QEMU is killed (`SIGKILL`, the virtual equivalent of pulling the plug) while RAUC writes the inactive slot. On the next boot the old slot must run, and a repeated install must succeed.

Plus two controls: a **good** update that commits, and an **unsigned / wrongly signed** bundle that RAUC must refuse.

Bonus if time allows: a power cut *after* the new slot boots but *before* it is committed (the "commit window").

This spike substitutes a small systemd "core" service for **k3s readiness** in the health gate. Running k3s inside an emulated x86_64 guest on an Arm Mac is too slow to be meaningful; the k3s-readiness version of the gate is written as a founder-runnable test (section 8).

## 2. Hypothesis

- H1: RAUC's documented GRUB integration (env variables `ORDER`, `A_OK`, `A_TRY`, `B_OK`, `B_TRY` in a `grubenv` file on the EFI partition) gives automatic fallback after one failed boot attempt, with no custom bootloader code.
- H2: Because RAUC marks the target slot unbootable *before* writing it and only switches the boot order *after* the write completes, a power cut during the write leaves the machine booting the old slot, and the half-written slot is simply rewritten by the next install.
- H3: A ~40-line health-gate service (`rauc status mark-good` on success, `rauc status mark-bad` plus reboot on failure) is enough to implement the ADR-001 rule "commit only after the platform is healthy".
- H4: All of this can be built and tested from an Apple Silicon Mac using only a Lima Linux VM plus QEMU, with no x86 hardware.

## 3. Pass / fail criteria (frozen before the run)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | One script, run inside a Lima VM, produces `disk.img` plus 4 bundles (`good`, `bad-health`, `bad-boot`, `wrong-key`); `rauc info` verifies the 3 signed bundles against the lab CA | Any step needs manual edits, or the image cannot be built on an Arm host |
| T1 | First boot | Guest boots slot A; `rauc status` shows A booted and good, B inactive | No boot, or RAUC cannot read the GRUB environment |
| T2 | Signature control | `rauc install wrong-key.raucb` exits non-zero with a signature/verification error; slot B and the boot order are unchanged | The bundle installs, or the boot order changes |
| T3 | Good update | Install `good` on A, reboot, guest runs B with `ONEMIND_VERSION=2`, health gate logs `mark-good`, `rauc status` shows B good; one more reboot still lands on B | Ends anywhere but committed B |
| T4 | Bad update, health gate | Install `bad-health` (v3) from the committed slot, reboot: the new slot boots, gate finds the core service unhealthy, runs `mark-bad` and reboots; guest ends on the previous slot (v2) with no human input, within 2 boots | Guest stays on the unhealthy slot, or needs manual action |
| T5 | Bad update, unbootable | Install `bad-boot` (v4), reboot: the kernel panics on the new slot, auto-reboots, GRUB skips the slot (TRY=1, never marked good) and boots the previous slot (v2) with no human input | Boot loop, or stuck on the broken slot |
| T6 | Power cut mid-write | Start installing `good` (v2-rewrite) and `SIGKILL` QEMU while RAUC is copying the image (confirmed by the log line before the kill). Next boot runs the old slot; `rauc status` shows the target slot is not primary; re-running the install succeeds and T3's end state is reached | Guest does not boot, boots a half-written slot, or the second install fails |
| T7 (bonus) | Power cut in commit window | After install + reboot into the new slot, `SIGKILL` before the gate marks it good. Next boot falls back to the old slot | Guest keeps booting the uncommitted slot |

A test that cannot run because of an environment limit is recorded as **BLOCKED** with the exact reason, never as PASS.

## 4. Design

- **Disk (GPT, 8 GiB raw):** `p1` ESP 128 MiB FAT32 (`EFI/BOOT/BOOTX64.EFI`, `grub.cfg`, `grubenv`) · `p2` `rootfs-A` 2 GiB ext4 · `p3` `rootfs-B` 2 GiB ext4 · `p4` `data` ext4 (rest; RAUC status file, test log). Fixed PARTUUIDs so the kernel command line can name the slot.
- **Bootloader:** GRUB EFI built with `grub-mkstandalone`; boot logic is the RAUC-documented GRUB script; kernel and initrd are read from inside the chosen slot, so kernel and root filesystem update together.
- **RAUC:** Debian package, `bootloader=grub`, slots by partition label, `verity` bundle format (as HAOS uses), X.509 signing with a throwaway lab CA kept outside the repo.
- **Health gate:** `onemind-health-gate.service` waits up to 60 s for `onemind-core.service` to be active and its heartbeat fresh; then `rauc status mark-good` or `rauc status mark-bad` + `systemctl reboot`. It only marks bad when the *other* slot is good (so it can never make a machine unbootable).
- **Bad bundles:** `bad-health` ships a core service that exits 1; `bad-boot` replaces `/sbin/init` with a program that exits, so the kernel panics (`panic=5` reboots it).
- **Where things run:** every upstream tool (debootstrap/mmdebstrap, RAUC, GRUB, QEMU running the test guest) runs inside a disposable Lima VM (Debian 13 arm64). The x86_64 guest runs under QEMU TCG emulation inside that VM, with no network device.

## 5. Requirement IDs served

R-1 (safe, user-controlled updates), R-3 (long-term maintainability of sold hardware), M-6 (guard rails for a solo developer), P-4 (OS Image surface), P-7 (bring-your-own-hardware x86 install). Feeds ADR-001 D3 and `04-image-install-updates-rollback.md` (W3).

## 6. Glossary

| Term | Meaning |
|---|---|
| A/B (symmetric) update | Two equal root filesystem slots; write the idle one, then switch |
| Slot | One copy of the OS (here a partition) |
| RAUC | "Robust Auto-Update Controller", LGPL-2.1 update client used by Home Assistant OS |
| Bundle (`.raucb`) | The signed update file: a squashfs with the new images plus a manifest and signature |
| verity bundle | Bundle format where every block is hash-checked by the kernel (dm-verity) while reading |
| GRUB / grubenv | The bootloader, and a 1 KiB file of variables GRUB can read and write at boot |
| `mark-good` / `mark-bad` | RAUC commands that tell the bootloader to keep or reject the booted slot |
| Health gate | A boot-time check that decides whether to commit the new slot |
| TCG | QEMU's pure-software CPU emulator (used because the Mac is Arm and the guest is x86_64) |
| SIGKILL | Immediate process kill; for a VM it is the same as pulling the power cable |

---

## Results

**Verdict: PASS (T0–T7 all pass), with the limits in section 8.** The final run (run 4) took 12 minutes on 2026-11-11 (01:48–02:00 UTC). A repeat run on the same image (run 5, 13 min) also passed 7/7; its power cut landed at 48 % of the write (`logs/driver-run5.log`). Runs 1–3 found and fixed four integration bugs (section 9). None of those bugs were in RAUC's own update logic.

> **Explain the result like I'm the founder.** RAUC did its job every time. A bad update that started but was unhealthy rolled itself back. An update that could not even boot rolled itself back. Pulling the virtual power cable halfway through writing the update left the box on the old, working system, and the next try worked. Pulling it during the first boot of the new system also sent the box back to the old system. Nobody had to touch it. The work that remains is not "does RAUC work". It is (1) making the health check real (k3s and the core pods, not a stand-in), (2) proving it on real hardware with a real power pull, and (3) choosing how many boot attempts a new version gets.

### 7.1 Test results (run 4)

| ID | Result | Evidence (line numbers in `logs/serial-run4-trimmed.log` unless noted) |
|---|---|---|
| T0 | **PASS** | `logs/build-run4.log`: 4 bundles built; `good`, `bad-health`, `bad-boot` show "Verified inline signature by 'O = OneMind LAB, CN = lab-signer'", `wrong-key` rejected by `rauc info`. Whole build ≈ 5 min inside the Lima VM (amd64 rootfs bootstrapped through qemu-user). |
| T1 | **PASS** | First boot to committed slot A in 33 s (TCG emulation). `GRUB-RAUC: ORDER=A B A_OK=1 A_TRY=1 …` then `HEALTH-GATE: RESULT mark-good slot=A version=1`; `rauc status`: `Booted from: rootfs.0 (A)`, A good, B bad (empty). |
| T2 | **PASS** | `LastError: signature verification failed: Verify error: unable to get local issuer certificate`; grubenv identical before and after [C-LAB-rauc-014]. |
| T3 | **PASS** | Install 62 s (1.8 GB ext4 image in a 239 MB verity bundle). `GRUB-RAUC: ORDER=B A … B_OK=1 B_TRY=1 default=2` then `RESULT mark-good slot=B version=2`; second reboot also `mark-good slot=B version=2` [C-LAB-rauc-013]. |
| T4 | **PASS** | New slot A v3 boots, then `RESULT mark-bad slot=A version=3 core-unhealthy -> reboot to B`; next boot `GRUB-RAUC: … A_OK=0 …` and `RESULT mark-good slot=B version=2` [C-LAB-rauc-015]. |
| T5 | **PASS** | `BAD-BOOT: broken init exiting`, `Kernel panic - not syncing: Attempted to kill init!`; after the `panic=5` reboot `GRUB-RAUC: … A_OK=1 A_TRY=1 … default=2` (A skipped) and `RESULT mark-good slot=B version=2` [C-LAB-rauc-016]. `rauc status` then shows A as `boot status: bad`. |
| T6 | **PASS** | RAUC journal on the console: `Marking target slot rootfs.0 as non-bootable...`, `writing data to device /dev/disk/by-partlabel/rootfs-A`, ` 47% Copying image to rootfs.0`, then `POWER CUT: SIGKILL qemu`. Restart: `GRUB-RAUC: ORDER=A B A_OK=0 …  default=2` → `mark-good slot=B version=2`. Re-install succeeded and committed `slot=A version=2` [C-LAB-rauc-017]. |
| T7 | **PASS** | New slot B booted (`HEALTH-GATE: start slot=B`), killed 3 s later, before the 15 s soak ended. Restart: `GRUB-RAUC: ORDER=B A A_OK=1 A_TRY=1 B_OK=1 B_TRY=1 default=1` → `mark-good slot=A version=2` [C-LAB-rauc-018]. |

### 7.2 Hypotheses

| | Verdict | Why |
|---|---|---|
| H1 | **Confirmed** | RAUC's reference GRUB script [C-LAB-rauc-006] plus its GRUB backend [C-LAB-rauc-004, -005] gave automatic fallback in T4, T5 and T7 with no custom bootloader code beyond `insmod` lines. |
| H2 | **Confirmed (in emulation)** | The code marks the target bad before writing and active only after [C-LAB-rauc-003]; T6 shows exactly that order on the console and a clean recovery. The real-hardware caveat is in section 8. |
| H3 | **Confirmed, with a design caveat** | The gate is 40 lines of shell (`scripts/build.sh`, `onemind-health-gate`). Caveat: with RAUC's GRUB script **every** boot sets `TRY=1`, so the gate must run and `mark-good` on every boot (as HAOS's Supervisor does [C-LAB-rauc-011]). A production gate should only `mark-bad` on the **first boot after an update**; on later boots a failure should raise an alert, not silently roll back to an older OS. |
| H4 | **Confirmed** | Everything ran on the M5 Mac: Lima (Debian 13 arm64, vz) + qemu-user for the amd64 build + QEMU TCG for the x86_64 guest. No x86 hardware or nested virtualization was needed. Cost: emulation is slow (33 s boot, 62 s for a 1.8 GB slot write). |

### 7.3 What the numbers mean for OneMind

- **One try or three?** RAUC's reference script gives a new slot one boot attempt [C-LAB-rauc-006]. HAOS gives three [C-LAB-rauc-010]. T7 shows the cost of one try: a single power blip during the first boot abandons the update (safe, but the user has to click "update" again). Three tries tolerate blips, but a crashing kernel then boots three times before falling back. **Recommendation:** 2–3 tries, with a hardware watchdog so a hung (not crashed) boot also counts as a failure.
- **What "healthy" means is OneMind's choice, not RAUC's.** HAOS commits once the Supervisor runs [C-LAB-rauc-011]. ADR-001 wants k3s plus core pods. RAUC accepts either; the gate script is where the policy lives.
- **Rollback only covers the OS.** The data partition is shared by both slots. If version N+1 migrates app or k3s data and then rolls back, version N must still read it (Umbrel handles the same issue for ZFS with `compatibility=openzfs-2.3`, per `research/platform/verify-updates-rollback-backups-security.md` §2). The lab did not test data migrations.

## 8. What this lab did NOT prove (limits) and founder-runnable tests

| Gap | Why it is not covered here | Status |
|---|---|---|
| Gate on real **k3s readiness** | k3s inside an emulated x86_64 guest on an Arm Mac would take minutes per boot and mostly measure emulation speed; the stand-in service tests the same RAUC mechanism | **BLOCKED (emulation speed / time-box)** → test F1 |
| A **real** power pull | `SIGKILL` of QEMU with `cache=writeback` kills the guest instantly, but writes QEMU had already passed to the Lima VM's page cache survive. A real power pull can also lose the disk's own volatile write cache, and the FAT `grubenv` write is the classic weak point | **Founder hardware** → test F2 |
| Raspberry Pi 5 (tryboot) and Jetson (UEFI/L4T) | x86_64 only in this spike; RAUC on Pi 5 needs a custom backend (HAOS ships `rpi-tryboot.sh`, see context/03) | Out of scope (separate spikes) |
| UEFI Secure Boot | GRUB built here is unsigned; OVMF ran without Secure Boot | Out of scope (W6) |
| Delta / adaptive updates, streaming over HTTP | Bundles were full images read from the data partition; the guest had no network | Not tested |
| Repetition | 2 full runs (runs 4 and 5); one power-cut point per run (47 % of the write in run 4) | A sweep of kill points is test F2b |

### F1: k3s-readiness health gate (x86 box, e.g. the Beelink or the Dell 5540)

1. Build as in section 12, but add k3s to the image: in `scripts/build.sh`, after `mmdebstrap`, download a pinned k3s binary **inside the Lima VM** (`curl -fsSLo $R/usr/local/bin/k3s https://github.com/k3s-io/k3s/releases/download/<version>/k3s` and compare it with that release's `sha256sum-amd64.txt`), add a `k3s.service` (`ExecStart=/usr/local/bin/k3s server --data-dir /data/k3s`), and use `HW=1` (see below).
2. Replace the health test in `onemind-health-gate` with: `k3s kubectl get --raw /readyz` returns `ok` **and** `k3s kubectl wait --for=condition=Ready pod --all -n kube-system --timeout=300s` succeeds; set `SOAK=60`.
3. Build `bad-health` by making k3s fail to start (for example `ExecStart=/bin/false`).
4. On the Mac: `limactl copy lab-rauc:/var/lab/out/disk.img ./disk.img`; `diskutil list` (find the **spare** USB SSD, e.g. `/dev/disk7`; double-check the size); `diskutil unmountDisk /dev/disk7`; `sudo dd if=disk.img of=/dev/rdisk7 bs=4m`. Boot the box from it in UEFI mode with Secure Boot off.
5. Run the same T3/T4/T5 steps by hand: `rauc install /data/bundles/good.raucb && systemctl reboot`, then `cat /data/gate.log` and `rauc status`.

**PASS:** good update commits only after `/readyz` is `ok` and all kube-system pods are Ready (time recorded); `bad-health` returns to the previous slot without a keyboard; `cat /data/gate.log` shows `mark-bad` then `mark-good`. **FAIL:** any boot needs a keyboard, or a slot is committed before k3s is Ready.

`HW=1` is not implemented in the tested script: for hardware add `console=tty0` before `console=ttyS0` in `CMDLINE` and an autologin drop-in for `getty@tty1` like the serial one, because the lab image locks the root password and only auto-logs-in on the serial port. Remove both before any non-lab use.

### F2: real power pull during an update (same box)

1. Boot the F1 image on the box; `rauc install /data/bundles/good.raucb` and, while it prints ` NN% Copying image`, pull the power cable. Repeat 10 times at different moments (start of copy, middle, the second it prints `done`, during the reboot, during the first boot of the new slot).
2. After each pull, power on and record: which slot booted (`rauc status`), `grub-editenv /boot/efi/EFI/BOOT/grubenv list`, and whether `fsck.vfat -n /dev/disk/by-partlabel/esp` reports errors.
3. **PASS:** 10/10 pulls end on a booting, committed slot with no keyboard, and a re-run install always succeeds. **FAIL:** any pull leaves a box that does not boot, or a corrupt `grubenv`/ESP. (F2b: script the same on QEMU with a kill-delay sweep of 0–60 s to cover more points cheaply.)

## 9. Deviations and problems found during the run (honest log)

Runs 1–3 failed for reasons that are themselves findings. Each fix is in `scripts/build.sh` with a comment.

1. **Signing certificate purpose.** A signer certificate with `extendedKeyUsage=codeSigning` was refused by RAUC 1.13: `signature verification failed: Verify error: unsuitable certificate purpose`. RAUC's default check purpose is OpenSSL `smimesign`; a codeSigning chain needs `check-purpose=codesign-rauc` in `[keyring]` [C-LAB-rauc-009]. The lab dropped the EKU. **For OneMind's real PKI, decide this explicitly** (codeSigning EKU + `check-purpose=codesign-rauc` is the stricter choice).
2. **Debian splits RAUC in two.** The `rauc` package alone gives a CLI that cannot run `status`, `mark-good` or `install` ("The name de.pengutronix.rauc was not provided by any .service files"); the daemon is in `rauc-service` [C-LAB-rauc-002]. Easy to miss when building a Debian image.
3. **GRUB standalone image.** `grub-mkstandalone` did not load `part_gpt`, so `(hd0,gpt1)` did not exist and GRUB stopped at its shell; fixed with explicit `insmod` lines [C-LAB-rauc-019].
4. **Silent gate failure.** The first gate version exited 0 without logging when `mark-good` failed. Fixed to log `RESULT commit-error`. Lesson: the gate must never fail silently, because an uncommitted slot is abandoned on the next reboot.
5. **Driver bug (not a guest failure).** Run 3 stopped at T6 because the test driver sent `cmd &; echo`, a bash syntax error. Fixed; logs kept as `logs/driver-run3-T6driverbug.log`. T1–T5 had passed in run 3 too.
6. Minor: `systemd-logind` restart-looped in this minimal image and was masked (not on the update path). Debian 13 ships RAUC 1.13, not the latest upstream 1.15.2 [C-LAB-rauc-001]; a product image should consider building newer RAUC.

## 10. What competitors do

| Product | Update tool and bootloader integration | When the new slot is committed | Tries before fallback | Constraint fit for OneMind |
|---|---|---|---|---|
| Home Assistant OS | RAUC; GRUB on x86 with grubenv on the ESP, PARTUUID roots [C-LAB-rauc-010] | When the Supervisor starts and calls `Mark(GOOD, booted)` [C-LAB-rauc-011] | 3 (`TRY -lt 3`) [C-LAB-rauc-010] | **High** for the mechanism (same tool, same x86 layout as this lab, Apache-2.0 repo). **Medium** for the gate: HAOS is Docker-based, so "Supervisor up" is a weaker test than OneMind's "k3s + core pods Ready". |
| umbrelOS 2.0 | Rugix (not RAUC), GRUB/tryboot boot flows; Debian trixie (see `research/platform/verify-updates-rollback-backups-security.md` §2) | How umbreld commits is UNVERIFIED in prior work | Not checked in this spike | **High** for base OS (Debian, x86 + Pi); license PolyForm-Noncommercial, so patterns only. The `debian-rugix` lab spike covers it. |
| This lab (OneMind candidate) | RAUC 1.13 from Debian; RAUC reference GRUB script | After a health gate passes (stand-in for k3s) | 1 | Proves the RAUC path works on a Debian base from a Mac; needs F1/F2 on hardware. |

## 11. Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| L-1 | Treat **RAUC on a Debian 13 base** as a proven-in-lab option for the x86 tier of ADR-001 D3: signed verity bundles, health-gated commit and power-cut safety all worked with stock Debian packages. It stays a valid fallback (or lead) next to Rugix, decided by the `debian-rugix` spike and the Pi 5/Jetson spikes. | R-1, R-3, M-6, P-4 |
| L-2 | Make the health gate a **first-class OneMind component** (versioned, tested): `mark-bad` only on the first boot after an update; on later boots alert instead of rolling back; never fail silently; log to the data partition for the dashboard. | R-1, R-2, M-6 |
| L-3 | Give a new slot **2–3 boot attempts** plus a hardware watchdog, instead of RAUC's reference single try. | R-1, R-3 |
| L-4 | Decide the **signing certificate profile** now: codeSigning EKU with `check-purpose=codesign-rauc`, separate dev and release CAs (as HAOS does), keys in an HSM/PKCS#11 token. | R-1, R-3 |
| L-5 | Run **F1 and F2** on the founder's x86 box before the week-4 update-tool gate in `20-PLAN-180-DAYS.md`. | R-1, P-7 |

## 12. How to re-run

From the Mac (needs Lima ≥ 2.0; all upstream tools run inside the VM):

```bash
LAB=<lab-dir>/rauc          # outside the repo
mkdir -p $LAB/scripts $LAB/logs && cp research-output/evidence/lab/rauc/scripts/{build.sh,run-tests.py} $LAB/scripts/
limactl create --name lab-rauc --tty=false --vm-type vz --cpus 10 --memory 16 --disk 60 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-rauc
limactl shell lab-rauc -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf rauc \
  gdisk dosfstools mtools e2fsprogs squashfs-tools openssl grub-common python3
limactl shell lab-rauc -- sudo bash -c "OUT=/var/lab/out bash $LAB/scripts/build.sh"            # T0, ~5 min
limactl shell lab-rauc -- sudo bash -c "mkdir -p /var/lab/run && cp --sparse=always /var/lab/out/disk.img /var/lab/run/ && \
  python3 -I $LAB/scripts/run-tests.py --disk /var/lab/run/disk.img --log $LAB/logs/serial.log"   # T1–T7, ~12 min
limactl delete -f lab-rauc                                                                        # clean up
```

`run-tests.py` exits 0 only if all of T1–T7 pass. Build outputs are not reproducible byte-for-byte (ext4 UUIDs, timestamps and keys are random); the hashes of the tested run are in `SHA256SUMS`, the exact package versions in `image-packages.txt` and `logs/versions.txt`.

## 13. Pinned versions

| Item | Version |
|---|---|
| Host | macOS 27.2 on Apple M5 Max, Lima 2.3.0, QEMU 11.1.3 (host QEMU not used for the guest) |
| Lab VM | Debian 13.7 arm64 (Lima `template:debian-13`, vz), kernel 6.12.115+deb13.1-cloud-arm64 |
| VM tools | mmdebstrap 1.5.7-1+deb13u1, qemu-system-x86 / qemu-user-binfmt 10.0.13+ds-0+deb13u1, ovmf 2025.02-8+deb13u1, rauc 1.13-3+deb13u1, grub-common 2.12-9+deb13u2, squashfs-tools 4.6.1-1+b1, openssl 3.5.7-1~deb13u3 |
| Guest image | Debian 13 amd64 minbase; linux-image 6.12.116-1; systemd 257.13-1~deb13u1; rauc + rauc-service 1.13-3+deb13u1; grub 2.12-9+deb13u2 (full list: `image-packages.txt`) [C-LAB-rauc-012] |
| Firmware | OVMF_CODE_4M.fd sha256 `624e06de…e4e0` (full hashes in `logs/versions.txt`) |
| Upstream source read | rauc/rauc @ `2d17b27`, home-assistant/operating-system @ `ab7d0f1`, home-assistant/supervisor @ `040f14c` |
| Artefact hashes (run 4/5 image) | `SHA256SUMS` (`disk.img` `020177f3…734e`, `good.raucb` `bd8e08b2…d721`) |

## 14. Files

- `scripts/build.sh`: builds the image and bundles (runs as root inside the Lima VM).
- `scripts/run-tests.py`: boots the guest and runs T1–T7 (stdlib Python, run with `-I`).
- `scripts/grub.cfg.generated`: the GRUB boot script as built.
- `logs/driver-run4.log`, `logs/serial-run4-trimmed.log`, `logs/build-run4.log`, `logs/driver-run5.log`, `logs/driver-run3-T6driverbug.log`, `logs/versions.txt`.
- `SHA256SUMS`, `image-packages.txt`.
- Claims: `../../claims/LAB-rauc.csv`; sources: `../../sources/LAB-rauc.md`.
- Not committed (outside the repo, deleted after the run): the 8 GiB disk image, bundles, private lab keys, full serial logs.
