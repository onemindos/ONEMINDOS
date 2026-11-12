# Lab spike LAB-aarch64-gate: the RAUC 1.15.2 + k3s health-gate suite on native arm64

**Status:** COMPLETE: **PASS** on native arm64 under the pre-registered host fallback (QEMU + HVF), with every pass/fail test passing in 2 full runs (runs 4 and 5). The primary environment (nested KVM inside Lima) did not give a usable run, and the fallback needed a different UEFI firmware build; both are logged in §8. Pre-registered: goal, hypotheses, design and pass/fail criteria were written 2026-11-11, before any build or test of this spike ran. The sha256 of this file at that moment is in `../PREREGISTRATION.md`. Results are added below the line "Results" after the run; nothing above that line is changed afterwards except typo fixes and the Status line, and any change is logged in the deviations section.

> **Explain it like I'm the founder.** Every test of our update safety net so far ran on an emulated **Intel/AMD (x86)** PC. But the first OneMind boxes many people will plug in are **Arm** boards: a Raspberry Pi 5, a Jetson. Arm is a different CPU family: different kernel, different boot firmware, different k3s download. This spike runs the same "break it on purpose" tests on an **Arm virtual machine** that runs at native speed on the Mac's Arm chip. It proves the software half of the story on Arm: RAUC 1.15.2, real k3s for Arm, and our health gate. It cannot prove the Raspberry Pi's own boot firmware (`tryboot`), because no emulator imitates it. That part stays a test you run on a real Pi 5 (`../rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`).

## 1. Goal

Close critic pass-3 gap **N8** ("no aarch64 RAUC + k3s gate run in QEMU"): run the T1–T11 suite of `../rauc-1152/` (itself the suite of `../rauc-k3s-gate/` plus a verity-only check) on an **aarch64 guest with hardware virtualization** instead of x86_64 under TCG emulation, with:

