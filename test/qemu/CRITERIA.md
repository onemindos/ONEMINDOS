# QEMU battery: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-11 before any OneMind image of this repo was built or booted. The sha256 of this file at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it (a separate commit, before the battery code; brief 30 §2 rule 4). Nothing in this file may change afterwards except typo fixes; any other change is a new, dated section at the end, and results never live here (they go to `test/qemu/results/` and CI logs).

**Serves:** D-B1.6, D-B2.2, B13 item 1 (brief 30), REC-DEC-05, -07, -31, -45; R-1, R-2, R-3, M-6, P-4, P-7. **Source of the criteria:** `research-output/evidence/lab/rauc-1152/README.md` §3, which reuses `../rauc-k3s-gate/` §3. They are copied here in substance and adapted only where the build differs from the lab (listed in §3 below).

## 1. Starting state and rules (unchanged from the lab)

- The box starts on slot A with version `1`. "No human input" means no command between an install's `reboot` and the end state, except the defined emulated power cuts (SIGKILL of QEMU).
- The gate deadline is **300 s** per trial boot (`ONEMIND_GATE_TIMEOUT`, default in the image); 3 fresh passing rounds 10 s apart commit.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A run that fails because of a driver (harness) bug is kept in the logs and named as such; it may be re-run **once** (rule 4).
- The run records whether QEMU used KVM or TCG and the host's CPU count with every verdict, because the deadline is wall-clock time [C-LAB-aarch64-gate-006].

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | The CI build, with no manual step, produces: RAUC from tag `v1.15.2` whose checked-out `HEAD` is `4fb7c798d6ae412344fb8f8d310d773046af3441`, `rauc --version` printing `1.15.2` (with or without a leading `v`); the rootfs from the pinned base digest and snapshot; the disk image and the bundles `good` (v2), `bad-k3s` (v3), `bad-noagent` (v4), and, when the run goes past T5, `bad-boot` (v5), `bad-hang` (v6), `naive-noagent` (v7); `wrong-key`; `plain-good` (v2, **plain** format). k3s artifacts verified by sha256 against the pinned values; every verity bundle reports format `verity`; `rauc info` with the dev keyring rejects `wrong-key`; the distribution's `rauc` / `rauc-service` packages are **not** installed in the image | Any manual edit, hash mismatch, wrong commit, or the distribution's RAUC in the image |
| T1 | First boot | The gate logs `RESULT committed-boot slot=A version=1`; a fresh k3s check passes (`K3S-FRESH ok`) on that boot; the guest's `rauc --version` prints `1.15.2`; `/etc/rauc/system.conf` contains `bundle-formats=verity`; the test app `apps/broken-app` is `0/1` (it can never start, and the gate ignores it) | Any of these missing within the timeouts, or a different RAUC on the guest |
| T2 | Signature control | `wrong-key` install exits non-zero with a signature/certificate error; grubenv unchanged; no trial marker written | Installs, or the boot order changes |
| T11 | Verity-only policy | `plain-good` (validly signed by the dev key) is refused with `Bundle format 'plain' not allowed`; grubenv unchanged; no trial marker | Installs, starts writing, or writes a trial marker |
| T3 | Good update | `good` installs to B; on the trial boot the gate logs at least 3 `CHECK pass n/3` and `RESULT mark-good slot=B version=2`; the apps line shows `broken-app` not ready (apps excluded); the next reboot logs `RESULT committed-boot slot=B version=2` | No commit, a commit with fewer than 3 passes, or a commit of the wrong slot |
| T4 | Bad update: k3s broken | `bad-k3s` installs to A; with no input the gate logs `RESULT mark-bad slot=A version=3` at the deadline, the box reboots to `committed-boot slot=B version=2`, grubenv shows `A_OK=0`, and a fresh k3s check passes on B | A commit of A, a hang, or any input needed |
| T5 | Stale-Ready trap | `bad-noagent` (API server up, kubelet never runs) installs to A; with no input the gate logs `RESULT mark-bad slot=A version=4`, then `committed-boot slot=B version=2`, `A_OK=0`, fresh k3s on B | The gate commits A (stale status believed) |
| T6 | Kernel panic | `bad-boot` to A: exactly 3 boot attempts (`BAD-BOOT` ×3), then GRUB falls back; the gate on B logs `RESULT fell-back slot=B version=2` with A marked bad; the next reboot does not try A again | Fewer/more than 3 attempts, no fall-back, or A retried |
| T7 | Hang + watchdog | `bad-hang` to A: 3 watchdog resets (`BAD-HANG` ×3), then the same fall-back as T6 | As T6 |
| T8 | Power cut mid-write | During the `good` install to A, after `pre-install: trial marker slot=A` and the copy has started, QEMU is killed before A is activated; the next boot logs `fell-back slot=B`, marker cleared, `A_OK=0`; a reinstall of `good` then commits `mark-good slot=A version=2` | Boots an ungated A, bricks, or the reinstall fails |
| T9 | Power cut in commit window | Killed after the first trial check of `good` on B and before commit; the next boot shows `B_TRY=2` in the GRUB line and the gate logs `RESULT mark-good slot=B version=2` with no reinstall | Falls back without a second try, or needs input |
| T10 | Naive gate (observation) | Observation only: with the test-only naive check (freshness off) the `naive-noagent` bundle is expected to commit a box with no kubelet (the stale-Ready trap reproduced) | n/a (recorded as OBSERVED) |
| T10r | Recovery | Installing `good` from the naive-committed slot commits `mark-good` on the other slot, version 2 | Does not commit |

