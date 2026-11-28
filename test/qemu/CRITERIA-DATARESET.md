# QEMU battery, factory reset of the data disk (R1, R2): pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 (ET) in the fix round of PR #1147, before R1 and R2 had ever run on any image. Its sha256 is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the harness's `results.json` and CI logs). It adds to, and never edits, `CRITERIA-DATAENC.md` (E1-E4) and `CRITERIA-DATABTRFS.md` (E5-E7).

**Why it exists:** the unit tests of the wipe fake `lsblk` and `cryptsetup`, so they cannot show that a default box really comes back from a reset. The review of PR #1147 found two faults only a real boot shows: the encrypted volume is already unlocked when the wipe runs, and nothing formats the blank partition on the boot that wiped it. R1 and R2 are those two cases, end to end.

**Serves:** #146 (factory reset, HOST-ACTIONS.md section 4), IMG-05 (#152), decision D-020. Harness: `test/qemu/dataenc.py` (`make dataenc`), which runs R1 and R2 after E5-E7 on fresh copies of the same fixtures.

## 1. Starting state and rules

- Image and fixtures: `make fixtures` with the default layout (blank data partition). Each test starts from a **fresh copy** of the fixtures disk and does not depend on the other tests.
- "Arming" means writing the ESP file `/boot/efi/onemind/factory-reset` exactly as `onemindd` would for the plan that `onemindd host plan factory-reset` prints on that box: `DATA_SET` is the plan's `set_uuid`, one `MEMBER=<partuuid>:<generation>` line per plan member, expiry one hour ahead. Then the test sends `systemctl reboot`. Nothing else is done to the box (no manual unlock, close or mount).
- "Marker" means a file of 32 random bytes written under `/data` (and one under `/data/storage`) before arming. "Old identity" means the filesystem UUID of the data partition (R1) or the LUKS2 UUID of the partition (R2) before arming, and, for R2, the recovery key printed on the first boot.
- No human input except what a test sends on the serial console. A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| R1 | Plain box: no TPM, plain btrfs data (E5's box), reset armed | After the one reboot, with nobody typing, the box wipes and restarts by itself and then makes a fresh first boot: the console prints `making it plain btrfs, NOT encrypted` after the arming reboot; the gate commits; `/boot/efi/onemind/factory-reset` is gone and `factory-reset.done` exists; the filesystem UUID of the data partition differs from the old identity; both markers are gone; `/data` is mounted from the partition and `/data/storage` is a mount of subvolume `@storage`; no `ONEMIND-RECOVERY: entered` line appears after the arming reboot; no failed units | Recovery mode, a prompt, the old UUID or either marker still there, `/data` or `/data/storage` not mounted, a failed unit, the armed marker still present, or the box not reaching the gate |
| R2 | Encrypted box: a software TPM, LUKS2 + btrfs data (E1's box, TPM #4), reset armed | After the one reboot, with nobody typing: the data disk is **not** unlocked on the arming reboot (no `data disk unlocked` line and no passphrase or recovery-key prompt appears at any point), the box wipes and restarts by itself, and the next boot makes a fresh encrypted first boot: a **new** `RECOVERY KEY` line with eight groups of eight modhex letters that differs from the old key; the gate commits; the LUKS2 UUID of the partition differs from the old identity; `/data` is mounted from `/dev/mapper/onemind-data`; `/data/storage` is a mount of subvolume `@storage`; both markers are gone; the marker file on the ESP is gone and `.done` exists; no `ONEMIND-RECOVERY: entered` line appears after the arming reboot; no failed units | A prompt of any kind, an unlock of the old volume, recovery mode, the old UUID or key reused, either marker still there, `/data` still on the plain partition or not mounted, a failed unit, or the box not reaching the gate |

## 3. What these tests do not cover (reported, never claimed)

- A passphrase box (no TPM, `onemind.data_encrypt=passphrase`): R2's "never unlocked" rule is the same code path, but typing a passphrase is not exercised here.
- A mirror of several disks, a late USB disk, or a power cut half way through the wipe (the unit tests of `internal/host` cover those with fake disks).
- Real TPM hardware, and the owner's passkey approval that arms the marker on a live box (HOST-ACTIONS.md section 4; R1 and R2 write the marker the approval would write).

## 4. Amendment 2026-11-28 (#1118): the recovery key is read from RAM, never from the serial console

Written before the matching change to `data_encrypt.py` and `dataenc.py` was booted anywhere. The recovery key is no longer printed on a serial console by default (CRITERIA-DATAENC.md section 4), so in R2:

- "Old identity" takes the recovery key from `/run/onemind/data-recovery-key` on the first boot, not from the console.
- Instead of "a **new** `RECOVERY KEY` line with eight groups of eight modhex letters that differs from the old key": the fresh first boot prints `ONEMIND-DATA-CRYPT: recovery key made`, `/run/onemind/data-recovery-key` then holds a key of eight groups of eight modhex letters that differs from the old key, and the serial console output after the arming reboot (until the gate commits) contains neither key nor a `RECOVERY KEY` line. All other R2 clauses stay; R1 is unchanged.
