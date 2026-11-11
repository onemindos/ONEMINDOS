# Lab spike LAB-rauc-1152: the k3s health-gate suite on RAUC 1.15.2 with verity-only bundles

**Status:** COMPLETE: **PASS** (run 2 passed every pass/fail test; run 1 passed all but T11, a driver bug); Debian backport confirmed (H5 refuted); Pi 5 founder test written and desk-checked. Pre-registered: goal, hypotheses, design and pass/fail criteria were written 2026-11-11 07:12 UTC, before any build or test of this spike ran. The sha256 of this file at that moment is recorded in `../PREREGISTRATION.md`. Results are added below the line "Results" after the run; nothing above that line is changed afterwards except typo fixes and this status line, and any change is logged in the deviations section (§8).

> **Explain it like I'm the founder.** Our decision document says "use RAUC, but only version 1.15.2 or newer, and only the safer *verity* bundle format", because older RAUC had a 2026 security bug where a signature could end up covering only the first few bytes of a big update [C-DEC-004]. But every RAUC test we ran used Debian's older RAUC 1.13, because that is what Debian 13 ships. So the configuration we recommend was never actually tested. This spike builds RAUC 1.15.2 ourselves from the official source, puts it in the same test image, tells it to refuse anything that is not a verity bundle, and re-runs the full set of "break it on purpose" tests with real Kubernetes. It also checks whether Debian has quietly fixed the bug in its own 1.13 package. Finally, because our emulator cannot pretend to be a Raspberry Pi 5, it gives you an exact test to run on a real Pi 5.

## 1. Goal

1. Re-run the T0–T10 suite of `../rauc-k3s-gate/` (fresh-signal k3s gate, 3 GRUB tries, watchdog, power cuts) unchanged in logic, with **RAUC v1.15.2 built from the upstream tag** (tag object `f1ceebd68b4edcf681c23d6a49aa5322d483c4d9`, commit `4fb7c798d6ae412344fb8f8d310d773046af3441`, the newest tag on 2026-11-11) instead of Debian's 1.13 package, and with `bundle-formats=verity` in the device's `system.conf` (01 §4.2 item 2) [C-DEC-004, C-DEC-005].
2. Record which RAUC version Debian ships (trixie, trixie-backports, forky, sid) and whether the CVE-2026-34155 fix is in Debian's package, from the Debian security tracker and the package tracker (closes critic pass-2 N6).
3. Write a founder-runnable Raspberry Pi 5 `tryboot` + RAUC test (exact commands, pass/fail), because QEMU cannot emulate the Pi 5 firmware's `tryboot` (critic pass-2 N8).

## 2. Hypotheses

- **H1** RAUC 1.15.2 builds from the pinned tag with Debian 13's own libraries (no extra sources) for both amd64 (the test image) and arm64 (the build VM, for bundle creation), and drops into the image in place of the Debian package with no change to the gate scripts, the pre-install handler, the GRUB script or `system.conf` other than `bundle-formats`.
- **H2** Behaviour is the same as on 1.13: every T1–T10r result of `../rauc-k3s-gate/` repeats. In particular, the pre-install handler still runs before the slot is touched, and the handler can still read the version from the bundle manifest.
- **H3** With `bundle-formats=verity`, the device refuses a validly signed **plain**-format bundle before any handler runs (no trial marker, grubenv unchanged).
- **H4** The CVE fix is observable at bundle creation: RAUC 1.15.2 refuses to create a `plain` bundle whose payload is larger than 2 GiB, while Debian's 1.13 creates it. A verity bundle with the same payload is created by 1.15.2.
- **H5** Debian 13's `rauc` package (1.13-3+deb13u1) does **not** carry the CVE-2026-34155 fix (expectation; to be read off the security tracker, not tested by exploit).

## 3. Pass / fail criteria (frozen before the run)

