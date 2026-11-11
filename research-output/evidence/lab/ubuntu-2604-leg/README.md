# Lab spike LAB-ubuntu-2604-leg: the RAUC + k3s gate battery on Ubuntu 26.04

**Status:** PRE-REGISTERED. Goal, hypotheses, design and pass/fail criteria were written 2026-11-11 07:11 UTC, before any build or test of this spike ran. Results are added below the line "Results" after the run. Nothing above that line is changed afterwards except typo fixes, and any change is logged in §9.

> **Explain it like I'm the founder.** We picked Debian over Ubuntu as the base OS by a whisker: the scores were a tie, and one of the tie-breakers was "Debian is the one our lab actually tested". The reviewer pointed out that this is unfair: Ubuntu never got a lab run, so of course it lost that row (critic gap N7). This spike gives Ubuntu 26.04 the exact same exam Debian passed: the same update tool (RAUC), the same "is Kubernetes really healthy on *this* boot?" check, the same broken updates, crashes, freezes and power cuts, run by the same test script. If Ubuntu passes too, that tie-break row becomes a draw and the decision rests on the other rows (mainly Canonical's redistribution rules). If Ubuntu fails, we learn exactly where it differs.

## 1. Goal

Run the battery from `../rauc-k3s-gate/` (T0–T10r) unchanged on an **Ubuntu 26.04 LTS ("resolute") amd64** root filesystem, so the S1 tie-break in `01-FOUNDATION-DECISION.md` §3.1.5 compares like with like (critic pass 2, N7 / Q-P2-2). Record every place where Ubuntu needs something different from Debian (kernel, initramfs, snapd, packaging, userland).

Two legs:

| Leg | Root filesystem | RAUC in the image | Runs | Purpose |
|---|---|---|---|---|
| **U1 (primary, like-for-like)** | Ubuntu 26.04 amd64 minbase | **v1.13 built from the upstream tag** (`v1.13` = `1183a39`), the same upstream version as the Debian run (Debian ships 1.13-3+deb13u1) | 2 full runs | The tie-break comparison |
| **U2 (secondary)** | Same as U1 | **Ubuntu's own `rauc` package** (1.15.1-1, universe [C-STEEL-ubu-008]) | 1 full run | What a real Ubuntu CI leg would ship; also a first look at RAUC 1.15.x (the Debian spike's F3) |

