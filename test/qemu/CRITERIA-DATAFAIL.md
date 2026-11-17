# QEMU battery, data disk failure: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-14 before the recovery mode it judges (`os/recovery/`) was built into any image or booted. Its sha256 at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it, which comes before the code. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the battery's `results.json` and CI logs).

**Serves:** the gap found in the umbrelOS image study (a failed data disk must not stop a box in a systemd emergency shell), CORE-UPDATE-8 / `docs/leap/core/UPDATES.md` §3.5 (rescue that works with k3s stopped), REC-DEC-45 (the `environment-bad` verdict), D-007. Design: `os/recovery/README.md`. **Does not replace** `CRITERIA.md`: T0–T11 keep their own criteria and run first on the same disk.

## 1. Starting state and rules

- The tests run in `test/qemu/run-tests.py` after the last test the run selected, whenever `--upto` is `T5` or later, on the battery's own disk and VM. They start from whatever committed state the earlier tests left (they read the booted slot and version; they do not assume one).
- **"Detach the data disk"** means: with QEMU stopped, rename the GPT partition `onemind-data` to `onemind-data-detached` in the disk image (`sgdisk -c`), so no partition carries the label the box mounts by. **"Restore"** renames it back. Nothing else in the image changes: the filesystem and its contents are untouched. This is how a missing, unplugged or dead data disk looks to the box.
- "Recovery state" means all of: the console shows `ONEMIND-RECOVERY: entered slot=<S> version=<V> reason=missing decision=<D>`; `onemind-recovery.target` is active; `emergency.target` and `rescue.target` are inactive; `onemind-health-gate.service` and `k3s.service` never started on that boot.
- "Reachable" means all of: the guest has a global IPv4 address; `http://<that address>:8080/` answers from inside the guest with HTTP status 503 and a body that contains `data disk`; the same page answers from the **host** through a QEMU forwarded port (an off-box client), and `/status.json` there returns JSON with `"state": "recovery"`; the same host check passes again at least 60 s later, and the serial shell still answers.
- No human input except the defined power-offs, disk edits and the reboots the test sends.
- Timeouts (wall clock): recovery line 600 s after QEMU starts; gate result as in `CRITERIA.md`.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such. Every verdict records the board, KVM or TCG, and the host CPU count.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| TD1 | Committed slot, data disk detached | Power off, detach, boot: the box reaches the recovery state on the committed slot `S` with `decision=committed` and is reachable; the ESP file `/boot/efi/onemind/data-failed` names `slot=S`; the bootloader shows `S_OK=1` and `S_TRY=0` (the try counter was reset, so repeated boots do not walk the box back to the other slot). Power off, restore, boot: the gate logs `RESULT committed-boot slot=S version=V`, the ESP note is gone and its line is in `/data/onemind/data-failures.log` | Emergency or rescue mode, no recovery line, the page not answering (in the guest or from the host), the gate or k3s started, the try counter not reset, or the restored boot not committing `S` |
| TD2 | Update trial, data disk detached | Install `good` (v2) to the other slot `T`, power off (no reboot), detach, boot: the box reaches the recovery state on `T` with `decision=trial` and is reachable; `T_OK=1` (not marked bad); `/boot/efi/onemind/pending` names `T`. Power off, restore, boot: the gate logs `RESULT mark-good slot=T version=2`, and `/data/onemind/bad-releases` has no line with `version=2` | `T` marked bad, a fall-back, a `mark-bad` or `unhealthy` result, or a `version=2` line in `bad-releases` |
| TD3 | Data disk stays failed for the whole trial | Install `good` (v2) to the other slot `T2`, power off, detach, boot: three boots of `T2` each reach the recovery state on `T2` with `decision=trial` (the test reboots after each); the fourth boot reaches the recovery state on the other slot `O` with `decision=fell-back`. Power off, restore, boot: the gate logs `RESULT fell-back slot=O version=2` with `verdict=environment-bad`, and the last line of `/data/onemind/bad-releases` ends with `version=2 verdict=environment-bad` | Any boot not in recovery, a fourth boot not on `O`, `verdict=image-bad`, or no `environment-bad` line |

**Verdicts per board for this change's "done":** `x86_64-efi` and `vm-do` must PASS TD1–TD3 (both run `--upto T5` in `image.yml`). `arm64-efi` runs `--upto T1` and does not run them; that is reported, not required.

## 3. What these tests do not cover (reported, never claimed)

- A **corrupted** filesystem (the partition is there but `fsck` or `mount` fails, reason `unmountable`), a data partition mounted read-only (`read-only`), and a failed bind mount (`layout`). The same guard handles them, but no fixture produces them deterministically in v0: `e2fsck -p` tries the backup superblocks by itself, so a zeroed superblock is not a stable fixture.
- Real hardware (a pulled USB disk, an SSD that dies while running). Hardware runs wait on F-25.
- A box whose data disk comes back while it is in recovery: v0 stays in recovery until the next boot, by design (`os/recovery/README.md`).