Same starting state and rules as `../rauc-k3s-gate/` §3: the box starts on slot A, v1; "no human input" means no command between the install's `reboot` and the end state except defined power cuts; the gate deadline stays **300 s** per trial boot.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | One script inside a Lima VM builds RAUC from the pinned commit (the checked-out `HEAD` equals `4fb7c798…`) for arm64 and amd64, `rauc --version` prints `1.15.2` for both; builds `disk.img` and 8 bundles (`good` v2, `bad-k3s` v3, `bad-noagent` v4, `bad-boot` v5, `bad-hang` v6, `naive-noagent` v7, `wrong-key`, and `plain-good` v2 in **plain** format); k3s artifacts verified against `sha256sum-amd64.txt`; the 7 verity bundles report format `verity`; the Debian `rauc` package is **not** installed in the image | Any manual edit, hash mismatch, wrong commit, or Debian RAUC in the image |
| T1 | First boot | As before, plus `rauc --version` on the guest prints `1.15.2` | As before, or a different RAUC on the guest |
| T2 | Signature control | `wrong-key` refused, grubenv unchanged, no marker | Installs, or boot order changes |
| T3 | Good update | As in `../rauc-k3s-gate/` T3 | As there |
| T4 | Bad update: k3s broken | As there | As there |
| T5 | Stale-Ready trap | As there | As there |
| T6 | Kernel panic | As there (exactly 3 attempts, then fall back, A marked bad, not retried) | As there |
| T7 | Hang + watchdog | As there | As there |
| T8 | Power cut mid-write | As there | As there |
| T9 | Power cut in commit window | As there | As there |
| T10 / T10r | Naive gate (observation) / recovery | T10 observation only; T10r recovery commits | T10r does not commit |
| **T11** | Verity-only policy | `plain-good` (validly signed by the lab key, so `rauc info` on the build VM without a format policy verifies it) is refused on the device with a bundle-format error; grubenv unchanged; no trial marker written | Installs, starts writing, or writes a trial marker |
| **T12** | CVE regression at creation (build VM, arm64) | With one 2.1 GiB payload: RAUC 1.15.2 refuses `format=plain`, RAUC 1.15.2 creates `format=verity`, Debian 1.13 creates `format=plain` (control) | 1.15.2 creates the >2 GiB plain bundle (fix absent), or the control fails for an unrelated reason (then **BLOCKED**, not PASS) |
| **D1** | Debian status (desk check) | Recorded with source and access date; not pass/fail | n/a |

**Spike verdict:** PASS if T0–T9, T10r, T11 and T12 pass in at least one full run on one build; a second full run on a fresh copy of the same disk is the target and is reported either way. A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A run that fails because of a driver bug is kept in the logs and named as such.

## 4. Design

- **Reused unchanged from `../rauc-k3s-gate/scripts/`:** the gate (`onemind-health-gate`, `onemind-k3s-check`), the pre-install handler, units, manifests, `grub.cfg.in`, `bad-hang-init`, the API stand-in, the disk layout and the T1–T10 driver logic. Diff against the earlier scripts is in `scripts/CHANGES-vs-rauc-k3s-gate.md`.
- **RAUC build:** `git clone --depth 1 --branch v1.15.2` inside the Lima VM; abort unless `HEAD` is `4fb7c798…`. Meson with `-Dtests=false -Dhtmldocs=false -Dmanpages=false`, prefix `/usr`. arm64 build natively in the VM (used to create and inspect bundles); amd64 build in a separate amd64 `mmdebstrap` build chroot via qemu-user, then `meson install --destdir` into the image rootfs. The image gets RAUC's runtime libraries from Debian but not Debian's `rauc` / `rauc-service` packages.
- **system.conf:** as before, plus `bundle-formats=verity`.
- **Host isolation:** as before. Disposable Lima VM (Debian 13 arm64, `vz`), only host mount the lab work folder; x86_64 guest under QEMU TCG with user-mode networking `restrict=on`; k3s air-gapped. VM deleted at the end.
- **Pi 5:** desk-written founder test in `PI5-TRYBOOT-FOUNDER-TEST.md`, built on HAOS's Pi 5 tryboot backend [C-W3-029] and the Raspberry Pi firmware docs [C-W3-066].

