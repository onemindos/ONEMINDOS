<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lab LAB-storage-actions: mirror operations with power cuts, LUKS2 members, boot assembly

**Status:** COMPLETE (2026-11-12). Final runs pass; five bugs found and fixed along the way (below).
**Serves:** STORAGE-ACT-1 / UMB-STOR-4 (operation engine), UMB-STOR-5 (gateway actions), UMB-STOR-2 (boot assembly), STORAGE-LUKS-1 / CORE-SEC-5 member side (H-11). **Code:** `internal/storage`, `internal/storage/ops`, `cmd/onemindd/storage.go`, `core/onemind_core/storage.py`. **Design:** [`docs/leap/core/STORAGE-ACTIONS.md`](../../../../docs/leap/core/STORAGE-ACTIONS.md).

> **In plain words.** The box can now turn one data disk into a mirror, add a disk, swap a disk and take one out, each only after the owner approves the exact plan. Each step is written to a journal before and after it runs, so if the power goes out in the middle, the box picks up where it stopped (or undoes the half-done part) when it starts again. This lab pulled the power at the worst moments, in the middle of copying data to a new disk and in the middle of replacing a disk, and checked every byte afterwards. It also booted with a disk missing and with it back. Every disk is encrypted, and one recovery key, shown once, opens all of them.

## Setup

| Item | Value |
|---|---|
| Host | Apple Silicon Mac, Lima 2.3.0 (`vmType: vz`) |
| Guest | Debian 13 (trixie) arm64 cloud image, kernel `6.12.115+deb13.1-cloud-arm64`, 2 vCPU, 2 GiB RAM, no TPM |
| Disks | `vda` system; `osa-a`, `osa-b`, `osa-c`: three blank 4 GiB raw Lima disks (`format: false`), seen as `vdb`, `vdc`, `vdd` |
| Tools (Debian packages) | btrfs-progs 6.14, cryptsetup 2.7.5, systemd 257, gdisk, smartmontools, util-linux, jq and curl (lab scripts only) |
| Binary | `onemindd` built from this branch, `GOOS=linux GOARCH=arm64` |
| Gateway (phase 10) | `core/` in a venv inside the VM, user `onemind-gw` in group `onemind`, SQLite, the repository's public example tokens |

**Power cut** = `echo b > /proc/sysrq-trigger`: an immediate reboot with no sync and no unmount. Only the system disk is flushed first (`sync -f /root`), so the log line survives; the data set is cut dirty. **Detaching a disk** = stop the VM, drop it from `additionalDisks`, start again. **The recovery key** is taken once through the socket and saved in `/root/lab/recovery.key` on the VM's system disk, a lab stand-in for the owner writing it down and typing it at boot. **Fault injection:** while `/run/onemind/storage/hold-before-<step>` exists the engine waits before that step (`Engine.HoldDir`), so a cut can land at an exact point.

Scripts are in `scripts/`; full output is in `logs/` (`SHA256SUMS` covers both).

## Results

| # | Phase | Expected | Observed | Log | |
|---|---|---|---|---|---|
| 1 | `onemindd storage init` on `vdb1` (first boot) | LUKS2 slots: recovery (argon2id), set key (pbkdf2), OneMind token; btrfs `@`, `@storage`, `@snapshots`; set key inside `@` | as expected; argon2id memory capped to 141 MiB by cryptsetup on this 2 GiB VM (the 256 MiB pin is a ceiling) | 1 | PASS |
| 2 | Recovery key through the socket | shown once, then `not_found` | 71 characters, systemd modhex format; the second take returns `not_found` | 1 | PASS |
| 3 | `storage.mirror.create` (vdb → vdb+vdc), power cut at 1 of 8 chunks balanced | boot unlocks both members from their tokens; the engine waits for the balance the kernel resumed and finishes | as expected: the engine adopted the boot's mapping name, balance done in 2 attempts, raid1 verified, scrub clean, corpus OK, the recovery key opens the new member | 2, 3 | PASS |
| 4 | `storage.mirror.add` (vdd), power cut after the header copy got its own UUID, before its own token | the boot does not unlock the half-made copy; the engine restarts the prepare phase | the boot skipped `vdd1` ("carries another member's token"); prepare steps ran twice; raid1 data + raid1c3 metadata verified; scrub clean; corpus OK | 4, 5 | PASS |
| 5 | `storage.mirror.remove` (vdd, wipe) | metadata raid1c3 → raid1 first, chunks moved off, old disk blank | as expected; `vdd` blank afterwards | 6 | PASS |
| 6 | `storage.mirror.replace`, power cut at 20 % of `btrfs replace` | the kernel resumes the replace at mount; the engine waits, sees the devid on the new disk, finishes | as expected (after the fixes below): kernel `continuing dev_replace … @0%` then `finished`; replace step skipped as done; old disk wiped; scrub clean; corpus OK | 21, 22 | PASS |
| 7 | Failure in the join phase (mapping closed by hand before `device add`) | roll back: target blank, set unchanged | `rolled_back`; `wipefs` and `sgdisk --zap-all` of `vdd`; set protected; corpus OK | 23 | PASS |
| 8 | Gateway end to end | an agent requests, cannot approve; the owner approves; the poller closes the action from the journal | as expected; audit `requested → awaiting_approval → authz.denied (agent) → approved (owner) → dispatched → succeeded`; set grew to three members; a user outside group `onemind` cannot connect to the socket | 24 | PASS |
| 9 | Boot assembly (`onemindd storage assemble`), all members present | mounted, protected | as expected | 25, 26 | PASS |
| 10 | Boot with `osa-b` detached | wait 20 s, mount degraded, markers `degraded` and `needs-scrub`; the set reads degraded | as expected (after fix 5) | 27 | PASS |
| 11 | 64 MiB written while degraded; disk back; `storage.mirror.repair` | normal mount, still degraded (stale copies) until the scrub; then protected | scrub corrected 16 412 errors, 0 uncorrectable; tokens re-stamped at one generation; protected; all 41 files match | 28, 29 | PASS |

