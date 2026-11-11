# Lab spike LAB-mender: Mender (standalone) A/B with the same k3s health gate as RAUC

**Status:** PRE-REGISTERED. Goal, hypotheses, design and pass/fail criteria were written 2026-11-11 07:15 UTC, before any build or test of this spike ran. The README's sha256 at that moment is recorded in `../PREREGISTRATION.md`. Results are added below the line "Results" after the run; nothing above that line is changed afterwards except typo fixes, and any change is logged in §9.

> **Explain it like I'm the founder.** We picked RAUC over Mender partly because RAUC had passed our lab tests and Mender had never been tested. That is not a fair fight. This spike gives Mender the exact same exam: the same Debian 13 system, the same Kubernetes (k3s), the same "is this new version really healthy *on this boot*?" check, the same broken versions and the same power cuts. Mender runs the way a OneMind box would run it without Mender's paid or hosted server: the device updates itself from a file ("standalone mode"). Whatever the result, the RAUC-vs-Mender choice (S2 in `01-FOUNDATION-DECISION.md`) can then be made on equal evidence.

## 1. Goal

Run the test battery of `../rauc-k3s-gate/` (T0–T10, same IDs, same deadline, same broken variants) with **Mender's open-source client in standalone mode** instead of RAUC, on **Debian 13 x86_64 in QEMU**, so the S2 tie-break compares like with like (critic pass 2, gap N7; Mender steelman experiment E2). Everything that is not the update engine stays the same as in `../rauc-k3s-gate/`: rootfs package set, k3s release and flags, read-only root with k3s state bind-mounted from `/data`, the fresh-signal check script (`onemind-k3s-check`, unchanged), core pods, the broken app, the API stand-in, the watchdog and the QEMU machine.

## 2. Hypotheses

Code references are to `mendersoftware/mender@0f4eb08` (tag 5.2.0), `mendersoftware/grub-mender-grubenv@d7c3ec2` (the commit mender-convert 5.3.0 pins in `configs/mender_grub_config`) and `mendersoftware/mender-convert@85e8c50` (tag 5.3.0).

- **H1 (no engine changes needed).** Mender's Debian client package (newest `mender-update` in Mender's `debian/trixie/stable` repository on build day; expected 5.2.0), Mender's GRUB integration at d7c3ec2 with its boot logic unmodified, one `ArtifactCommit_Enter` state script holding the gate, and one systemd unit that calls `mender-update commit` or `mender-update rollback` implement 01's gate. No Mender code is changed.
- **H2 (no trial marker needed).** Unlike RAUC, Mender does not need a OneMind trial marker. The `rootfs-image` module writes the whole inactive partition in `DownloadWithFileSizes` and only then, in `ArtifactInstall`, sets `mender_boot_part`, `upgrade_available=1` and `bootcount=0` [mender@0f4eb08 `support/modules/rootfs-image` L176–L228]. So there is no window in which a power cut boots a new, ungated slot, and `upgrade_available=1` is itself the trial signal.
- **H3 (stale-Ready trap is engine-independent).** With a naive gate (API status only), Mender also commits a k3s whose kubelet never starts (`--disable-agent`), as RAUC [C-LAB-rauc-k3s-gate-008] and Rugix [C-LAB-debian-rugix-023] did. The fresh-signal gate rejects it.
- **H4 (one trial boot; predicted difference).** Mender's stock GRUB logic allows **exactly one** trial boot: `bootcount` may only be 0 or 1, and any boot with `upgrade_available=1` and `bootcount≠0` rolls back [grub-mender-grubenv@d7c3ec2 `04_mender_setup_env_functions_grub.cfg` L98–L100, L139–L159]. Prediction: T6 and T7 fall back after **1** attempt (RAUC: 3), and **T9 fails** its criterion: a power cut during the first boot of a good update abandons that update (the box stays safe on the old version, but the update must be reinstalled). This is the same result as the 1-try RAUC lab [C-LAB-rauc-018], and it conflicts with 01 §4.2 item 3 (3 boot tries).
- **H5 (watchdog).** A hung trial boot is turned into a failed try by the watchdog, and Mender's bootloader logic returns to the old slot with no human action.
- **H6 (signatures before writes).** An artifact signed with a key not in `ArtifactVerifyKeys` is refused before anything is written or the bootloader environment changes.

## 3. Pass / fail criteria (frozen before the run)