## 5. Requirement IDs served

R-1 (safe updates), R-2 (self-healing), R-3 (maintainability), M-6 (guard rails for a solo developer), P-4 (OS image surface), P-7 (bring-your-own x86), and for the Pi 5 test P-1/Lite-tier hardware as listed in `../rauc-k3s-gate/` §5 and 01 §4.2. Feeds REC-DEC-05 and REC-DEC-07; closes critic pass-2 N6 and the founder-test part of N8.

## 6. Glossary

| Term | Meaning |
|---|---|
| RAUC 1.15.2 | The RAUC release (2026-03-27) that fixes CVE-2026-34155 |
| CVE-2026-34155 | A 2026 RAUC bug: for a "plain" bundle over 2 GiB, a number overflowed and the signature covered only the first few bytes of the update |
| Plain bundle | RAUC's older format: the signature covers the whole file, checked once before install |
| Verity bundle | RAUC's newer format: every block of the update is hash-checked as it is read, using the kernel's dm-verity |
| `bundle-formats` | A device setting that lists which bundle formats it accepts; `verity` means "refuse everything else" |
| Backport | A distribution copying a fix from a newer release into the older version it ships |
| Pinned tag / commit | A fixed, named point in the source history, so the build can be repeated exactly |
| tryboot | Raspberry Pi firmware feature: boot the other partition *once*; if not confirmed, the next reboot returns to the old one |
| Other terms | See `../rauc-k3s-gate/` §6 (slot, grubenv, try counter, health gate, fresh signal, stale-Ready trap, watchdog, TCG, SIGKILL) |

---

## Results

**Verdict: PASS (run 2).** Run 2 passed every pass/fail test (T0–T9, T10r, T11, T12) on one build: 56 min, 2026-11-11 08:47–09:44 UTC, from a fresh copy of the disk (sha256 `cdbde1ec…c60a`); run 1 took 55 min, 07:52–08:47 UTC. Run 1, on the same build, passed every test except T11. Its T11 FAIL is a **driver bug**, not a RAUC result: the raw log shows identical grubenv values before and after and no trial marker (deviation 4). T10, the naive gate, committed a broken system in both runs, as on 1.13. Two earlier attempts ran in parallel and were stopped because the VM was overloaded. They are kept as failed attempts (deviation 2). **D1 overturned an expectation: Debian 13 has backported the CVE fix** (H5 refuted). **A Pi 5 founder test is written**, and a desk pre-flight of its kit passed after it found and fixed one backend bug.

> **Explain the result like I'm the founder.** The exact RAUC configuration our decision document asks for is now tested: version 1.15.2, built from the official source, set to accept only the safer "verity" update files. It behaves the same as the older 1.13 in every test. Good updates are kept only after Kubernetes proves itself on the new boot. Broken ones roll back by themselves, and power cuts never brick the box. It also refuses an old-format update file even when that file is properly signed. Two surprises. First, **Debian already fixed the 2026 signature bug in its own RAUC 1.13** (June 2026), so "use Debian's RAUC" is no longer a security problem. The rule becomes "1.15.2 *or* Debian's patched 1.13-3+deb13u1 or later". Second, RAUC checks the whole signature of an old-format file before it refuses it. That is safe, but slow on big files. The Raspberry Pi 5 cannot be emulated, so there is now a step-by-step test for a real Pi 5 (about 3 hours). Its scripts were dry-run in a VM against the real Raspberry Pi OS image, and that dry run caught a bug before you would have hit it.

### 7.1 Test results

Evidence: `logs/serial-run{1,2}-trimmed.log`, driver verdicts in `logs/driver-run{1,2}.log`, build in `logs/build-rauc.log` and `logs/build-image.log`. All times are under QEMU TCG (x86 emulated on Arm), on a host shared with three other agents' lab VMs (host load average 27–39). That made boots about 2× slower than in `../rauc-k3s-gate/`.