## Bugs the lab found (all fixed, each with a unit test)

1. **Stale replace status (logs 10, 11).** `btrfs replace status` keeps reporting the last replace ever run on the filesystem. A second replace looked "finished" and was skipped. The old member's token was then demoted while it still held devid 2, so the next boot skipped it and mounted degraded. **Fix:** a replace is done only when the new device holds the devid; demoting the old member's token checks the same; the boot retries with older-generation members before mounting degraded; `repair` re-stamps every member's token (log 12 recovered the set this way).
2. **ENOSPC on replace (logs 13, 14).** At 94 % allocated, the kernel could not set a block group read-only. The engine failed forward-only and the set stayed protected. **Fix:** `PlanReplace` requires headroom on the members that stay (10 %, at most 1 GiB, log 15 shows the refusal), and a replace that fails before the new disk takes the devid rolls back.
3. **Kernel lock race after a cut mid-replace (logs 18, 19).** After the kernel finished the resumed replace, the status text already read "finished" while the kernel still held the replace lock. A re-run failed with "another exclusive operation 'device replace' in progress", and the operation was recorded as failed although the data had moved. **Fix:** the engine reads `/sys/fs/btrfs/<fsid>/exclusive_operation`, re-checks the membership for a few polls after the replace stops, and treats a failed attempt whose effect is in place as done (log 22).
4. **Half-made copy unlocked at boot (found before phase 4, while designing it).** A cut between the header copy and the new disk's own token left a disk carrying another member's token. **Fix:** the token records the member's own GPT partition id, and the assembly skips any partition whose token names another one (phase 4 shows the skip).
5. **Missing device not listed (log 27, first try).** For a set that is not mounted, btrfs-progs prints only `Total devices 3` and `*** Some devices missing`, without a line for the missing devid. The first assembly counted zero missing and went to recovery mode. **Fix:** `ShowCounts` uses the total; a failed normal mount falls through to the older-generation and degraded steps.

Lab-script mistakes, not product bugs, also left traces in the logs: the recovery key was first saved with a trailing newline (log 1 shows the failed unlock before the fix); the mid-replace trigger missed twice (logs 7, 16) because btrfs prints `20.0% done` with no leading text while running. The first runs of `3-check.sh` show journal lines from earlier boots; later scripts filter by boot.

## Findings for other streams

- **Gateway on Debian 13 (image stream):** `core/pyproject.toml` pins Python `>=3.12,<3.13`, and Debian 13 ships 3.13. The lab installed with `--ignore-requires-python` and it ran; the image's gateway venv must bring 3.12 or the pin must widen.
- **argon2id memory:** cryptsetup lowers the requested memory on small machines (141 MiB on 2 GiB). Unlocking a member costs about 1 s of argon2id on this VM; the assembly opens members one after another, so a three-disk box spends about 3 s unlocking. TPM2 avoids it.
- **Boot assembly order:** unlock and mount in the signed root, before `local-fs.target`. No initramfs change is needed (os patch §1).

## Not covered

TPM2 unlock (no vTPM in Lima VZ; the TPM2 slot is enrolled by `systemd-cryptenroll` and cloned with the header, both standard paths), hot unplug and USB bridges (STOR-10 hardware lab), x86_64, a power cut at every single step (the engine's unit tests cut in the prepare, join and commit phases, before and after a step's effect; the VM covered the long-running ones, balance and replace, and the prepare phase), and the image's own units (os patch).

## Reproduce

```
limactl disk create osa-a --size 4GiB --format raw   # and osa-b, osa-c
# VM: base template:debian-13; additionalDisks osa-a, osa-b, osa-c with format: false;
#     apt-get install btrfs-progs cryptsetup smartmontools gdisk jq util-linux nvme-cli
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -o onemindd ./cmd/onemindd
limactl copy onemindd scripts/*.sh <vm>:/var/lib/lab/
# inside, as root, in /var/lib/lab: sh 1-init.sh; sh 2-create-cut.sh (the VM reboots); sh 3-check.sh lab-create-1 /dev/vdb1 /dev/vdc1; ...
```