- **RAUC v1.15.2 built from the pinned upstream tag** (tag object `f1ceebd68b4edcf681c23d6a49aa5322d483c4d9`, commit `4fb7c798d6ae412344fb8f8d310d773046af3441`), natively for arm64, installed into the image in place of Debian's package, with `bundle-formats=verity`.
- **Real k3s v1.37.2+k3s1 for arm64** (`k3s-arm64` and `k3s-airgap-images-arm64.tar.zst`, verified against the release's `sha256sum-arm64.txt`), air-gapped.
- **The same fresh-signal health gate**, unchanged: the gate scripts, pre-install handler, units, manifests and GRUB slot logic are byte-identical to `../rauc-1152/scripts/guest/` except the serial console name in the GRUB template (`ttyAMA0` instead of `ttyS0`).
- **Boot chain:** UEFI firmware for Arm VMs (AAVMF/EDK2 from Debian's `qemu-efi-aarch64`) → GRUB `arm64-efi` (`BOOTAA64.EFI`) → Debian 13 arm64 kernel. Same 3-try GRUB script (Home Assistant OS logic).
- **Watchdog:** QEMU `i6300esb` (a PCI watchdog, usable on the `virt` machine) with `-action watchdog=reset`, systemd `RuntimeWatchdogSec=30s`, if the Debian arm64 kernel ships the `i6300esb` driver. If it does not, T7 is **BLOCKED** (not rewritten to a different watchdog after the fact).

The three tests the critic asked for are the core: **good update commits (T3), k3s-broken update rolls back by itself (T4, plus the stale-Ready variant T5), power cut mid-install (T8)**. The rest of the suite runs too, because it costs minutes under hardware virtualization.

## 2. Hypotheses

- **H1 (portability)** The suite ports to arm64 with no change to gate logic: only architecture inputs change (Debian arch, k3s artifacts, GRUB target and EFI file name, firmware, console name, QEMU machine). RAUC 1.15.2 builds natively for arm64 from the pinned commit with Debian 13 libraries.
- **H2 (same behaviour)** Every pass/fail result of `../rauc-1152/` run 2 repeats on arm64: T1–T9, T10r and T11 PASS; T10 (naive gate) again commits a kubelet-less system.
- **H3 (reproducible RAUC build)** The arm64 `rauc` binary built here has the same sha256 as the one built in `../rauc-1152/` (`7f076b8b8ab7882dd4522952d511354c9d23690280945965ec14ad0009639d1f`), because the source commit, compiler and libraries are the same Debian 13 packages. Observation, not a pass/fail test (a newer Debian point release may change it).
- **H4 (speed)** Under hardware virtualization a good update commits in well under the ~80–150 s seen under x86 TCG. Observation only; the 300 s deadline is **not** changed, so the timing of a rollback stays comparable.

## 3. Pass / fail criteria (frozen before the run)

Same starting state and rules as `../rauc-1152/` §3: the box starts on slot A, v1; "no human input" means the driver sends no command between the install's `reboot` and the end state, except defined power cuts; gate deadline **300 s** per trial boot.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | Scripts inside a Lima VM: RAUC built from the pinned commit (checked-out `HEAD` = `4fb7c798…`), `rauc --version` = 1.15.2; arm64 `disk.img` and 8 bundles (`good` v2, `bad-k3s` v3, `bad-noagent` v4, `bad-boot` v5, `bad-hang` v6, `naive-noagent` v7, `wrong-key`, `plain-good` in plain format); k3s arm64 artifacts verified against `sha256sum-arm64.txt`; the guest kernel and every ELF binary in the slot that the suite depends on (`rauc`, `k3s`, `grub-editenv`) is aarch64; Debian `rauc` package not in the image; the image's kernel has an `i6300esb` module (else T7 BLOCKED) | Manual edit, hash mismatch, wrong commit, an x86 binary in the image, or Debian RAUC in the image |
| T1 | First boot | Slot A v1 boots via GRUB arm64-efi; gate `RESULT committed-boot slot=A version=1`; `K3S-FRESH ok`; `apps/broken-app` not Ready; guest `rauc --version` = 1.15.2; `uname -m` = `aarch64` | No boot, k3s never fresh-healthy, wrong RAUC, or not aarch64 |
| T2 | Signature control | `wrong-key` refused with a signature error; grubenv unchanged; no trial marker | Installs or boot order changes |
| T11 | Verity-only policy | `plain-good` refused with "Bundle format 'plain' not allowed"; grubenv unchanged; no marker | Installs, writes, or writes a marker |
| T3 | **Good update** | `good` v2 to B; ≥ 3 consecutive fresh passes, then `RESULT mark-good slot=B version=2`; `apps` pod not Ready at commit; next reboot `committed-boot B v2` | Anything else |
| T4 | **k3s broken** | `bad-k3s` v3 to A; `RESULT mark-bad slot=A version=3` at the deadline, automatic reboot, then `committed-boot B v2` with `A_OK=0` and `K3S-FRESH ok` | Commits v3, stays on v3, or needs input |
| T5 | Stale-Ready trap | `bad-noagent` v4 to A: same end state as T4 | Commits v4 |
| T6 | Kernel panic | `bad-boot` v5: exactly 3 boot attempts, then B; `fell-back`, A marked bad, not tried on the next reboot | Boot loop, ≠ 3 attempts, or A retried |
| T7 | Hang + watchdog | `bad-hang` v6: 3 watchdog resets, then B; A marked bad; not retried | Box stays hung, or A retried. BLOCKED if no `i6300esb` driver (T0) |
| T8 | **Power cut mid-install** | SIGKILL of QEMU after RAUC logged the trial marker, "Marking target slot rootfs.0 as non-bootable" and the start of the copy, and **before** the slot was marked active. Next boot: B v2 `fell-back`, marker cleared, `A_OK=0`; reinstall of `good` then commits A v2 | No boot, half-written slot boots, marker left, or reinstall fails. If the copy finished before the kill (slot activated), the run is **INVALID** for T8 (not PASS), and the driver's kill delay is a deviation to log |
| T9 | Power cut in commit window | Kill after the trial gate on B logged its first check, before commit; next boot `B_TRY=2`, then `mark-good B v2` with no reinstall | Update abandoned, or an ungated slot boots |
| T10 / T10r | Naive gate (observation) / recovery | T10 recorded only; T10r: reinstalling `good` from the naive-committed slot commits | T10r does not commit |

**Spike verdict:** PASS if T0–T9, T10r and T11 pass in at least one full run on one build; a second full run on a fresh copy of the same disk is the target and is reported either way. A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A run that fails because of a driver bug is kept in the logs and named as such.

## 4. Design

- **Host isolation:** the build (mmdebstrap, RAUC compile, k3s downloads, GRUB tools) runs inside a disposable **Lima VM** (`template:debian-13`, the Debian 13 arm64 cloud image, `vz`), whose only host mount is the lab work folder `<lab-dir>/aarch64-gate`. The test guest runs under QEMU **inside that VM with KVM**, using the Mac's nested virtualization (Lima `nestedVirtualization: true`, M3 or newer). **Fallback, decided now:** if `/dev/kvm` does not appear in the Lima VM, the same disk is booted by the host's Homebrew QEMU with `-accel hvf` (same machine model, same firmware file from inside the VM copied out with its hash, same driver, run with `python3 -I`). Both are native aarch64 virtualization. TCG emulation would be a logged deviation, not a silent swap. Guest networking: QEMU user-mode `restrict=on` (no route to the LAN or internet); k3s air-gapped.
- **Guest image:** built with `mmdebstrap` (Debian 13 arm64 minbase), exactly as the x86 suite built its amd64 image, so the only differences are architecture inputs. The Debian arm64 cloud image is the *build VM*, not the guest: a cloud image has a different package set (cloud-init, a different kernel flavour) and would add differences unrelated to the question.
- **Disk:** GPT 14 GiB, ESP 128 MiB, rootfs-A 2 GiB, rootfs-B 2 GiB, data (rest); same partition UUIDs and layout as `../rauc-1152/`.
- **Machine:** `qemu-system-aarch64 -machine virt -cpu host -smp 4 -m 3072`, AAVMF pflash (code read-only, per-run copy of vars), `virtio` disk, `virtio-net-pci` user net `restrict=on`, `-device i6300esb -action watchdog=reset`, serial on the virt machine's PL011 (`ttyAMA0`).
- **Write throttling (decided now):** the guest disk is throttled to **60 MiB/s writes** (`throttling.bps-write=62914560`) for every test. Two reasons: under KVM the 1.7 GiB slot copy could finish before the driver's power cut lands, which would make T8 vacuous; and 60 MiB/s is in the range of an SD card or cheap eMMC, which is closer to a Pi than a Mac SSD. The driver's T8 kill delay is shortened from 6 s to 2 s after the first "Copying image" line, for the same reason.
- **Driver:** `../rauc-1152/scripts/run-tests.py` with only the QEMU command line, firmware paths and the T8 delay changed (diff in `scripts/CHANGES-vs-rauc-1152.md`). T12 (CVE regression at bundle creation) is not repeated: it already ran on arm64 in `../rauc-1152/` [C-LAB-rauc-1152].

## 5. What an arm64 VM proves and does not prove about a Raspberry Pi 5 (written before the run)

| Proves (if PASS) | Does not prove |
|---|---|
| RAUC 1.15.2 (arm64 build) installs verity bundles, runs the pre-install handler, and marks slots good/bad correctly on arm64 | The Pi 5 **boot path**: EEPROM bootloader, `config.txt`, `autoboot.txt`, the `tryboot` one-shot flag and `reboot '0 tryboot'`. The VM boots UEFI + GRUB, which a Pi 5 does not use by default |
| k3s arm64 (binary and air-gap images) starts on a read-only arm64 root with state bind-mounted from `/data`, and the fresh-signal gate tells a healthy k3s from a broken or stale one | Pi-specific kernel (Raspberry Pi's `linux-image-rpi-2712`, 16 KiB pages) vs Debian's generic arm64 kernel (4 KiB pages) used here |
| The gate logic (trial / fell-back / committed, 3 passes, apps excluded, never retry a failed slot) is CPU-architecture-neutral | The Pi watchdog (`bcm2835-wdt`) and how the Pi firmware treats a watchdog reset during `tryboot` (the VM uses a PCI `i6300esb`) |
| A GRUB-based arm64 box (generic Arm servers, many industrial Arm boards with UEFI, SystemReady devices) can use the same design unchanged | Real power loss on SD/NVMe and FAT writes on the Pi's boot partition (QEMU SIGKILL does not drop disk caches) |
| Timing under native (not emulated) CPU speed, as a lower bound for the deadline | Pi 5 thermal or memory limits under k3s, or Jetson (NVIDIA's own A/B) |

## 6. Requirement IDs served

R-1 (safe updates), R-2 (self-healing), R-3 (maintainability), M-6 (guard rails for a solo developer), P-4 (OS image surface), and the Arm hardware tiers (P-1 Lite tier). Feeds REC-DEC-05 and REC-DEC-07 in `01-FOUNDATION-DECISION.md`; closes the emulator part of critic pass-3 N8.

## 7. Glossary

| Term | Meaning |
|---|---|
| aarch64 / arm64 | Two names for the 64-bit Arm CPU family (Pi 5, Jetson, Apple Silicon) |
| KVM / HVF | Hardware virtualization on Linux / on macOS: the guest runs directly on the CPU, at near-native speed |
| TCG | QEMU's software CPU emulator, used by the earlier x86 labs; many times slower |
| Nested virtualization | A VM that can itself run VMs with hardware acceleration |
| AAVMF | The UEFI firmware build for Arm virtual machines (EDK2) |
| `tryboot` | The Raspberry Pi firmware's "boot the other config once" switch, which RAUC's Pi backend uses instead of GRUB |
| Slot, commit, mark-bad, trial, fresh signal, stale-Ready trap | As in `../rauc-k3s-gate/README.md` §6 |

---

## Results

**Verdict: PASS.** On an arm64 (aarch64) guest running at native speed under the Mac's hypervisor (QEMU 11.1.3 `-accel hvf`), with RAUC 1.15.2 built from the pinned tag, k3s v1.37.2+k3s1 for arm64 and the unchanged fresh-signal gate, T0–T9, T10r and T11 passed in **two full runs on one build** (run 4: 26 min, 2026-11-11 13:28–13:54 UTC; run 5: 25 min, 13:54–14:20 UTC, each from a fresh APFS clone of the same disk, sha256 `62035cb3…8d22`). T10 (the naive gate) committed a kubelet-less system in both runs, as it did on x86 [C-LAB-aarch64-gate-004, -010]. Getting there took three failed or aborted attempts (runs 1–3). None of them was caused by RAUC, k3s or the gate; §8 records each one.

> **Explain the result like I'm the founder.** The update safety net behaves the same on an Arm computer as on a PC. The gate scripts were not changed, not even by one byte. The good update was accepted 31 seconds after the new version started checking itself. An update with broken Kubernetes went back to the old version on its own after the 5-minute limit. So did the sneaky one that only *looks* healthy from yesterday's records. A version that crashed, and one that froze, were each tried three times and then dropped for good. Pulling the virtual plug in the middle of writing an update did no harm: the box came back on the old version, and the next try installed cleanly. What this does **not** show is the Raspberry Pi's own way of switching between versions (`tryboot`), the Pi's own kernel, or a real power cord. Those still need the real-Pi test. We also learned something practical: the time limit is measured on the clock. On a slow or overloaded machine, a perfectly good update can run out of time. So the limit must be set from timings on the real hardware.

### 7.1 Run history (all kept in `logs/`)

| Run | Environment | Outcome | Cause |
|---|---|---|---|
| 1 | Nested KVM in the Lima VM, Debian AAVMF | **T1 FAIL**, then stopped by the operator after T11 | (a) Pods stayed `ContainerCreating` and RunPodSandbox failed after 5 min because the pause image was not yet available. Most likely cause: I/O contention, since QEMU started 23 s after the build had written ~20 GB in the VM. This is not proven. (b) A **driver bug**: an escape fragment `[?2004l` in front of `rauc v1.15.2` made the version check false. The guest really printed `rauc v1.15.2` and `ARCH=aarch64` (`logs/driver-run1.log`). Fixed before run 2. T2 and T11 passed |
| (debug 1–7) | Nested KVM, diagnostic boots | Not tests | Debug 1–2 showed containerd panicking on a corrupt bbolt database (`panic: assertion failed: Page expected to be: 176, but self identifies as 0`). **This was an operator error, not a finding.** Stopping run 1 with `pkill qemu-system-aarch64` matched nothing (Linux limits process names to 15 characters), so run 1's QEMU kept running. Its disk was then copied while it was still being written. The same stray QEMU, plus a second one left by a timed-out debug boot, loaded the CPU during debug 3–5. Debug 6–7, on an idle VM with a pristine disk: containerd up at 17 s, `K3S-FRESH ok after 61s`. The driver now kills its own QEMU on any exit (tracked processes, never by name) |
| 2 | Nested KVM, Debian AAVMF, idle VM after `sync` | **T1 FAIL** (`apiserver /readyz not ok` after the gate's 300 s window), stopped by the operator after T11 | The gate's "300 s" loop took **411 s of wall time** (start 13:04:27, alert 13:11:18): each check ran slowly. T1 had passed in debug 7 with the same disk and setup. Nested KVM gave erratic speed, so it was not a usable test environment. T2 and T11 passed |
| 3 | **Host QEMU 11.1.3 + HVF** (the pre-registered fallback), Debian AAVMF copied out of the VM (same hashes) | Hung in the UEFI firmware for 10 min (banner printed, then nothing), stopped | A firmware/accelerator mismatch in the lab tooling. A 120 s probe of the same disk with Homebrew QEMU's bundled EDK2 (`edk2-stable202408`) booted to `RESULT committed-boot` (`logs/fwtest-homebrew-edk2-trimmed.log`) [C-LAB-aarch64-gate-008] |
| **4** | Host HVF, Homebrew EDK2 | **All PASS** | Result run |
| **5** | Same, fresh disk clone | **All PASS** | Repeat |

### 7.2 Test results (runs 4 and 5)

Evidence: `logs/driver-run4.log`, `logs/driver-run5.log` (driver verdicts) and `logs/serial-run4-trimmed.log`, `logs/serial-run5-trimmed.log` (gate, GRUB and RAUC lines).

| ID | Run 4 | Run 5 | What happened (run 4) |
|---|---|---|---|
| T0 | **PASS** | (same build) | `logs/build-rauc.log`: `HEAD=4fb7c798…`, `rauc v1.15.2`. `logs/build-image.log`: k3s arm64 artifacts `OK` [C-LAB-aarch64-gate-002]; `rauc`, `k3s` and `grub-editenv` are `ARM aarch64`; kernel "ARM64 boot executable Image … 4K pages"; `i6300esb.ko.xz` present [C-LAB-aarch64-gate-003]; 7 bundles "Verified inline signature … Bundle Format: verity", `plain-good` "Bundle Format: plain", `wrong-key` rejected; Debian `rauc` not installed |
| T1 | **PASS** | **PASS** | Slot A v1 via GRUB arm64-efi: `RESULT committed-boot`, `K3S-FRESH ok after 42s` (31 s in run 5); `rauc v1.15.2`, `ARCH=aarch64`, `broken-app` not Ready |
| T2 | **PASS** | **PASS** | Signature error, grubenv unchanged, no marker |
| T11 | **PASS** | **PASS** | `Bundle format 'plain' not allowed`, grubenv unchanged, no marker |
| T3 | **PASS** | **PASS** | Trial on B: `CHECK pass 1/3 at 11s`, `2/3 at 21s`, `3/3 at 31s`, `RESULT mark-good slot=B version=2 after 31s`; `broken-app 0/1 ImagePullBackOff` excluded; reboot gives `committed-boot B v2` |
| T4 | **PASS** | **PASS** | k3s exits at start: `no kubeconfig on this boot` until `RESULT mark-bad slot=A version=3 after 300s … -> reboot to B` (≈316 s after the reboot); back on B v2, `A_OK=0`, `K3S-FRESH ok after 10s` |
| T5 | **PASS** | **PASS** | Stale-Ready trap: `kubelet /healthz not answering` until `RESULT mark-bad slot=A version=4`; back on B v2 |
| T6 | **PASS** | **PASS** | `BAD-BOOT` and `Kernel panic - not syncing: Attempted to kill init!` 3 times (`A_TRY=1→2→3`) in 71 s, then `default=2`; `RESULT fell-back … slot A (v5) marked bad, never retried`; the next boot shows `A_OK=0` and no attempt on A |
| T7 | **PASS** | **PASS** | `BAD-HANG: arming watchdog, then freezing` 3 times in 146 s (≈45 s per attempt, the i6300esb reset on arm64), then the same fallback |
| T8 | **PASS** | **PASS** | Console order: `pre-install: trial marker slot=A version=2`, `Marking target slot rootfs.0 as non-bootable (bad)`, `46% … 61% Copying image to rootfs.0`, `POWER CUT` (59 % in run 5); not activated before the cut. Restart: `GRUB-RAUC: … A_OK=0 … default=2`, `RESULT fell-back slot=B version=2; slot A (v2) marked bad`, marker cleared; reinstall `RESULT mark-good slot=A version=2 after 31s` |
| T9 | **PASS** | **PASS** | Killed after the trial gate on B started; next boot `B_OK=1 B_TRY=2 default=2`, then `RESULT mark-good slot=B version=2` without a reinstall |
| T10 (obs.) | **committed broken** | **committed broken** | `CHECK pass 1/3 at 10s … 3/3 at 30s (NAIVE: freshness off)`, `RESULT mark-good slot=A version=7 after 30s`; on that slot `curl localhost:10248/healthz` → `NO-KUBELET` |
| T10r | **PASS** | **PASS** | Reinstalling `good` from the broken-but-committed slot: `RESULT mark-good slot=B version=2` |

Each 490 MB verity bundle installed in 29–30 s under the 60 MiB/s write throttle.

### 7.3 Hypotheses

| | Verdict | Why |
|---|---|---|
| H1 | **Confirmed, with one tooling caveat** | Only architecture inputs changed (`scripts/CHANGES-vs-rauc-1152.md`); the 9 gate files are byte-identical. RAUC 1.15.2 built natively from `4fb7c798…` with Debian 13 libraries. The caveat is lab tooling, not the OS: under HVF the guest needed Homebrew's EDK2 instead of Debian's AAVMF |
| H2 | **Confirmed** | Every pass/fail result of `../rauc-1152/` run 2 repeated on arm64 in 2/2 valid runs. The T10 naive gate again committed a broken system, after 30 s here versus about a minute on x86 TCG [C-LAB-rauc-k3s-gate-008] |
| H3 | **Confirmed** | The arm64 `rauc` binary sha256 is `7f076b8b…639d1f`, byte-identical to `../rauc-1152/`'s build. The RAUC build is reproducible on Debian 13 at the same package versions [C-LAB-aarch64-gate-001] |
| H4 | **Confirmed** | A good update committed **31 s** after the trial gate started (first fresh pass at 10–11 s). On x86 TCG it took 81 s [C-LAB-rauc-k3s-gate-006] and 87–148 s [C-LAB-rauc-1152-011] [C-LAB-aarch64-gate-005]. Rollbacks still took the full 300 s deadline, as designed |

### 7.4 What this means for OneMind

1. **The gate design is architecture-neutral.** The same nine files work unchanged on x86_64 and arm64 with GRUB, [C-LAB-aarch64-gate-009], so REC-DEC-07's gate can ship as one shared component across the Lite (Arm) and x86 tiers. Only the boot backend differs per board (GRUB here, `tryboot` on a Pi 5, NVIDIA's A/B on Jetson).
2. **The deadline is wall-clock time, so a slow box can reject a good update.** In run 2 the gate's 300 s window took 411 s because the guest ran erratically slowly [C-LAB-aarch64-gate-006]. On a *committed* boot that only produced an alert. On a *trial* boot of a healthy update it would have caused a false rollback, which is safe but annoying, and the update would be marked bad. Two consequences: set the production deadline from real hardware timings with a wide margin (≈3× the good-commit time, as in `../rauc-k3s-gate/` F1), and do not run timing-sensitive gate tests on nested virtualization in CI. Use direct HVF or KVM, or real arm64 runners.
3. **The k3s state bind-mount list from `../rauc-k3s-gate/` §7.3 item 1 works unchanged on arm64.** k3s started on the read-only arm64 root with no new paths.
4. **The arm64 kernel already has the generic PCI watchdog driver.** The `i6300esb` reset path worked. On real Arm boards the driver is board-specific (the Pi uses `bcm2835-wdt`).

### 7.5 What an arm64 VM proves about a Raspberry Pi 5 (results against §5)

| Question | Answer from this spike |
|---|---|
| Does RAUC 1.15.2 (arm64) + our handler + the verity-only policy behave correctly on arm64? | **Yes** (T2, T3, T8, T11; same binary hash as the one the Pi kit builds from the same commit) |
| Does real k3s for arm64 pass and fail the fresh-signal gate correctly on a read-only arm64 root? | **Yes** (T1, T3, T4, T5, T10) |
| Do 3 tries, watchdog resets and power cuts end on a working slot on arm64? | **Yes, with GRUB** (T6–T9). A Pi 5 does not use GRUB: its firmware's `tryboot` is a **one-shot** flag, so the Pi path gets **one** trial boot, not three [C-LAB-rauc-1152-012]. T9's "power cut during the trial, retried on the next boot" does **not** carry over: on a Pi 5 that cut sends the box back to the old slot, and the gate's fell-back mode marks the update bad. That is safe, but the update is lost. This is a real behaviour difference [C-LAB-aarch64-gate-011] |
| Pi firmware, `autoboot.txt`, `reboot '0 tryboot'`, the FAT boot partition write | **Not tested here** (no emulator implements the Pi 5 firmware); covered only by the desk pre-flight [C-LAB-rauc-1152-017] and the founder test `../rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md` |
| Pi kernel | **Not tested.** The Pi 5 firmware loads `kernel_2712.img` by default, which uses a **16 KiB page size** [C-LAB-aarch64-gate-007]. This VM ran Debian's generic arm64 kernel with 4 KiB pages. Whether k3s, containerd and the air-gap images run on a 16 KiB-page kernel is not shown here |
| Real power loss, SD/NVMe behaviour, thermals | **Not tested** (QEMU SIGKILL keeps the host page cache; 60 MiB/s throttling is only a rough stand-in for SD speed) |

## 8. Deviations and problems (honest log)

1. **Primary environment unusable; fallback used beyond its stated trigger.** §4 named the host-HVF fallback "if `/dev/kvm` does not appear". `/dev/kvm` did appear, but nested KVM was erratic (runs 1–2, §7.1). Switching to HVF was decided after run 2, and results are reported only for the HVF runs. Runs 1–2 remain in `logs/`.
2. **Firmware.** §4 said the fallback uses "the same firmware file from inside the VM". That firmware (Debian AAVMF 2025.02-8+deb13u1) hung under host HVF (run 3). Runs 4–5 used Homebrew QEMU 11.1.3's bundled EDK2 (`edk2-stable202408`; hashes in `logs/firmware-host.sha256`). The root cause of the hang was not investigated (lab tooling, not on the OS update path).
3. **Driver fixes** (all in `scripts/CHANGES-vs-rauc-1152.md`): the T1 escape-fragment strip (after run 1); kill only our own QEMU on exit (after run 1, refined before run 4 so it can never hit another agent's QEMU); `LAB_WRITE_BPS` override (used only for diagnostic boot debug 5). No pass/fail criterion changed.
4. **Operator error** (§7.1, debug 1–5): a stray QEMU and a disk copied while in use. The corrupt-bbolt panic it caused is **not** a k3s or RAUC finding.
5. **Run-1 T1 root cause not proven.** I/O contention right after the build is the most likely explanation; debug 6–7 and runs 4–5 never reproduced the failure on an idle machine.
6. Not run: T12 (bundle-creation CVE check; already done on arm64 in `../rauc-1152/`).
7. Lab-only shortcuts as in `../rauc-k3s-gate/` (fixed machine-id, serial autologin, restricted user-net). They must not ship.

## 9. Founder-runnable follow-ups

| ID | Test | Why |
|---|---|---|
| A1 | On the Pi 5 kit from `../rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`, before anything else: `getconf PAGESIZE` (expect `16384` with `kernel_2712.img`), then `k3s check-config` and start k3s once. Record whether CoreDNS reaches Ready. **PASS:** k3s fresh-healthy on the 16 KiB kernel. **FAIL:** crash or a pod that never starts, then retry with `kernel=kernel8.img` in `config.txt` (4 KiB pages) and record both | The one arm64 difference this VM cannot cover cheaply |
| A2 | In the same Pi test, pull power during the trial gate (the Pi equivalent of T9) and record whether the update is lost (expected with one-shot `tryboot`) | Confirms the behaviour difference in §7.5 and tells us whether OneMind needs its own retry counter on the Pi |
| A3 | When an arm64 CI runner exists, rerun `scripts/run-tests.py` there with `LAB_ACCEL=kvm` (bare-metal KVM, not nested) | Makes this suite a CI regression test for both architectures |

## 10. What competitors do

| Product | Arm A/B mechanism | Kubernetes-aware gate? | Constraint fit for OneMind |
|---|---|---|---|
| Home Assistant OS (Pi 5) | RAUC + custom `tryboot` backend, one trial attempt [C-W3-029, C-LAB-rauc-1152-014] | No (Supervisor marks good) | **High** for the Pi boot backend; **low** for the gate (same reason as on x86) |
| Home Assistant OS (generic aarch64 / UEFI boards) | RAUC + GRUB | No | **High**: the same chain this spike tested |
| OneMind lab, this spike | RAUC 1.15.2 + GRUB arm64-efi, 3 tries + watchdog | Yes, fresh-signal gate | **Direct** for UEFI Arm boxes; the gate half carries over to the Pi 5 |

## 11. Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| L-A1 | Ship the health gate as one architecture-neutral component (the 9 files tested on x86_64 and arm64). Keep the boot backend per board family | R-1, R-3, M-6 |
| L-A2 | Set the production gate deadline per hardware tier from measured good-commit times, with ≥ 3× margin. Log wall-clock duration per check, so a slow box shows up as "slow", not as "broken" | R-1, R-2 |
| L-A3 | On the Pi 5, decide explicitly whether one-shot `tryboot` is acceptable or whether OneMind adds its own retry counter before re-arming `tryboot` (A2 decides) | R-1, R-2 |
| L-A4 | Run founder test A1 (16 KiB pages) before committing to the Pi 5 kernel flavour for the Lite tier | P-1, R-3 |
| L-A5 | CI: run this suite on bare-metal KVM or HVF, never on nested virtualization | M-6 |

## 12. How to re-run

```bash
LAB=<lab-dir>/aarch64-gate          # outside the repo
mkdir -p $LAB/{dl,logs,out} && cp -R research-output/evidence/lab/aarch64-gate/scripts $LAB/scripts
limactl create --name lab-a64 --tty=false --vm-type vz --cpus 10 --memory 16 --disk 80 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-a64
limactl shell lab-a64 -- sudo apt-get install -y mmdebstrap gdisk dosfstools mtools e2fsprogs squashfs-tools \
  openssl grub-common grub-efi-arm64-bin python3 curl zstd git file build-essential meson ninja-build pkgconf \
  libglib2.0-dev libssl-dev libjson-glib-dev libdbus-1-dev libfdisk-dev libcurl4-openssl-dev libnl-genl-3-dev
# k3s v1.37.2+k3s1: k3s-arm64, k3s-airgap-images-arm64.tar.zst, sha256sum-arm64.txt into $LAB/dl (inside the VM, with curl)
limactl shell lab-a64 -- sudo bash -c "OUT=/var/lab/a64-out bash $LAB/scripts/build-rauc.sh"
limactl shell lab-a64 -- sudo bash -c "OUT=/var/lab/a64-out DL=$LAB/dl bash $LAB/scripts/build.sh"      # T0, ~6 min
limactl shell lab-a64 -- sudo cp --sparse=always /var/lab/a64-out/disk.img $LAB/out/
limactl delete -f lab-a64                                         # keys die with the VM
# On the Mac (Homebrew qemu, native arm64 with HVF), each run from a fresh APFS clone:
cp -c $LAB/out/disk.img $LAB/run/disk.img
LAB_ACCEL=hvf LAB_CODE_FD=$(brew --prefix)/share/qemu/edk2-aarch64-code.fd \
  LAB_VARS_FD=$(brew --prefix)/share/qemu/edk2-arm-vars.fd \
  python3 -I $LAB/scripts/run-tests.py --disk $LAB/run/disk.img --log $LAB/logs/serial.log   # ~26 min
```

`run-tests.py` exits 0 only if every pass/fail test passes. `--upto T3` stops early. On exit it kills only the QEMU processes it started.

## 13. Files

- `scripts/`: `build-rauc.sh`, `build.sh`, `run-tests.py`, `debug-boot.py`, `trim-logs.sh`, `guest/`, `grub.cfg.generated` (as built), `CHANGES-vs-rauc-1152.md`; full diff in `scripts-vs-rauc-1152.diff`.
- `logs/`: build logs, driver verdicts and trimmed serial logs for runs 1–5, diagnostic boots debug 1–7, firmware hashes, version lists. Paths are masked as `<lab-dir>`; VM-internal addresses as `<vm-private-ip>`.
- `SHA256SUMS`, `versions.md`, `image-packages.txt`, `PREREGISTRATION.sha256`.