| ID | Run 1 | Run 2 | What happened (run 1 unless noted) |
|---|---|---|---|
| T0 | **PASS** | (same build) | `build-rauc.log`: tag v1.15.2 checked out at `4fb7c798…`; `rauc v1.15.2` (arm64) and `rauc 1.15.2` (amd64). `build-image.log`: Debian `rauc` package absent from the image, all runtime libraries present, k3s `OK` against `sha256sum-amd64.txt`, 7 bundles `Bundle Format: verity` with "Verified inline signature", `plain-good` "Verified detached signature" / `Bundle Format: plain`, `wrong-key` rejected [C-LAB-rauc-1152-010] |
| T1 | **PASS** | **PASS** | `committed-boot A v1`; `K3S-FRESH ok after 200s` (run 2: 153 s; earlier spike 75 s); guest `rauc --version` = 1.15.2; `broken-app 0/1` |
| T2 | **PASS** | **PASS** | `LastError: signature verification failed: … unable to get local issuer certificate`; grubenv unchanged; no marker |
| T11 | FAIL (driver bug) | **PASS** | `LastError: Bundle format 'plain' not allowed`, rc=1, no trial marker. grubenv identical before and after (`ORDER=A B A_OK=1 A_TRY=0 B_OK=0 B_TRY=0`) in both runs. Run 1's driver compared text that held a split escape sequence (`logs/t11-driver-bug-raw-excerpts.txt`). The refusal took 22 s (run 1) and 51–66 s under heavier load, because the full plain signature is checked first [C-LAB-rauc-1152-008] |
| T3 | **PASS** | **PASS** | Trial on B: `no kubeconfig` ×2, then `CHECK pass 1/3, 2/3, 3/3` at 55/70/85 s, `APPS (excluded): broken-app 0/1 ErrImagePull`, `RESULT mark-good slot=B version=2 after 87s` (run 2: 122 s); the next reboot gives `committed-boot B v2` [C-LAB-rauc-1152-011] |
| T4 | **PASS** | **PASS** | k3s exits at start; `no kubeconfig` for 300 s → `RESULT mark-bad slot=A version=3` → reboot → `committed-boot B v2`, `K3S-FRESH ok after 93s` |
| T5 | **PASS** | **PASS** | Stale-Ready trap: API server up, `kubelet /healthz not answering` until 300 s → `mark-bad slot=A version=4` → back on B v2 |
| T6 | **PASS** | **PASS** | `BAD-BOOT` ×3 in 108 s (run 2: 152 s); GRUB `A_TRY=3 … default=2`; `RESULT fell-back … slot A (v5) marked bad, never retried`; not retried on the next boot |
| T7 | **PASS** | **PASS** | `BAD-HANG` ×3 in 203 s (run 2: 213 s; watchdog resets); same fall-back |
| T8 | **PASS** | **PASS** | Order on the console: `pre-install: trial marker slot=A version=2`, then `Marking target slot rootfs.0 as non-bootable`, then the cut at 48 %. Next boot: `fell-back slot=B`, marker cleared; reinstall `mark-good slot=A version=2 after 120s` |
| T9 | **PASS** | **PASS** | Killed after the first trial check on B; next boot `GRUB-RAUC: … B_OK=1 B_TRY=2`, `RESULT mark-good slot=B version=2 after 121s`, no reinstall |
| T10 (obs.) | **committed broken** | **committed broken** | Naive gate: passes at 61/74/88 s (run 2: 58/73/87 s), `RESULT mark-good slot=A version=7 after 90s` in both runs, with no kubelet [C-LAB-rauc-1152-011] |
| T10r | **PASS** | **PASS** | Reinstalling `good` from the broken-but-committed slot: `mark-good slot=B version=2 after 148s` |
| T12 | **PASS** | n/a (build VM) | See 7.3 |
| D1 | recorded | | See 7.3 |

Good-update commit times on 1.15.2 were 87–148 s across both runs against the 300 s deadline, about a 2× margin on a heavily loaded emulator. That is one more reason to set the production deadline from hardware timings (`../rauc-k3s-gate/` F1), not from emulation.

### 7.2 Hypotheses