Identical to `../rauc-k3s-gate/` §3 except where Mender has no equivalent concept; every difference is marked **(M)** and explained. The box starts on slot A (partition 2), version 1. "No human input" means the driver sends no command between the install's `reboot` and the end state, except where a test is defined as a power cut. Gate deadline: **300 s** per trial boot (same value as RAUC).

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | One script inside a Lima VM builds `disk.img` and 7 Mender artifacts (`good` v2, `bad-k3s` v3, `bad-noagent` v4, `bad-boot` v5, `bad-hang` v6, `naive-noagent` v7, `wrong-key`); k3s artifacts verified against the release's `sha256sum-amd64.txt`; the Mender client package comes from Mender's signed APT repository (key fingerprint checked, as mender-convert does); `mender-artifact read` verifies the 6 signed artifacts with the lab public key and rejects `wrong-key` | Manual edits, or a hash/fingerprint mismatch |
| T1 | First boot | Slot A v1 boots, gate logs `RESULT committed-boot`, k3s passes the fresh check, the broken app is visibly not Ready | No boot, or k3s never passes the fresh check on a clean install |
| T2 | Signature control | `wrong-key` refused with a signature/verification error; bootloader env unchanged; **(M)** no update left in progress (instead of RAUC's "no trial marker written") | Installs, env changes, or an update is left in progress |
| T3 | Good update | `good` (v2) to B; the gate (run by `mender-update commit` as the `ArtifactCommit_Enter` state script) logs ≥ 3 consecutive fresh passes, then `RESULT mark-good`; at commit time the `apps` pod is not Ready; a further reboot stays on B v2 (`committed-boot`) | Commit without the fresh checks, or ends anywhere but B v2 committed |
| T4 | Bad update: k3s broken | `bad-k3s` (v3) to A; gate logs `RESULT mark-bad` within deadline + 60 s, Mender rolls back, the unit reboots; box ends on B v2, k3s fresh-healthy, **(M)** env `mender_boot_part=3 upgrade_available=0` (Mender has no per-slot "bad" flag; the failed slot is simply never selected) | Commits v3, stays on v3, or needs input |
| T5 | Stale-Ready trap | `bad-noagent` (v4) to A with the fresh gate: ends on B v2, as T4 | Commits v4 |
| T6 | Unbootable (kernel panic) | `bad-boot` (v5) to A: the box returns to B v2 with no input; the gate on B logs `RESULT fell-back` and cleans up Mender's in-progress update; A is not tried again on the next reboot. **(M)** Attempts on A are recorded, not required to be 3: H4 predicts 1 | Boot loop, A tried again, or the box needs input |
| T7 | Hang + watchdog | `bad-hang` (v6) to A: watchdog reset(s), then B v2 with no input; A not tried again. **(M)** Attempts recorded (H4 predicts 1) | Box stays hung, or A tried again |
| T8 | Power cut mid-write | `SIGKILL` QEMU while `mender-update install good` is writing partition A (kill ≥ 5 s after the install started streaming and before it prints its result). Next boot: B v2 with no input; env unchanged (`mender_boot_part=3 upgrade_available=0`); after the gate's clean-up, a reinstall commits A v2 | No boot, a half-written slot boots, or the reinstall fails |
| T9 | Power cut in commit window | Install `good` to B, reboot, `SIGKILL` after the gate has started its trial on B but before `RESULT`. **Same criterion as RAUC:** the next boot retries B and commits B v2 without a reinstall. **H4 predicts FAIL.** Also recorded: **T9s (safety, pass/fail):** the box ends on a committed, k3s-healthy slot with no input | T9: the update is abandoned. T9s: the box does not end on a working slot |
| T10 | Naive gate (observation) | `naive-noagent` (v7, freshness off). Expectation: it commits a broken system. The driver then installs `good` from that system; that recovery must commit (**T10r**, pass/fail) | T10r: recovery does not commit |

A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. Two full runs are the target; a run that fails because of a driver bug is kept in the logs and named as such. **Overall verdict:** PASS if every pass/fail test except T9 passes and T9 behaves as H4 predicts, reported as "PASS with the predicted one-try limitation"; any other T9 outcome is reported as observed.

## 4. Design

- **Host isolation:** as `../rauc-k3s-gate/`: a disposable Lima VM (Debian 13 arm64, `vz`) whose only host mount is the lab work folder; the x86_64 guest runs under QEMU TCG inside it with user-mode networking `restrict=on`. k3s is air-gapped from its bundled image tarball. Docker is not needed (mender-convert is not used; see below).
- **Disk (GPT, 14 GiB):** ESP 128 MiB (partition 1) · rootfs-A 2 GiB (2) · rootfs-B 2 GiB (3) · data (4, rest). Same as the RAUC build. Artifacts are on `/data`.
- **Mender components:** `mender-update` (and its dependencies) from `https://downloads.mender.io/repos/device-components` suite `debian/trixie/stable`, signing key fingerprint `E6C857345575F9218396566224072B80A1B29B00` checked (mender-convert 5.3.0 `configs/mender_convert_config` L231–L237). `mender-auth` and any server add-ons are not enabled: standalone mode, no server. `mender-artifact` (the artifact tool) runs in the Lima VM.
- **Bootloader:** GRUB EFI built from Debian's `grub-efi-amd64-bin` (as in RAUC), loading Mender's standalone `mender_grub.cfg` compiled by grub-mender-grubenv@d7c3ec2's `make` (`install-standalone-boot-files`, the path mender-convert uses for non-grub.d images), with `mender_grubenv_defines` for this disk (rootfs parts 2/3, PARTUUIDs, `vmlinuz`/`initrd.img`) and a `11_bootargs_grub.cfg` giving the same kernel arguments as RAUC (`console=ttyS0,115200 panic=5 rootwait loglevel=4`; no `rw`, so the root is read-only). Lab-only addition: one `echo` line printing Mender's env at boot (`MENDER-GRUB: ...`); it changes no variable. The env lives as two redundant copies on the ESP (`/boot/efi/grub-mender-grubenv/`), read and written in Linux with `grub-mender-grubenv-print/-set`.
- **Client config:** `/etc/mender/mender.conf` with `RootfsPartA=/dev/disk/by-partlabel/rootfs-A`, `RootfsPartB=…-B`, `ArtifactVerifyKeys=[lab public key]`, `StateScriptTimeoutSeconds=600`, `DeviceType=onemind-lab-x86_64`. `/var/lib/mender` is a symlink to `/data/mender` (mender-convert's layout), so the client database survives slot switches.
- **Gate (same logic and thresholds as RAUC):** the trial logic (3 fresh passes 10 s apart, 300 s deadline, apps excluded, `onemind-k3s-check` unchanged) is the rootfs state script `/etc/mender/scripts/ArtifactCommit_Enter_00_onemind-gate`, so it ships in, and is versioned with, the new OS. A systemd oneshot `onemind-health-gate` (ordered like RAUC's: after the API stand-in, never after `k3s.service`) picks the mode from Mender's own state:
  - *trial* (`upgrade_available=1`, so this is the first boot of a new slot): run `mender-update commit`. The state script decides; on success Mender sets `upgrade_available=0` → log `RESULT mark-good`. On failure Mender runs `ArtifactRollback` (env points back to the old slot) → log `RESULT mark-bad`, then `systemctl reboot` (the standalone client never reboots by itself).
  - *fell-back* (`upgrade_available=0` but Mender's database still holds an update in progress: the bootloader already rolled back after a crash, hang or power cut): run `mender-update rollback` to finish Mender's state machine → log `RESULT fell-back`.
  - *committed* (`upgrade_available=0`, nothing in progress): log `RESULT committed-boot`; check k3s for the log only; never roll back.
- **Watchdog, API stand-in, core pods, broken app, variants:** identical to `../rauc-k3s-gate/` §4 (`i6300esb`, `RuntimeWatchdogSec=30s`; socat responder; `coredns`, `local-path-provisioner`, `onemind-core`; `apps/broken-app`; variant differences in `/etc/onemind-release`, `/etc/default/k3s`, `/etc/default/onemind-health-gate`, `/sbin/init`). Artifact versions are carried as `rootfs-image.version` provides and in `/etc/onemind-release`.
- **Why not mender-convert:** it repartitions a finished golden image, downloads a prebuilt GRUB and uses its own partition sizes. That would change several variables at once against the RAUC spike. This build installs the same pieces mender-convert installs (the client package from Mender's repository, grub-mender-grubenv at the commit mender-convert pins, `/var/lib/mender → /data/mender`) into the same disk as the RAUC spike, so the update engine is the only variable. A mender-convert run remains a separate, smaller check (§8).

## 5. Requirement IDs served

R-1 (safe, user-controlled updates), R-2 (self-healing), R-3 (long-term maintainability), M-6 (guard rails for a solo developer), M-7, P-4 (OS image surface), P-7 (bring-your-own x86), F-11 (IoT/IIoT update path). Feeds REC-DEC-05, REC-DEC-07 and REC-DEC-26 (Mender runner-up spike E2) in `01-FOUNDATION-DECISION.md` §3.2, and closes critic pass 2 gap N7's Mender half.

## 6. Glossary

| Term | Meaning |
|---|---|
| Mender | An open-source (Apache-2.0) over-the-air update system from Northern.tech: a device client, an artifact tool and an optional fleet server |
| Standalone mode | The Mender client installs an update file given on the command line; no server is involved. `mender-update install`, `commit`, `rollback` |
| Mender artifact | Mender's signed update file (`.mender`), here holding a full root filesystem image |
| State script | A script Mender runs when it enters or leaves a step of its update state machine. `ArtifactCommit_Enter` runs just before Mender commits; if it fails, Mender rolls back |
| `upgrade_available` / `bootcount` | Mender's two bootloader variables: "a new slot is on trial" and "the trial slot has already been booted once" |
| Slot A / B | The two copies of the OS on disk (here partitions 2 and 3) |
| Commit | Make the trial slot permanent (Mender: `upgrade_available=0`) |
| Health gate | The boot-time program that decides commit or roll back |
| Fresh signal | Evidence produced on *this* boot, as opposed to status stored from a previous boot |
| Stale-Ready trap | k3s keeps cluster state on the data partition; after a reboot it can report the previous boot's "Ready" |
| Watchdog | A hardware timer that reboots the machine if software stops "petting" it |
| TCG | QEMU's software CPU emulation (the guest is x86_64, the Mac is Arm) |
| SIGKILL | Instant kill of QEMU; for the guest, the same as pulling the plug |

---

## Results

*(Added after the run.)*

**Status: COMPLETE.** Two full runs (run 1: 2026-11-11 08:06–08:58 UTC, 52 min; run 2: 08:58–09:52 UTC, 53 min), each from a fresh copy of the same disk (`build-run3`, disk sha256 in `SHA256SUMS`). Everything above this line is the pre-registered text, byte for byte: `head -c "$(wc -c < <pre-registered copy>)" README.md | shasum -a 256` gives the hash in `../PREREGISTRATION.md`. Two integration problems were found and fixed before run 1; both are logged in §9, and one of them is a finding in its own right.

**Verdict: PASS with the predicted one-try limitation** (the overall rule in §3). Every pass/fail test except T9 passed in both runs. T9 failed in both runs exactly as H4 predicted: a power cut during the first boot of a good update made Mender's bootloader roll back, so the update was abandoned (the box stayed safe on the old version, T9s PASS). T10 (naive gate) committed a broken system in both runs, as expected.

> **Explain the result like I'm the founder.** Mender passed the same exam RAUC passed, with one predicted exception. With the same health check, it kept good updates, threw out a version whose Kubernetes would not start, and threw out the sneaky version whose Kubernetes *looked* healthy from yesterday's records. A version that crashed and one that froze were each tried once and dropped. Pulling the plug while the update was being written did no harm. The one difference is the second chance. RAUC gives a new version three boots to prove itself; stock Mender gives it one. So if the power goes out during that single first boot, Mender plays safe, goes back to the old version and throws the update away. You would have to download it again, which matters for off-grid boxes on slow links. That is fixable, but only by changing Mender's boot script, which means OneMind would maintain that change. We also found a trap that would bite a real product. If the health check is put in the wrong folder, Mender skips it without any warning and accepts every update. The check has to travel inside every update file.

### 7.1 Test results

Evidence: `logs/serial-run1-trimmed.log`, `logs/serial-run2-trimmed.log` and the driver verdicts in `logs/driver-run{1,2}.log`. Times are under QEMU TCG (x86 emulated on Arm), and other lab VMs were running on the same host during both runs, so durations are indicative only and not comparable to the RAUC spike to the second.

| ID | Run 1 | Run 2 | What happened (run 1; run 2 in brackets where it differs) |
|---|---|---|---|
| T0 | **PASS** | (same build) | `logs/build-run3.log`: k3s `OK` against `sha256sum-amd64.txt`; Mender APT key fingerprint `E6C8…9B00 OK`; mender-update/mender-auth 5.2.0-1+debian+trixie and mender-flash 1.1.0 installed from Mender's signed repository; 6 artifacts "signed and verified correctly" and each lists `ArtifactCommit_Enter_00_onemind-gate`; `wrong-key` "verification using provided key failed". Build ≈ 7 min. |
| T1 | **PASS** | **PASS** | GRUB `MENDER-GRUB: mender_boot_part=2 upgrade_available=0 bootcount=0`; gate `RESULT committed-boot slot=A version=1`; `K3S-FRESH ok after 113s` (110 s); `apps/broken-app 0/1`. |
| T2 | **PASS** | **PASS** | `Signature verification Error: Wrong manifest signature or wrong key`, rc 1; env unchanged; `mender-update commit` afterwards says `No update in progress` (nothing was left half-done) [C-LAB-mender-012]. |
| T3 | **PASS** | **PASS** | Install 90 s; trial boot `Booting new update...`, env `3/1/1`; `mender-update commit` ran the artifact's `ArtifactCommit_Enter` script: `no kubeconfig` ×2, `apiserver /readyz not ok`, `coredns … not Ready`, then `CHECK pass 1/3, 2/3, 3/3` at 86, 104, 121 s; `APPS (excluded from gate): broken-app 0/1 ImagePullBackOff`; Mender `Committed.`; `GATE-SCRIPT-RAN yes`; `RESULT mark-good slot=B version=2 after 124s` (116 s). Next reboot `committed-boot B v2` [C-LAB-mender-008]. |
| T4 | **PASS** | **PASS** | k3s exits at start: `no kubeconfig on this boot` until `deadline 300s reached -> refuse commit`; Mender `Committing failed. Rolled back.`; env already `mender_boot_part=3 upgrade_available=0` when the gate logged `RESULT mark-bad slot=A version=3 after 304s` and rebooted (≈ 329 s after the reboot; 334 s). Back on B v2, `K3S-FRESH ok`; the next reboot stays on B [C-LAB-mender-009]. |
| T5 | **PASS** | **PASS** | Stale trap with the fresh gate: API server up, `kubelet /healthz not answering` to the deadline; `RESULT mark-bad slot=A version=4 after 306s` (302 s); back on B v2, not retried [C-LAB-mender-009]. |
| T6 | **PASS** | **PASS** | **1 attempt** (H4): `Booting new update...` → `BAD-BOOT` → kernel panic → `Rolling back...` → `mender_boot_part=3 upgrade_available=0 bootcount=0`; gate on B: `RESULT fell-back` after `mender-update rollback` finished Mender's state; next reboot `committed-boot B v2`, A not tried. 98 s (105 s) [C-LAB-mender-010]. |
| T7 | **PASS** | **PASS** | **1 attempt** (H4, H5): `BAD-HANG: arming watchdog, then freezing` → watchdog reset → `Rolling back...` → B v2, `fell-back`; not retried. 125 s (140 s) [C-LAB-mender-010]. |
| T8 | **PASS** | **PASS** | `SIGKILL` at **16 %** of Mender's progress counter: partition A had 233,472 sectors (114 MiB) written and 595,640 (291 MiB) read (mender-flash reads the target and skips identical blocks). Restart: `MENDER-GRUB: mender_boot_part=3 upgrade_available=0`, `RESULT committed-boot slot=B version=2` (no update was in progress, because Mender records state only after the write); reinstall `good` → `mark-good slot=A version=2 after 137s` (138 s) [C-LAB-mender-011]. |
| T9 | **FAIL (predicted)** | **FAIL (predicted)** | Killed after the trial gate on B had started and logged its first check. Restart: GRUB `Rolling back...`, `mender_boot_part=2 upgrade_available=0 bootcount=0`; gate `RESULT fell-back slot=A version=2`. The good update was abandoned: no retry, a reinstall would be needed [C-LAB-mender-013]. |
| T9s | **PASS** | **PASS** | The box ended on committed A v2, `K3S-FRESH ok after 100s` (89 s), env consistent, with no input. |
| T10 (obs.) | **committed broken** | **committed broken** | Naive gate: `CHECK pass` at 60, 74, 88 s (63, 79, 93 s), `RESULT mark-good slot=B version=7`; on the committed slot `curl localhost:10248/healthz` → `NO-KUBELET` [C-LAB-mender-014]. |
| T10r | **PASS** | **PASS** | Reinstalling `good` from the broken-but-committed slot committed A v2 (137 s; 135 s). |

### 7.2 Hypotheses

| | Verdict | Why |
|---|---|---|
| H1 | **Confirmed, with a correction** | Stock Mender client 5.2.0 (Debian package), grub-mender-grubenv d7c3ec2 with unmodified boot logic, one 29-line state script and a 51-line systemd-unit script implement 01's gate. No Mender code was changed. **Correction:** the state script cannot live in the root filesystem as §4 planned; Mender runs `Artifact*` scripts only from the artifact, so the gate is embedded in every artifact with `mender-artifact write -s` [C-LAB-mender-007] (§9 item 2). |
| H2 | **Confirmed (code + lab)** | The env flips only in `ArtifactInstall`, after the whole write [C-LAB-mender-001]. In T8 a kill at 16 % left `mender_boot_part=3 upgrade_available=0` and nothing in progress, and the old slot booted. The OneMind trial marker that RAUC needs [C-LAB-rauc-k3s-gate-001] is unnecessary with Mender: `upgrade_available=1` is the trial signal. |
| H3 | **Confirmed** | Third engine, same trap: the naive gate committed v7 at 90 s (run 1) and 97 s (run 2); the fresh gate rejected the same failure (T5). Same as RAUC [C-LAB-rauc-k3s-gate-008] and Rugix [C-LAB-debian-rugix-023]. |
| H4 | **Confirmed** | T6/T7: exactly 1 attempt each, in both runs (RAUC: 3). T9: the good update was abandoned in both runs [C-LAB-mender-003, C-LAB-mender-013]. |
| H5 | **Confirmed (in emulation)** | T7: one watchdog reset, then Mender's bootloader rollback. |
| H6 | **Confirmed** | T2: signature error before any write; env and client state untouched. |

### 7.3 What the numbers and findings mean for OneMind

1. **The S2 "lab proof" tie-break row no longer separates RAUC and Mender.** Mender passed the same pre-registered battery with the same gate script (`onemind-k3s-check` unchanged), on the same disk layout, kernel, firmware and k3s. 01 §3.2 says "Mender has none"; that is now false [C-LAB-mender-008…014].
2. **The real difference the lab found is boot tries: 3 (RAUC with HAOS's GRUB logic) vs 1 (stock Mender).** With one try, any single bad event during the first boot of a good update discards it: a power cut, a watchdog reset from a transient hang, a crash. The box stays safe, but it must download the update again. For off-grid boxes on slow links (T-W3-05) that is a real cost. 01 §4.2 item 3 requires 3 tries, so **stock Mender does not meet 01's rule; patched Mender might.** The rootfs-image module only sets `bootcount=0` and never reads it [mender@0f4eb08 `support/modules/rootfs-image` L227]. So a 3-try rule looks like a boot-script-only change (relax the `bootcount` validity check and count to 3). It is **not tested** (F3), and OneMind would then maintain a fork of Mender's boot script, for GRUB and for U-Boot on Pi 5.
3. **Mender has two properties RAUC needed OneMind code for.** (a) No trial marker: the env flips after the write, and `install` refuses while an update is in progress [C-LAB-mender-001, C-LAB-mender-006]. (b) A refused commit reverts the bootloader env at once (`Committing failed. Rolled back.`), and a failed slot is never selected again by construction. RAUC needed explicit `mark-bad` and "fell-back" marking. Mender also keeps two env copies with lock files [C-LAB-mender-004]. That was not exercised by a kill during a bootloader write here (F2).
4. **New pitfall: the gate travels with the artifact, and a misplaced gate fails open, silently.** In run 0 a gate in `/etc/mender/scripts` was skipped: `mender-update commit` printed `Committed.` 4 s into the trial boot, with no check and no warning [C-LAB-mender-007]. An artifact built without the script would likewise be committed unchecked. The defence is cheap: CI checks that every artifact lists the script (`mender-artifact read`), and the device unit treats "commit succeeded but the script did not run" as an alert. This lab logs `GATE-SCRIPT-RAN yes|no`. The stronger alternative is to run the checks in the unit itself and call `mender-update commit` only after they pass (not tested).
5. **Engine-neutral layout confirmed.** The same 4-partition disk, read-only root, `/data` bind mounts and gate script worked under both engines. Only the engine packages, its config, `/var/lib/mender → /data/mender` and `/data/mender/device_type` differ. That supports 01's "switch engines with an update, not a reflash" claim. An engine-migration artifact itself was not tested.
6. **Install time.** Mender installs took 67–114 s (run 1) and 79–125 s (run 2), against 56–67 s for RAUC in its spike (one RAUC outlier at 121 s). Mender uses zstd and mender-flash's read-compare-write; RAUC uses a verity bundle copy. Host load differed (parallel spikes), so treat it as indicative only and measure on hardware (F1).

## 8. Limits and founder-runnable tests

| Gap | Status |
|---|---|
| Real hardware, real power pull (QEMU `SIGKILL` does not drop disk caches; Mender's two-copy env on FAT was not hit mid-write) | **Founder hardware**: F1, F2 |
| 3-try variant of Mender's boot script (would turn T9 into a pass) | Not tested: F3 |
| mender-convert's own output (its prebuilt GRUB, its partition sizes) instead of this hand-built equivalent | Not tested: F4 |
| Pi 5 (Mender uses U-Boot there [C-STEEL-updates-mender-017]), Jetson (E3) | Separate spikes / T-W3-06 |
| Managed (daemon) mode with a Mender server; delta updates (paid) | Out of scope: standalone only, per the task |
| One kill point per power-cut test per run (16 % of Mender's counter) | F2 sweep |
| Gate process crash during the trial boot: the box keeps running the uncommitted slot until the next reboot, and **the next reboot rolls back** (one try). That is safer than RAUC's equivalent case, but the update is lost | Not tested |
| Lab-only shortcuts: fixed machine-id, serial autologin, `systemd-logind` masked, restricted user-net | Must not ship |

**F1: the same suite on an x86 box (Beelink or Dell 5540), about 1 hour.** In a Debian 13 Lima VM: `sudo OUT=/var/lab/mender-out DL=<k3s dir> GE=<grub-mender-grubenv@d7c3ec2 dir> bash scripts/build.sh`. For hardware, add `console=tty0` to `scripts/guest/11_bootargs_grub.cfg`, add a `getty@tty1` autologin drop-in (lab only), and replace `i6300esb` with the box's watchdog driver (for example `iTCO_wdt`; check `dmesg | grep -i watchdog`). Write `disk.img` to a **spare** USB SSD from the Mac: `diskutil list` (check the size twice), `diskutil unmountDisk /dev/diskN`, `sudo dd if=disk.img of=/dev/rdiskN bs=4m`. Boot UEFI with Secure Boot off. By hand, reading `/data/onemind/gate.log`: `mender-update install /data/artifacts/good.mender && systemctl reboot` (expect `mark-good`), then `bad-k3s` and `bad-noagent` (expect `mark-bad`, return to the old slot), then `bad-boot` and `bad-hang` (expect one attempt, `fell-back`). **PASS:** all with no keyboard after `reboot`, and `GATE-SCRIPT-RAN yes` on every commit. Record the good-commit time and the bad-decision time. **FAIL:** a keyboard is needed, or a slot is committed while `curl -s localhost:10248/healthz` fails.

**F2: real power pulls (same box).** Pull the cord 10 times: at the start, middle and end of the install's progress counter, during the reboot, and during the trial gate. After each, record `grub-mender-grubenv-print`, `cat /boot/efi/grub-mender-grubenv/mender_grubenv{1,2}/lock`, `fsck.vfat -n /dev/disk/by-partlabel/esp`, `mender-update show-artifact` and the last gate line. **PASS:** 10/10 end on a working slot without a keyboard, with a consistent env (both copies agree after the next boot). A pull during the trial gate is **expected** to end on the old slot with the update abandoned (stock Mender). **FAIL:** a corrupt env or ESP, or no boot.

**F3: 3-try boot script (can run in this QEMU lab, about 1 hour).** In a copy of grub-mender-grubenv, allow `bootcount` 0–3 in `mender_check_grubenv_valid` and change `mender_load_env_with_rollback` to roll back only when `bootcount` has reached 3 (incrementing it otherwise). Rebuild and rerun `run-tests.py`, with T6/T7 expecting 3 attempts. **PASS:** T9 commits B v2 on the retry, and every other test still passes. This is the experiment that decides whether Mender can meet 01 §4.2 item 3.

**F4: mender-convert path.** Run mender-convert 5.3.0 (`generic_x86-64_hdd_config`, Docker inside a Lima VM) on a raw image of the same rootfs. Embed the gate in the artifacts and rerun T1–T8. **PASS:** same results. This checks that the supported conversion path behaves like this lab's hand-built equivalent.

## 9. Deviations and problems (honest log)

1. **`/var/lib/mender/device_type` missing (smoke run, before run 1).** `mender-update install` failed with `Failed to open '/var/lib/mender/device_type'` (`logs/driver-smoke1-no-device_type.log`). mender-convert writes this file to `/data/mender` [mender-convert@85e8c50 `mender-convert-modify` L217–L218]. The build now writes `device_type=onemind-lab-x86_64` there (`build-run2`). T2 had already passed in the smoke run, because signature verification comes first.
2. **Gate script location (design text in §4 changed in practice).** §4 put the gate in `/etc/mender/scripts`. In run 0 (`logs/*run0-rootfs-script-not-run*`), T1 and T2 passed, but in T3 Mender committed B **without running the gate**: 0 checks, `Committed.` after 4 s. Mender runs `Artifact*` scripts only from the artifact [C-LAB-mender-007]. Run 0 was stopped during T4. From `build-run3` on, the same script is embedded in every artifact (`-s`). The unit logs `GATE-SCRIPT-RAN` after each commit as a tripwire; it is an observation only and decides nothing. Thresholds, checks and pass criteria did not change. This is finding 7.3 item 4.
3. **Slot size.** As in the RAUC spike, the slots are 2 GiB, not the 2.5 GiB named in that spike's §4 (this README's §4 already says 2 GiB).
4. **Lab VM size.** 8 vCPU / 12 GiB instead of the RAUC spike's 10 / 16 GiB, because other spikes were sharing the host. The guest QEMU machine is identical.
5. `systemd-logind` is masked (as in the RAUC spike), so `systemctl reboot` from the shell prints `Call to Reboot failed: … login1 …` before systemd reboots anyway. This is not on the update path.
6. Run 1 and run 2 used the same build (`build-run3`), each from a fresh copy of the disk. `build-run1` and `build-run2` are kept as logs only.

## 10. What competitors do

| Product | Update engine and trial boots | When a new OS is committed | Kubernetes-aware? | Constraint fit for OneMind |
|---|---|---|---|---|
| Home Assistant OS | RAUC + GRUB, 3 tries [C-LAB-rauc-010] | Supervisor marks the booted slot good when it starts [C-LAB-rauc-011] | No (Docker) | **High** for the mechanism; **low** for its gate (it would commit the T5 failure) |
| umbrelOS (legacy Mender devices) | A separate `umbrelos-mender-amd64` variant keeps Mender's partition numbering [C-W3-040] | Not verified | No | Medium (same Debian appliance class; PolyForm-NC: patterns only) |
| Mender via mender-convert (Debian, x86) | grub-mender-grubenv, **1 trial boot** [C-LAB-mender-003] | `mender-update commit` (standalone) or the daemon; `ArtifactCommit` scripts embedded in the artifact can veto [C-LAB-mender-007] | No (generic) | **High** for the mechanism (this lab); **medium** against 01's 3-try rule without a patch |
| Fedora IoT / bootc + greenboot | rpm-ostree/bootc with a boot counter and health scripts [C-W2-052] | When greenboot's required checks pass | Possible with a k3s check (W2 lab) | Medium; our lab saw a power-cut finalize problem [C-LAB-fedora-bootc-011] |
| OneMind lab, RAUC | RAUC 1.13, 3 tries + watchdog [C-LAB-rauc-k3s-gate-006…010] | Fresh-signal k3s gate, pre-install marker | Yes | **Direct**: 01's chosen design; T0–T10 pass |
| **OneMind lab, this spike** | Mender 5.2.0 standalone, 1 try + watchdog | Same fresh-signal gate, embedded in each artifact; no marker needed | Yes | **Direct** runner-up: T0–T10 pass except T9 (one try) |

## 11. Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| L-M1 | In 01 §3.2, replace the tie-break row "Lab proof: Mender has none" with this lab's result: **both engines pass the same battery**. The remaining evidence-based difference is **boot tries**: stock Mender abandons a good update after one interrupted first boot (T9), which conflicts with §4.2 item 3. That row still favours RAUC, but on a narrower, testable point. Run F3 before treating it as decisive. | R-1, R-3, M-7 |
| L-M2 | If Mender is chosen, or kept as the fallback: (a) maintain a 3-try patch of Mender's boot script and gate releases on T9; (b) embed the gate in **every** artifact and fail CI if `mender-artifact read` does not list it; (c) have the device unit alert when a commit succeeds without the gate having run, or run the checks in the unit before `commit`. | R-1, R-2, M-6 |
| L-M3 | Keep the gate engine-neutral: one `onemind-k3s-check` package, unchanged across RAUC and Mender, with a thin per-engine adapter (RAUC: pre-install marker + `mark-good`/`mark-bad`; Mender: `ArtifactCommit_Enter` + `commit`/`rollback`). | R-3, P-4, M-6 |
| L-M4 | The engine-neutral disk layout held: same partitions and `/data` bind mounts under both engines. Keep `/data/<engine>/` as the only engine-specific state, so an engine switch stays an update, not a reflash. Test an actual engine-migration artifact before relying on it. | R-3, P-7 |
| L-M5 | Never ship an API-status-only gate. RAUC, Rugix and now Mender all committed a broken k3s with it. | R-1, AI-4 |
| L-M6 | Add F1–F4 to `22-HARDWARE-LAB-TEST-PLAN.md` and the 180-day plan's update-engine gate. F3 (3-try Mender) can run in this QEMU lab without hardware. | R-1, P-7, F-11 |

## 12. How to re-run

```bash
LAB=<lab-dir>/mender                                   # outside the repo
mkdir -p $LAB/logs $LAB/dl && cp -R research-output/evidence/lab/mender/scripts $LAB/scripts
# grub-mender-grubenv at the commit mender-convert 5.3.0 pins:
git init $LAB/grub-mender-grubenv-d7c3ec2 && cd $LAB/grub-mender-grubenv-d7c3ec2 && \
  git fetch --depth 1 https://github.com/mendersoftware/grub-mender-grubenv d7c3ec217e281727f56c3651799f805637cb2cda && \
  git checkout FETCH_HEAD && rm -rf .git && cd -
limactl create --name lab-mender --tty=false --vm-type vz --cpus 8 --memory 12 --disk 80 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-mender
limactl shell lab-mender -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf \
  gdisk dosfstools mtools e2fsprogs openssl grub-common python3 curl zstd make gpg socat
# mender-artifact 4.4.2 from Mender's workstation-tools repo (key fingerprint E6C857345575F9218396566224072B80A1B29B00)
# k3s v1.37.2+k3s1: k3s, k3s-airgap-images-amd64.tar.zst, sha256sum-amd64.txt into $LAB/dl
limactl shell lab-mender -- sudo bash -c "OUT=/var/lab/mender-out DL=$LAB/dl GE=$LAB/grub-mender-grubenv-d7c3ec2 bash $LAB/scripts/build.sh"   # T0, ~7 min
limactl shell lab-mender -- sudo bash -c "mkdir -p /var/lab/run && cp --sparse=always /var/lab/mender-out/disk.img /var/lab/run/ && \
  python3 -I $LAB/scripts/run-tests.py --disk /var/lab/run/disk.img --log $LAB/logs/serial.log"   # T1-T10, ~53 min
scripts/trim-logs.sh $LAB/logs/serial.log > serial-trimmed.log
limactl delete -f lab-mender
```

`run-tests.py` exits 0 when every pass/fail test except T9 passes (the §3 overall rule; T9 is reported separately). `--upto T3` stops early.

## 13. Files

- `scripts/build.sh`: image and artifacts. `scripts/guest/`: everything installed into the image or artifacts (`mender.conf`, the `ArtifactCommit_Enter_00_onemind-gate` state script, the mode-choosing `onemind-health-gate` and its unit, `onemind-k3s-check` (unchanged from the RAUC spike), k3s unit, manifests, API stand-in, bad-hang init, and the two lab GRUB snippets). `scripts/grub.cfg.generated`: Mender's boot script as built.
- `scripts/run-tests.py`: test driver (stdlib Python; run with `-I`). `scripts/trim-logs.sh`: log trimming and masking.
- `logs/`: build logs (`build-run1..3`), the smoke run without `device_type`, run 0 (gate not run), runs 1 and 2 (driver verdicts and trimmed serial logs), `versions.txt`. VM-internal addresses are masked as `<vm-private-ip>`.
- `SHA256SUMS`, `image-packages.txt`, `versions.md`: pins and hashes. The lab signing keys stayed inside the VM and were deleted with it; only the public verification key and Mender's public APT key are hashed.