## 3. Adaptations from the lab (and why)

1. **Version strings.** The image carries `ONEMIND_VERSION` in `/usr/lib/os-release` (brief 30 B5 G7) instead of the lab's `/etc/onemind-release`. The test fixtures keep the lab's integer versions 1–7.
2. **Bundle delivery.** Bundles reach the guest on a second, read-only virtual disk (filesystem label `onemind-test`) instead of being baked into the data partition, so the shipped data partition holds no test files.
3. **Naive mode lives only in the test harness.** The shipped `onemind-k3s-check` has no freshness switch. T10 replaces it inside the `naive-noagent` fixture only. A CI check fails any shipped rootfs that contains a naive mode (brief 30 B5).
4. **Lab-only conveniences** (serial autologin, the never-starting `broken-app`) come from `test/qemu/overlay/`, applied to test fixtures only, never to `make image` output.
5. **Disk layout.** The fixtures use each board's real `layout.yaml` (brief 30 B2 / 01 §4.3 labels) instead of the lab's 4-partition test layout.
6. **Boards.** `x86_64-efi` boots OVMF (UEFI) as in the lab. `vm-do` (BD-DO-1) boots **SeaBIOS** (QEMU's default BIOS, no pflash) through GRUB `i386-pc`. `arm64-efi` boots AAVMF on `virt`.

## 4. New criteria (not in the lab)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T4v | Verdict, k3s broken | T4's `mark-bad` line carries `verdict=image-bad` (G1/G2 never passed; brief 30 B5 rev. 4) | Any other verdict |
| T5v | Verdict, stale-Ready | T5's `mark-bad` line carries `verdict=image-bad` (the kubelet, G2, never passed) | Any other verdict |
| TC1 | Cloud first boot (`vm-do` only) | With a NoCloud seed disk attached (no ConfigDrive in QEMU), `cloud-init status` reports `done`; the seed's public key is in `~onemind/.ssh/authorized_keys`; `ssh.service` is active; the SSH host keys live under `/data` (not in the read-only slot) | Any of these missing within 600 s of the first boot, or host keys inside the slot image |

**Battery verdicts per board for this build session's "done" (task scope):** `x86_64-efi` and `vm-do` must PASS T0–T5 (T0, T1, T2, T11, T3, T4, T5) plus T4v and T5v, and `vm-do` also TC1. `arm64-efi` must PASS T0 and T1. Every other cell is reported, never required.