| | Verdict | Why |
|---|---|---|
| H1 | **Confirmed** | RAUC 1.15.2 built from the pinned commit with Debian 13's libraries for arm64 (natively) and amd64 (qemu-user chroot). It replaced the Debian package with `guest/` byte-identical to `../rauc-k3s-gate/` (`scripts/CHANGES-vs-rauc-k3s-gate.md`). The only `system.conf` change was `bundle-formats=verity` |
| H2 | **Confirmed** | Every T1–T10r outcome of the 1.13 spike repeated (run 2 fully; run 1 except the driver-bug T11, which is new). The pre-install handler still ran before the slot was touched (T8 console order) and still read the version from the manifest (`trial marker slot=A version=2`) |
| H3 | **Confirmed** | T11: a validly signed plain bundle was refused with `Bundle format 'plain' not allowed`, with no marker and no grubenv change. Refinement: the refusal comes after RAUC has verified the plain bundle's whole detached signature [C-LAB-rauc-1152-008] |
| H4 | **Confirmed, and extended** | 1.15.2 refused to create the 2.1 GiB plain bundle; it created the verity bundle. The unfixed v1.15.1 control (added after pre-registration, deviation 3) created the plain bundle, and **1.15.2 and Debian's 1.13-3+deb13u1 both refuse to verify it** [C-LAB-rauc-1152-007] |
| H5 | **Refuted** | Debian's `rauc 1.13-3+deb13u1` (a non-maintainer upload dated 2026-06-28, accepted into proposed-updates 2026-07-04) carries both upstream fixes as patches. The security tracker lists trixie as **fixed** [C-LAB-rauc-1152-004, -005], and the lab shows the fix working (T12 control) |

### 7.3 Debian status (D1) and the CVE regression (T12)

| Debian release | rauc version | CVE-2026-34155 | Source |
|---|---|---|---|
| 13 trixie (stable) | 1.13-3+deb13u1 | **fixed** (backported patches; point release, not a DSA) | [C-LAB-rauc-1152-004, -005] |
| trixie-backports | none | n/a | [C-LAB-rauc-1152-006] |
| forky (testing), sid | 1.15.2-1 | fixed | [C-LAB-rauc-1152-004] |
| 12 bookworm (oldstable) | 1.8-2 | **vulnerable**, `<no-dsa>` (minor issue) | [C-LAB-rauc-1152-004] |
| 11 bullseye | (n/a in table) | `<postponed>` | [C-LAB-rauc-1152-004] |

T12, one 2.1 GiB incompressible payload (`logs/build-rauc.log`, `logs/t12-control.log`):

| Build | `format=plain` create | `format=verity` create | Verify the v1.15.1 plain bundle |
|---|---|---|---|
| Upstream 1.15.2 (`4fb7c798`) | **refused**: "exceeds maximum for bundles using plain format (2 GiB)" | created (2,272,204,851 bytes) | **refused** (same message) |
| Debian 1.13-3+deb13u1 | **refused** (same message) | not tried | **refused** (same message) |
| Upstream 1.15.1 (`fac72b83`, unfixed control) | **created** (2,254,444,227 bytes) | not tried | n/a |

What this means for 01 §4.2 item 2: the condition "RAUC ≥ 1.15.2 or a confirmed Debian backport" is **met by Debian 13's own package today**. Two refinements follow. (a) Pin the floor as "upstream ≥ 1.15.2, or Debian ≥ 1.13-3+deb13u1". A box that has not taken the June 2026 point release is still vulnerable. (b) Keep `bundle-formats=verity` anyway: it refuses plain bundles even on an unfixed RAUC, because the format is decided by the signature type, not by attacker-controlled content [C-LAB-rauc-1152-003, -008]. Bookworm-based products (Debian 12) remain vulnerable without a DSA.

### 7.4 Pi 5 founder test and its desk pre-flight