Everything else is identical to the Debian spike: the same gate scripts, RAUC pre-install handler, GRUB script, systemd units, manifests, k3s release (v1.37.2+k3s1, same hashes), disk layout, bundle-signing tool (the lab VM's RAUC 1.13), QEMU machine and test driver (`run-tests.py`).

## 2. Hypotheses

- **HU1 (portability)** The gate files under `scripts/guest/`, `run-tests.py` and `grub.cfg.in` need **zero changes** for Ubuntu (byte-identical, checked by `sha256sum` against `../rauc-k3s-gate/scripts/`). Only the bootstrap/package section of `build.sh` changes.
- **HU2 (same verdicts)** U1 gives the same verdicts as the Debian runs: T0–T9 and T10r PASS, and T10 (the naive gate) commits a broken system.
- **HU3 (RAUC 1.15.1)** U2 gives the same verdicts as U1. RAUC 1.13 and 1.15.1 use the same `grubenv` variables and handler order.
- **HU4 (Ubuntu differences are off the update path)** The Ubuntu-specific items below may need build changes, but none of them changes a test verdict:
  - kernel: Ubuntu's 7.0 kernel, where the `i6300esb` watchdog module may live in `linux-modules-extra` rather than the base modules package;
  - initramfs: Ubuntu may default to `dracut` instead of `initramfs-tools`; the build installs `initramfs-tools` explicitly so the boot path matches Debian, and records what the default would be;
  - snapd: a minbase bootstrap does not pull snapd, and nothing in the image needs it;
  - userland: Ubuntu 26.04 may ship Rust coreutils (uutils) as `coreutils`; the gate's shell scripts (`date`, `cut`, `stat`, …) must still work;
  - AppArmor: the Ubuntu kernel enables AppArmor by default; k3s's containerd must still start pods.

## 3. Pass / fail criteria (frozen before the run)

The test IDs, PASS and FAIL conditions, the 300 s gate deadline and the "no human input" rule are **exactly those of `../rauc-k3s-gate/README.md` §3** (T0–T10, T10r), applied to each run. T0 for this spike adds: the image's `/etc/os-release` says Ubuntu 26.04, and for U1 `rauc --version` in the image says 1.13; for U2 it says 1.15.1.

| ID | Spike-level criterion | PASS if | FAIL if |
|---|---|---|---|
| U1-PASS | Like-for-like leg | T0–T9 and T10r PASS in **both** U1 runs | Any pass/fail test FAILs in either run for a reason that is not a driver/harness bug (driver bugs are named and the run is repeated) |
| U2-PASS | Native RAUC leg | T0–T9 and T10r PASS in the U2 run | Any FAIL as above |
| HU1-CHECK | Portability | Gate files, driver and GRUB template byte-identical to the Debian spike | Any of them had to change (then the diff and reason are recorded, and the tie-break notes it) |
| T10 (both legs) | Observation | Expected: the naive gate commits a broken system, as on Debian | n/a (observation) |

Observations, not pass/fail: rootfs and slot-image size; boot-to-`COMMITTED-BOOT` time on T1; good-update commit time (T3); kernel version; which coreutils implementation is installed; whether `apparmor` is active and needed; what the initramfs generator would be without the explicit choice. Timing comparisons with Debian are reported, not judged: TCG emulation noise is large.

**What the result changes:** if U1-PASS, the S1 tie-break "Lab" row ("D: Nothing") must change to "both passed the same battery", and the tie-break is recounted without it. If U1 fails, the row stays and gains a concrete reason.

A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS.

## 4. Design

- **Host isolation:** as in the Debian spike. A disposable Lima VM (Debian 13 arm64, `vz`), whose only host mount is this spike's lab folder plus the Debian spike's lab folder **read-only** (for the verified k3s downloads), runs mmdebstrap, the RAUC build, image assembly and QEMU. The x86_64 guest runs under QEMU TCG with user-mode networking `restrict=on`; k3s is air-gapped.
- **Bootstrap:** `mmdebstrap --variant=minbase --arch=amd64 resolute` from `archive.ubuntu.com/ubuntu` (`main universe`, plus `resolute-updates` and `resolute-security`), signed by `ubuntu-archive-keyring.gpg` from Debian's `ubuntu-keyring` package. Package list = the Debian list with Ubuntu names: `linux-image-generic` replaced by the smallest Ubuntu kernel meta-package that boots the q35 guest (`linux-image-virtual`, adding `linux-modules-extra-*` only if `i6300esb` is missing), `initramfs-tools` explicitly.
- **RAUC v1.13 (U1):** built inside the amd64 chroot from a shallow clone of the `v1.13` tag (commit checked against `1183a39`) with meson, `-Dservice=true`, installed to `/usr` with its D-Bus service and systemd unit. Build dependencies are removed from the image afterwards. **RAUC 1.15.1 (U2):** `apt install rauc rauc-service` (or Ubuntu's equivalent package split) from universe.
- **Everything after the rootfs** (fstab with the 6 k3s bind mounts, `system.conf`, watchdog, network, serial autologin, k3s, gate, images, bundles, disk) is the Debian `build.sh` unchanged.

## 5. Requirement IDs served

R-1 (safe, user-controlled updates), R-2 (self-healing), R-3 (long-term maintainability), P-4 (OS image surface), P-7 (bring-your-own x86), M-6 (guard rails for a solo developer). Feeds S1 (base OS, `01-…` §3.1.5 tie-break), REC-DEC-17 (two CI legs, `FROM debian:trixie` and `FROM ubuntu:26.04`) and the Debian spike's F3 (RAUC 1.15.x).

## 6. Glossary

| Term | Meaning |
|---|---|
| Leg | One variant of the same test run on a different base (here: Ubuntu instead of Debian) |
| Like for like | Same tool versions, same scripts, same tests; only the thing being compared differs |
| minbase | The smallest bootstrap: only essential packages, no "recommended" extras such as snapd |
| mmdebstrap | The tool that builds a Debian or Ubuntu root filesystem from the package archive |
| universe | Ubuntu's community-maintained archive section; RAUC lives there, not in `main` (no Canonical security commitment without Ubuntu Pro) |
| snapd | Canonical's daemon for snap packages; installed by default on Ubuntu desktop/server, not needed here |
| dracut / initramfs-tools | Two tools that build the small boot-time filesystem (initramfs) that mounts the real root |
| uutils | A Rust rewrite of the basic shell commands (`ls`, `date`, `cut`, …) |
| AppArmor | A Linux security module Ubuntu enables by default; it restricts what programs may do |
| Tie-break | The rule in the frozen scorecard: when the top two are within 3 points, decision-critical evidence decides |

For slot, grubenv, try counter, trial boot, commit, health gate, fresh signal, stale-Ready trap, kubelet, watchdog, TCG and SIGKILL, see `../rauc-k3s-gate/README.md` §6.

---

## Results

### 9.0 Run log and deviations (written as they happened, before the affected runs)

- **07:15Z** T0 builds for U1 and U2 started in parallel; both finished `EXIT=0` (07:26Z, 07:23Z).
- **07:26Z** U1 run 1 and U2 run 1 started in parallel. Host contention was much higher than in the Debian run: three other lab VMs (other spikes) were running, and the host load average was 53 on 18 cores at 07:33Z.
- **07:33Z, D1 (driver bug, named):** T2 FAILed in both runs on `env_unchanged=False`, although the serial log shows the same `grubenv` before and after (`ORDER=A B A_OK=1 A_TRY=0 B_OK=0 B_TRY=0`). Cause: Ubuntu's systemd 259 wraps each shell prompt and command in OSC 3008 escape sequences that carry a fresh UUID. The driver strips only CSI sequences, so the two texts differed. Fix: a single regex change in `scripts/run-tests.py` (this spike's copy; the Debian original is untouched). Runs after 07:40Z use it. T2 of the runs before the fix is judged from the log, and the reason is stated.
- **07:34Z, D2 (real failure, not a driver bug):** U1 (RAUC 1.13) **failed T3**. Every bundle install stops with `Failed mounting bundle: Unexpected dm-verity status 'V -' (instead of '\0')`. U1 run 1 was stopped there, because every later test depends on installing a bundle. Per §3, **U1-PASS = FAIL**. Root cause: see §9.2.
- **07:40Z, D3 (added legs, decided before running them):**
  - **U2 run 2** uses the fixed driver, so U2 gets two full runs, like Debian.
  - **U1p** (one run, fixed driver): RAUC v1.13 plus the upstream fix `a45cdb14`, cherry-picked with the two preparatory commits it builds on from the same series (`abeccdc5`, `a40986fe`). All three touch `src/dm.c` only (+40/−15 lines). The fix alone did not apply (07:42Z).
- **07:48Z, D4 (timing control, added before it ran):** U2 run 1 committed T3 at **290 s**, against the frozen 300 s deadline; the Debian spike committed at 81 s. To tell host contention apart from an Ubuntu slowdown, the **Debian image is rebuilt in this VM** with the Debian spike's own `build.sh` and run `--upto T3` **under the same contention**, alongside the Ubuntu runs. This is an observation only. The deadline stays at 300 s for every verdict.
- **07:50Z, D5 (lab-VM disk full, harness):** The first U1p build and the first Debian control build failed because the lab VM's 80 GiB disk filled up (several 14 GiB images and 19 GiB build trees at once). Freed space by deleting the U1 artifacts (their hashes were already saved) and both build trees; builds now run one after another and delete their trees afterwards. U2 run 1 was in T4 during the full-disk window. Its serial log kept growing afterwards, and its verdicts are checked against the log like every other run.
- **08:20Z, D6 (D1's fix was incomplete, driver bug):** U1p run 1 and U2 run 2 (started 08:05Z with the D1 driver) again FAILed T2 on `env_unchanged`. The regex was right, but the driver strips each pipe read on its own, and the serial console delivers a few bytes per read, so a ~150-byte OSC sequence never arrives whole (short CSI sequences rarely split, which is why Debian never hit this). Fixed by carrying an unfinished escape sequence over to the next read (`TAIL` in `scripts/run-tests.py`), and tested by replaying the U2 run-2 log in random 1–40-byte chunks: 0 OSC sequences left, all prompts kept. The two runs continue: T3–T10r do not compare raw text, and T2 is judged from their logs. To get a driver-judged T2 for each leg, **short `--upto T2` runs** of U2 and U1p on fresh disk copies use the fixed driver. The Debian control (`--upto T3`) uses the Debian spike's original driver.
- **08:42Z, D7 (lab-VM out of memory, harness):** With five guests at once (about 4.4 GB resident each in a 16 GiB lab VM), the lab VM's kernel OOM-killed the QEMU of **U2 run 1** (08:14Z, during the T6 install, after T1 and T3–T5 had passed) and of **U2 run 2** (08:16Z, after T1 and T3 had passed). Their drivers waited on a dead guest. Both runs are **incomplete (harness)**, not failures, and their completed verdicts are kept. U1p run 1 was not affected. Two fresh full U2 runs (**U2 run 3, U2 run 4**, fixed driver, fresh disk copies) replace them, with at most two guests running at a time.
- **09:45Z, D8 (paired timing control, observation only, added before it ran):** At low load, Ubuntu committed T3 in 155–159 s (U1p run 1, U2 runs 2–3), against 80–81 s in the Debian spike and 89 s for the Debian control. Those Debian numbers come from other times and other loads. One **paired run** settles it: the Debian image (rebuilt with the Debian `build.sh`) and the U2 image, `--upto T3`, started at the same second, with no other guest in the lab VM.
- **10:30Z, D9 (paired-run result, and a third harness weakness):** Both paired runs passed T1 and T3 (timings in §9.5). The Ubuntu paired run's T2 again showed driver FAIL, although the log shows the same grubenv lines before and after, the signature refused and no marker. This time the escape sequences were stripped. The cause is that T2 compares the *whole* captured text, which also includes the terminal's echo of the typed command whenever that echo lands inside the capture window. That depends on timing, on any base (the original Debian driver has the same code). T2 is not the purpose of the paired run, and Ubuntu has four driver-judged T2 PASSes (both T2 checks, U2 runs 3 and 4), so the driver was not changed after the runs. The fix for future use is to compare only the parsed `KEY=VALUE` lines (§12 U-5). It separates "RAUC version" from "Ubuntu base". PASS criteria are the same as U1.

### 9.1 Verdict

**U1 (RAUC 1.13 on Ubuntu 26.04): FAIL.** It cannot install any bundle, because RAUC 1.13 does not understand Linux 7.0's dm-verity status line (§9.3) [C-LAB-ubuntu-2604-leg-010]. **U2 (Ubuntu's own RAUC 1.15.1): PASS.** T1–T9 and T10r passed in two complete runs (runs 3 and 4), plus every test that ran before the out-of-memory kills in runs 1 and 2 [C-LAB-ubuntu-2604-leg-011]. **U1p (RAUC 1.13 + the 3-commit upstream fix): PASS** in one complete run [C-LAB-ubuntu-2604-leg-012]. In every leg the naive gate (T10) committed a broken system, as on Debian. The gate itself needed **no change at all** (HU1, for the system under test). The test driver needed one fix for Ubuntu's console output, and that fix also removes a latent flake on Debian.

> **Explain the result like I'm the founder.** Ubuntu 26.04 passes the same safety exam as Debian, with one important catch. The exact RAUC version we tested on Debian (1.13) breaks on Ubuntu's newer Linux 7.0 kernel: it cannot open *any* update file. That's because Linux changed a one-line status message in version 6.19 and old RAUC reads it too strictly. Ubuntu's own RAUC (1.15.1) already has the fix, and with it Ubuntu passed every test: broken updates rolled back on their own, crashes and freezes were dropped after three tries, and pulling the virtual plug did no harm. The catch matters for **Debian too**. Debian's RAUC is the same old 1.13, so the day we put a newer kernel on a Debian box (a backports kernel, or new hardware that needs one), updates stop working unless we ship our own newer RAUC. The plan already says "RAUC 1.15.2 or later", and now we have a concrete, tested reason for that rule. For the Debian-vs-Ubuntu decision, this removes Debian's "only one we tested" advantage. The choice now rests on the other rows, mainly Canonical's redistribution rules.

### 9.2 Test results

Evidence: `logs/driver-*.log` (verdict lines) and `logs/serial-*-trimmed.log`. "h" = harness problem, named in §9.0. Times are TCG emulation of x86 on Arm, under varying host load.

| ID | U1 run 1 | U1p run 1 | U2 run 1 | U2 run 2 | U2 run 3 | U2 run 4 | Debian spike (runs 1, 2) |
|---|---|---|---|---|---|---|---|
| T0 build | PASS (RAUC 1.13) | PASS | PASS (RAUC 1.15.1) | (same build) | (same build) | (same build) | PASS |
| T1 first boot | PASS (k3s fresh 314 s, load 53) | PASS (119 s) | PASS (309 s, load 53) | PASS (139 s) | PASS (144 s) | PASS (114 s) | PASS (75 s) |
| T2 wrong key | refused, grubenv unchanged in log; driver FAIL (h, D1) | log: unchanged (h, D6); **T2-check run: PASS** | as U1 (h, D1) | as U1p (h, D6) | **PASS** | **PASS** | PASS |
| T3 good update | **FAIL**: `Unexpected dm-verity status 'V -'`, nothing installed | PASS, commit 155 s | PASS, commit **290 s** (deadline 300 s, load 53) | PASS, 159 s | PASS, 156 s | PASS, 123 s | PASS, 81 / 80 s |
| T4 k3s broken | not run (stopped, every install fails) | PASS (rollback ≈338 s after reboot) | PASS (≈399 s) | killed (h, D7) | PASS (≈345 s) | PASS (≈348 s) | PASS |
| T5 stale-Ready trap | not run | PASS | PASS | killed (h) | PASS | PASS | PASS |
| T6 kernel panic | not run | PASS (3 panics, 150 s) | killed during install (h, D7) | killed (h) | PASS (144 s) | PASS (157 s) | PASS (113 s) |
| T7 hang + watchdog | not run | PASS (3 resets, 234 s) | killed (h) | killed (h) | PASS (214 s) | PASS (237 s) | PASS (180 s) |
| T8 power cut mid-write | not run | PASS (cut at 47 %) | killed (h) | killed (h) | PASS (48 %) | PASS (47 %) | PASS |
| T9 power cut in commit window | not run | PASS (`B_TRY=2`, then commit) | killed (h) | killed (h) | PASS | PASS | PASS |
| T10 naive gate (obs.) | not run | **committed broken** (80 s) | killed (h) | killed (h) | **committed broken** (84 s) | **committed broken** (78 s) | committed broken (66 / 63 s) |
| T10r recovery | not run | PASS | killed (h) | killed (h) | PASS | PASS | PASS |

Spike-level criteria (§3): **U1-PASS: FAIL** (real, §9.3) · **U2-PASS: PASS** (runs 3 and 4: every pass/fail test PASS, driver exit 0; runs 1 and 2 incomplete for harness reasons with no failure) · **U1p: PASS** (one run, T2 from the T2-check run) · **HU1-CHECK: PASS for the system under test** (13 gate/GRUB/manifest files byte-identical; the generated `grub.cfg` hashes the same as Debian's), **with one driver change** (§9.0 D1/D6).

### 9.3 Why RAUC 1.13 fails on Ubuntu 26.04, and why this matters for Debian too

1. **What the kernel changed.** Linux commit `ae97648e` (2025-11-05, first in v6.19-rc1) added a second field to the dm-verity status line: the number of blocks repaired by forward error correction, or `-` when FEC is off. So a healthy device now reports `V -` instead of `V` [C-LAB-ubuntu-2604-leg-003].
2. **What RAUC 1.13 does.** After it sets up the verity device for a bundle, it compares the status to the exact string `V` and gives up otherwise (`src/dm.c` L229–L244 at `1183a39`). Every `rauc install` therefore fails *before touching any slot*. This is safe (nothing is written, the box stays on its slot), but no update can ever be installed. Our U1 console shows exactly this [C-LAB-ubuntu-2604-leg-003].
3. **The fix.** RAUC `a45cdb14` splits the status on spaces and checks only the first field. It builds on two refactors (`abeccdc5`, `a40986fe`), all in `src/dm.c`, +40/−15 lines. It was first released in **RAUC 1.15.1 (2026-01-05)**; 1.14 and 1.15 do not have it. With these three commits on top of 1.13 (U1p), the whole battery passes, so the dm-verity check was the *only* blocker.
4. **Debian.** Debian 13's `rauc 1.13-3+deb13u1` carries signature and OpenSSL patches but **not** this fix, and trixie-backports offers kernels up to 7.2.12. A Debian 13 box with a backports kernel ≥ 6.19 and Debian's RAUC would fail the same way. This is an inference from the code and package metadata; it was not run [C-LAB-ubuntu-2604-leg-004]. The Debian spike passed because trixie's own kernel is 6.12. Hardware that needs a newer kernel (new GPUs, NICs, Pi or x86 SoCs) is the realistic trigger.
5. **What this means.** OneMind cannot use either distribution's RAUC as is: Debian's is too old for new kernels, and Ubuntu's 1.15.1 sits in *universe*, below 01's ≥ 1.15.2 floor, with no Canonical security commitment without Ubuntu Pro. On either base, OneMind should **build and ship its own pinned RAUC package** (as HAOS does through Buildroot), and CI should boot the newest kernel the product may run.

### 9.4 Hypotheses

| | Verdict | Why |
|---|---|---|
| HU1 portability | **Confirmed for the OS side; driver needed one fix** | Gate, handler, units, manifests, bad-hang init, API stand-in and GRUB template: 13 files byte-identical (`SHA256SUMS`), and the generated `grub.cfg` hash equals the Debian one. Only the bootstrap section of the build changed. The test driver needed a fix (D1, D6) because Ubuntu's systemd 259 prints OSC 3008 escape sequences on the console [C-LAB-ubuntu-2604-leg-006, -007] |
| HU2 same verdicts with RAUC 1.13 | **Refuted** | U1 fails T3 onwards: RAUC 1.13 vs Linux 7.0 (§9.3). With the 3-commit fix (U1p), every verdict matches Debian |
| HU3 RAUC 1.15.1 same verdicts | **Confirmed** | U2 runs 3 and 4: all PASS; same `grubenv` variables, same handler order (T8: marker before `Marking target slot`, as on Debian) |
| HU4 Ubuntu differences off the update path | **Confirmed except the kernel/RAUC interaction** | uutils coreutils ran the gate scripts correctly; initramfs-tools works when named explicitly; the watchdog module is in the base modules; snapd and AppArmor are absent in minbase and not needed. The kernel *was* on the update path (§9.3) |

### 9.5 Ubuntu-specific differences found

| Area | What we saw on Ubuntu 26.04 | Debian 13 (same build) | Effect on OneMind |
|---|---|---|---|
| Kernel | 7.0.0-43-generic (`linux-image-virtual`) | 6.12.116 | Needs RAUC ≥ 1.15.1 (§9.3). Newer hardware support; faster kernel cadence means more such interface changes |
| RAUC packaging | 1.15.1-1 in **universe** [C-LAB-ubuntu-2604-leg-002] | 1.13-3+deb13u1 in main | Neither meets 01's ≥ 1.15.2; ship our own package on both |
| initramfs | Default is **dracut** (release notes); the kernel package Recommends `dracut \| linux-initramfs-tool` [C-LAB-ubuntu-2604-leg-001, -005] | initramfs-tools | Name the generator explicitly in the image recipe; a dracut image is a separate boot path to test |
| Core utilities | **uutils (Rust) coreutils** 0.10.0; `date --version` → `uutils coreutils` | GNU | The gate scripts worked unchanged. Keep the gate POSIX-simple, and run the CI leg on Ubuntu so a uutils incompatibility shows up early |
| systemd | 259; prints **OSC 3008** context markers around every prompt and command [C-LAB-ubuntu-2604-leg-007] | 257, none | Console-scraping tests (and serial-console support tools) must strip them |
| logind masked | `systemctl reboot` prints "Call to Reboot failed … login1" but reboots anyway (12 such messages in U2 run 3, from driver reboots and the gate's own rollback reboots; every one was followed by a boot, and the run passed; the final poweroff printed the same for PowerOff) [C-LAB-ubuntu-2604-leg-008] | silent | Do not mask logind in a product image; or reboot with `systemctl --force reboot` / `--no-wall` in tools |
| sudo, snapd, AppArmor | none installed by minbase; sudo-rs is the distro default [C-LAB-ubuntu-2604-leg-001] | none | A OneMind Ubuntu image would be "Ubuntu without snapd", like this lab. That is fine technically but is a *modified Ubuntu* for Canonical's policy [C-W2-050] |
| Size | rootfs 790 MiB (with k3s and air-gap images) | 678 MiB | +112 MiB per slot; irrelevant at 2 GiB slots |
| Timing | **Same speed.** In the paired run (D8: both images at the same second, no other guest), the gate started at the same second; k3s was fresh after 136 s (Debian) and 148 s (Ubuntu); the good update committed after **120 s (Debian) and 122 s (Ubuntu)**. The earlier 155–159 s Ubuntu commits were host load, not Ubuntu [C-LAB-ubuntu-2604-leg-013]. The `good` install took 102 s (Debian RAUC 1.13) against 143 s (Ubuntu RAUC 1.15.1), a single sample | | Set the gate deadline on hardware (Debian spike F1), per base |

### 9.6 What this changes in the S1 tie-break (`01-FOUNDATION-DECISION.md` §3.1.5)

- The **"Lab" row ("D: Nothing")** is no longer true. Both bases have now passed the same pre-registered battery with the same gate, given RAUC ≥ 1.15.1. The row should read **"both pass; neither passes with RAUC 1.13 on a ≥ 6.19 kernel"**. Following critic N7's own prescription, it is dropped from the tie-break. The remaining rows (G1 redistribution, proven competitor, DC-05 rebase precedent, DC-04 CRA route) still favour Debian, so **the tie-break verdict is unchanged, with one row fewer**. This file does not edit 01; the change is proposed for the next revision.
- A new **minor point for Ubuntu**: its archive already carries the RAUC version with the fix; Debian 13's does not (forky has 1.15.2). Since OneMind ships its own RAUC either way (§9.3 item 5), this is not scored.
- REC-DEC-17 (`FROM ubuntu:26.04` CI leg) is now **proven runnable**: this spike *is* that leg for the update path, at the cost of a 40-line bootstrap change.

## 10. Limits and founder-runnable tests

| Gap | Status |
|---|---|
| Real hardware, real power pulls | Same as the Debian spike (its F1, F2). Run them **on both bases** with the same `disk.img` recipe: build with `scripts/build-ubuntu.sh RAUC_MODE=archive` and with the Debian `build.sh`, then follow the Debian spike's F1/F2 steps for each. **PASS:** identical verdicts on both |
| RAUC 1.15.2 (01's floor) on Ubuntu | Not tested here; the `rauc-1152` spike covers 1.15.2 on Debian. To cover Ubuntu: build 1.15.2 from its tag with `RAUC_MODE=src RAUC_SRC=<v1.15.2 checkout>` and rerun `run-tests.py`. **PASS:** same as U2 |
| Debian 13 + backports kernel ≥ 6.19 + Debian RAUC 1.13 | **Inferred, not run** (§9.3 item 4). Founder test F-U1: in the Debian build, add `-t trixie-backports linux-image-amd64` and rerun `--upto T3`. **Expected:** T3 fails with `Unexpected dm-verity status 'V -'`. **If it passes, C-LAB-ubuntu-2604-leg-004 is wrong** |
| dracut instead of initramfs-tools on Ubuntu | Not tested (this lab kept Debian's boot path). F-U2: drop `initramfs-tools` from the package list, add `dracut` plus a `/etc/dracut.conf.d/` `add_drivers+=" i6300esb "` line, and rerun. **PASS:** same verdicts |
| Ubuntu's arm64 / Pi 5 flavor (`linux-raspi` 7.0) | Not tested; same dm-verity rule applies (any kernel ≥ 6.19 needs RAUC ≥ 1.15.1) |
| Timing under contention | Host load varied widely (other spikes' VMs). Verdicts use the frozen 300 s deadline; U2 run 1's T3 committed at 290 s at load 53. The deadline must be set on hardware |
| Lab-only shortcuts (fixed machine-id, serial autologin, masked logind, no network beyond restricted user-net) | Must not ship (as in the Debian spike) |

## 11. What competitors do

| Product | Base and update engine | RAUC version / kernel policy | Constraint fit for OneMind |
|---|---|---|---|
| Home Assistant OS | Buildroot + RAUC + GRUB/U-Boot, 3 tries [C-LAB-rauc-010] | Builds its own RAUC through its Buildroot fork: **RAUC 1.13** (plus a CVE-2026-34155 patch and one logging patch) on **kernel 6.18.62**, the 6.18 LTS line just below 6.19, at `ab7d0f1` (2026-11-10) [C-LAB-ubuntu-2604-leg-009]. HAOS is therefore not affected today, but must move to RAUC ≥ 1.15.1 before it takes any kernel ≥ 6.19 | **High** for "ship and pin your own RAUC, and move RAUC and the kernel together": the answer this spike reaches for both Debian and Ubuntu |
| umbrelOS 2.0 | Debian trixie + Rugix [C-W2-043] | Not RAUC | Medium (same Debian base; PolyForm-NC: patterns only) |
| Ubuntu Core 26 | Ubuntu 26.04 + snapd, transactional snaps [C-STEEL-ubu-012] | No RAUC; Canonical-controlled update path | Low: a snap-based device OS is a different model from our A/B images and k3s |
| Olares | Ubuntu/Debian host + k3s, no OS A/B [C-TD-olares-007] | n/a | None for OS update safety |
| **This spike** | Ubuntu 26.04 minbase + RAUC + the OneMind gate | 1.13 fails on Linux 7.0; 1.15.1 (Ubuntu archive) and 1.13 + fix pass | **Direct**: the REC-DEC-17 CI leg |

## 12. Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| U-1 | **Ship OneMind's own pinned RAUC package (≥ 1.15.2) on every base; never the distribution's.** Debian 13's 1.13 breaks on any kernel ≥ 6.19, and Ubuntu's 1.15.1 is in universe and below the floor. Track RAUC's `CHANGES` for kernel-interface fixes like `a45cdb14` | R-1, R-3, M-6 |
| U-2 | Add a CI gate: **boot the newest kernel the product may run** (backports / HWE / vendor kernel) and run at least T1–T3. Kernel interface changes reach the update path, not just drivers | R-1, R-3, P-4 |
| U-3 | Keep the REC-DEC-17 `FROM ubuntu:26.04` leg. It costs about 40 lines of bootstrap and the gate needs no change. Use `build-ubuntu.sh` as its seed | R-3, P-4, P-7 |
| U-4 | S1 tie-break: replace the "Lab" row with "both pass the same battery (RAUC ≥ 1.15.1)" and drop it from the count, as N7 asks; the verdict (Debian core) stands on the other rows. Propose in 01's next revision | R-3, M-6 |
| U-5 | Image recipes name the initramfs generator explicitly. Test-harness and support tools strip OSC sequences across read boundaries (systemd ≥ 258), and the shared driver's T2 compares parsed `grubenv` variables, not raw console text (D6, D9; this also removes a latent flake on Debian) | P-4, M-6 |
| U-6 | Do not mask `systemd-logind` in product images (systemd 259 reports a failed reboot call even when the reboot happens) | R-2, M-6 |

## 13. How to re-run

```bash
LAB=<lab-dir>/ubuntu-2604-leg                       # outside the repo
mkdir -p $LAB/logs $LAB/src $LAB/dl
cp -R research-output/evidence/lab/ubuntu-2604-leg/scripts $LAB/scripts
cp -R research-output/evidence/lab/rauc-k3s-gate/scripts $LAB/gate-scripts     # guest files, unchanged
git clone --depth 1 --branch v1.13 https://github.com/rauc/rauc.git $LAB/src/rauc-v1.13   # U1/U1p only; expect 1183a39
# U1p: cp -a rauc-v1.13 rauc-v1.13p; apply rauc commits abeccdc5, a40986fe, a45cdb14 (in that order)
# k3s v1.37.2+k3s1 files into $LAB/dl (hashes in SHA256SUMS)
limactl create --name lab-u2604 --tty=false --vm-type vz --cpus 10 --memory 16 --disk 80 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-u2604
limactl shell lab-u2604 -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf rauc \
  gdisk dosfstools mtools e2fsprogs squashfs-tools openssl grub-common python3 curl zstd ubuntu-keyring
# U2 (Ubuntu's RAUC); ~8 min. Use RAUC_MODE=src RAUC_SRC=$LAB/src/rauc-v1.13[p] for U1/U1p (~11 min)
limactl shell lab-u2604 -- sudo bash -c "W=/var/lab/w OUT=/var/lab/out DL=$LAB/dl G=$LAB/gate-scripts/guest RAUC_MODE=archive bash $LAB/scripts/build-ubuntu.sh"
limactl shell lab-u2604 -- sudo bash -c "rm -rf /var/lab/w; mkdir -p /var/lab/run && cp --sparse=always /var/lab/out/disk.img /var/lab/run/ && \
  python3 -I $LAB/scripts/run-tests.py --disk /var/lab/run/disk.img --log $LAB/logs/serial.log"     # T1–T10, ~60 min
bash research-output/evidence/lab/ubuntu-2604-leg/scripts/trim-logs-ubuntu.sh $LAB/logs/serial.log > serial-trimmed.log
limactl delete -f lab-u2604
```

**Resource rule learned the hard way (§9.0 D5, D7):** at most two guests per 16 GiB lab VM (each QEMU guest uses about 4.4 GB resident), and delete each build tree (about 19 GiB) after the build.

## 14. Files

- `scripts/build-ubuntu.sh`: the Ubuntu image and bundles. It reads the Debian spike's `scripts/guest/` unchanged. `scripts/run-tests.py`: the Debian driver plus the OSC/split-read fix (D1, D6). `scripts/trim-logs-ubuntu.sh`: strips OSC markers, then calls the Debian trim script.
- `logs/`: build logs (`build-u1`, `build-u1p`, `build-u2`, `build-deb-control`), driver verdicts and trimmed serial logs for every run (U1 run 1, U1p run 1 and its T2 check, U2 runs 1–4 and its T2 check, the Debian control and the paired timing run). VM-internal addresses are masked as `<vm-private-ip>` and host paths as `<lab-dir>`.
- `SHA256SUMS`, `versions.md`, `image-packages-{u1p,u2}.txt`, `ubuntu-observations-{u1,u1p,u2}.txt`: pins and hashes. The lab keys stayed inside the VM and were deleted with it.