`PI5-TRYBOOT-FOUNDER-TEST.md` gives the commands, the A/B layout (Raspberry Pi's documented partition-level `autoboot.txt` + `tryboot_a_b` [C-LAB-rauc-1152-013]), and 13 pass/fail steps, including power pulls during the write, during the trial and during the commit. Status: **blocked: founder-hardware**. The kit is `scripts/pi5/`: `build-rauc-pi.sh`, `prepare-disk.sh`, the RAUC custom backend `rpi-tryboot-ab.sh`, the Pi gate variant, units and `onemind-status`.

Desk pre-flight in the arm64 VM (`logs/pi5-preflight-run2.log`, `-run6.log`; [C-LAB-rauc-1152-017]):

| Step | Result |
|---|---|
| P-a `build-rauc-pi.sh` | `rauc v1.15.2`, same binary sha256 as the arm64 build in T0 |
| P-b `prepare-disk.sh` on the real Raspberry Pi OS Lite 2026-10-06 tree, a loop device as the SSD | 7-partition MBR layout; 7 verity + 1 plain bundles; `wrong-key` rejected; `autoboot.txt` = A committed. Took about 25 min under load |
| P-c Device policy (RAUC inside slot A with its own `system.conf`) | `good` accepted; `plain-good` refused `Bundle format 'plain' not allowed`; `wrong-key` refused |
| P-d Real `rauc install good.raucb` from slot A (desk-only `-Dservice=false` build of the same commit, deviation 6) | Boot B (50 files, `cmdline_b.txt` → root partition 6, `rauc.slot=B`) and root B (v2) written; marker `B 2`; `/run/systemd/reboot-param` = `0 tryboot`; `autoboot.txt` unchanged |
| P-e Backend state machine with a faked device tree | A tryboot boot from partition 3 commits B (autoboot swap). A normal boot keeps B. A commit of A without tryboot is refused (rc 1). Marking A bad removes its marker |
| Bugs found and fixed | (1) The backend printed "armed" and exited 0 when `/run/systemd` was missing, so RAUC would record an activation that never arms tryboot. It now creates the directory and fails loudly. (2) `prepare-disk.sh` left the target mounted. (3) The Raspberry Pi OS first-boot `resize` flag would have been copied into both slots' command lines. All fixed in the kit. (3) was verified on a string only, because the pre-flight disk was built before the fix |

What the pre-flight cannot show is the subject of the founder test: the firmware's tryboot itself, the Pi watchdog, kernel panics, real power loss, and the **one-chance** behaviour. On x86 a power cut during the first trial boot is retried (T9). On Pi 5 the docs say it falls back [C-LAB-rauc-1152-012], so the update is abandoned and must be reinstalled (F-P11a). HAOS handles this by dropping the missed tryboot and marking the slot bad [C-LAB-rauc-1152-014]. `boot_count` cannot replace a try counter, because it is cleared on power loss [C-LAB-rauc-1152-015].

### 7.5 What this changes in 01

1. **REC-DEC-05 condition (RAUC version):** satisfied by Debian 13's own `rauc 1.13-3+deb13u1` (backport confirmed from the source package) **and** by upstream 1.15.2, which is now lab-proven with the real k3s gate. Recommend shipping **upstream RAUC built from a pinned tag** anyway. Debian 13 will not move past 1.13, and 01's "track the latest RAUC within 30 days" rule cannot be met from Debian stable. This lab shows that the build is simple (one meson call, Debian's libraries only).
2. **`bundle-formats=verity`** works as specified and should stay. It is defense in depth, not the fix: plain bundles are hashed in full before the refusal.
3. **Pi 5:** the update engine path is ready for hardware. Add F-PI5 to `22-HARDWARE-LAB-TEST-PLAN.md`. Until it passes, the Pi 5 tier is "designed, desk-checked, not proven". Plan for **one** trial boot per update on Pi 5 (abandon and re-offer, or a software re-arm, as for the x86 `efi` backend).

## 8. Deviations and problems (honest log)

1. **Status line.** The status line above "Results" was updated from PRE-REGISTERED to the final verdict after the runs. Nothing else above the line was changed after the hash in `../PREREGISTRATION.md` was taken.
2. **Parallel attempts stopped (environment, my scheduling).** Two full runs were first started in parallel while the Pi pre-flight was also building bundles, with VM load around 15 on 12 vCPUs. Both T1s failed (`K3S-FRESH ALERT not healthy after 300s … core pod kube-system/coredns not Ready`). Both runs were stopped after T2/T11, and their logs are kept as `logs/*parallel*-aborted*`. The suite was then run twice sequentially, as `../rauc-k3s-gate/` did. In the sequential runs, T1 passed at 200 s and 153 s. The host also carried three other agents' lab VMs throughout (host load 27–39), which explains why even the sequential runs were about 2× slower than the earlier spike. No criterion or deadline was changed.
3. **T12 control added after pre-registration.** H5 expected Debian's 1.13 to be the vulnerable control. It is patched, so it could not serve as one. The unfixed upstream v1.15.1 (`fac72b83`) was added as the control (`scripts/t12-control.sh`). The pre-registered T12 criteria for 1.15.2 are unchanged, and the Debian line is reported as refused.
4. **Driver bug in grubenv comparison (T11, run 1 and parallel attempt 2).** A terminal escape sequence (`ESC[?2004l`, bracketed paste off) split across two serial reads was not stripped. It was glued to the `ORDER=` line, so the before/after comparison failed while the values were identical (`logs/t11-driver-bug-raw-excerpts.txt`). The first fix (compare only `KEY=VALUE` lines) was not enough. The second also strips escape fragments and was tested on the run-1 log before run 2. Run 1's T11 stays FAIL in the table.
5. **Version string.** The git-built binary prints `rauc v1.15.2`, the chroot-built one `rauc 1.15.2`. The checks accept both. This does not change what T0/T1 test.
6. **Pi pre-flight only:** `rauc install` in a service build needs the D-Bus daemon, and `--override-boot-slot` exists only in `-Dservice=false` builds [C-LAB-rauc-1152-009]. So P-d used a `-Dservice=false` build of the same commit, run from tmpfs inside the chroot. The kit itself uses the normal service build. The pre-flight also needed four attempts: run 1 was broken by my editing `prepare-disk.sh` while bash was reading it; runs 3–5 fixed wrapper problems (a missing `partprobe`, an option order) and then the backend bug. All logs are kept.
7. **Runtime package list bug in `build-rauc.sh`** (merged-/usr paths from `ldd` unknown to `dpkg -S`). Fixed and regenerated before the image build. The build log shows the corrected list.
8. **Disk space.** The first sequential start failed with "No space left on device" (the Pi target image). Build intermediates were deleted and the run restarted. No test had started.

## 9. Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| L-1 | Ship RAUC **built from a pinned upstream tag** (today v1.15.2, `4fb7c798`), not Debian stable's package, so the 30-day "track latest" rule in 01 can be met. Keep Debian's runtime libraries. Record the build as in `scripts/build-rauc.sh`. Floor: upstream ≥ 1.15.2 **or** Debian ≥ 1.13-3+deb13u1 | R-1, R-3, M-6 |
| L-2 | Keep `bundle-formats=verity`. Add an image test that a signed plain bundle is refused (T11), and treat the policy as defense in depth, not as the CVE fix | R-1, AI-4 |
| L-3 | Update 01 §4.2 item 2 and the critic N6 row: the backport exists (trixie fixed in 1.13-3+deb13u1); bookworm remains vulnerable, so never base a product on Debian 12 + its RAUC | R-1, R-3 |
| L-4 | Run F-PI5 (`PI5-TRYBOOT-FOUNDER-TEST.md`) before claiming the Pi 5 tier. Design the update service for **one trial boot on Pi 5**: either re-offer an abandoned update, or prototype a gate re-arm with a bounded counter on `data` | R-1, R-2, P-1 |
| L-5 | Use the vendor-documented partition-level A/B (`autoboot.txt`, `tryboot_a_b=1`) on Pi 5 rather than HAOS's `os_prefix` folders. It keeps whole boot partitions per slot, matching the x86 layout's "slot = boot + root" model. Measure the FAT commit write under power loss (F-P11c) before relying on it | R-1, P-4 |
| L-6 | A custom backend must never report success it did not achieve. Add the pre-flight checks (P-c to P-e) to CI for every board backend | M-6, R-3 |

## 10. What competitors do

| Product | RAUC version source | Bundle format policy | Constraint fit for OneMind |
|---|---|---|---|
| Home Assistant OS | Buildroot package, pinned per HAOS release (not re-verified here) | Not verified here | High for the mechanism; HAOS builds RAUC itself, which supports L-1 |
| Debian-based appliance on stock Debian 13 | 1.13-3+deb13u1 (CVE-patched) [C-LAB-rauc-1152-005] | Configurable, the same option | Medium: patched, but cannot follow upstream releases |
| Debian 12 based appliance | 1.8-2, vulnerable, no DSA [C-LAB-rauc-1152-004] | n/a | **None**: do not use |
| OneMind (this lab) | Upstream 1.15.2 from a pinned tag, Debian 13 libraries | `bundle-formats=verity` | Direct: this is 01's configuration, now lab-tested |

## 11. How to re-run

```bash
LAB=<lab-dir>/rauc-1152                      # outside the repo
mkdir -p $LAB/logs $LAB/dl && cp -R research-output/evidence/lab/rauc-1152/scripts $LAB/scripts
limactl create --name lab-r1152 --tty=false --vm-type vz --cpus 12 --memory 24 --disk 100 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-r1152
limactl shell lab-r1152 -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf rauc gdisk dosfstools \
  mtools e2fsprogs squashfs-tools openssl grub-common python3 curl zstd git build-essential meson ninja-build pkgconf \
  libglib2.0-dev libssl-dev libjson-glib-dev libdbus-1-dev libfdisk-dev libcurl4-openssl-dev libnl-genl-3-dev
# k3s v1.37.2+k3s1 amd64 files into $LAB/dl (see ../rauc-k3s-gate/ §12)
limactl shell lab-r1152 -- sudo bash -c "OUT=/var/lab/r1152-out bash $LAB/scripts/build-rauc.sh"        # RAUC + T12, ~4 min
limactl shell lab-r1152 -- sudo bash $LAB/scripts/t12-control.sh                                        # unfixed control
limactl shell lab-r1152 -- sudo bash -c "OUT=/var/lab/r1152-out DL=$LAB/dl bash $LAB/scripts/build.sh"  # T0, ~9 min
limactl shell lab-r1152 -- sudo bash -c "mkdir -p /var/lab/run && cp --sparse=always /var/lab/r1152-out/disk.img /var/lab/run/ && \
  python3 -I $LAB/scripts/run-tests.py --disk /var/lab/run/disk.img --log $LAB/logs/serial.log"         # T1-T11, ~55 min; run ALONE
# Pi kit desk pre-flight (needs the Raspberry Pi OS Lite image, sha256 in versions.md, extracted to /var/lab/pi/img):
limactl shell lab-r1152 -- sudo bash -c "IMG=/var/lab/pi/img bash $LAB/scripts/pi5/desk-preflight.sh"
limactl delete -f lab-r1152
```

## 12. Files

- `scripts/`: `build-rauc.sh` (RAUC from the tag + T12), `t12-control.sh`, `build.sh` (image and 8 bundles), `run-tests.py` (driver, stdlib, run with `-I`), `trim-logs.sh`, `guest/` (unchanged from `../rauc-k3s-gate/`), `pi5/` (founder kit and desk pre-flight), `CHANGES-vs-rauc-k3s-gate.md`.
- `logs/`: build, T12, versions, driver verdicts, trimmed and masked serial logs for both runs and both stopped parallel attempts, the T11 raw excerpts, and the Pi pre-flight logs.
- `SHA256SUMS`, `versions.md`, `image-packages.txt`: pins and hashes. Lab keys stayed in the VM and were deleted with it.
- `PI5-TRYBOOT-FOUNDER-TEST.md`: the founder test.
