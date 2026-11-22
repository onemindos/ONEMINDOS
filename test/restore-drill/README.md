<!-- SPDX-License-Identifier: Apache-2.0 -->
# Whole-box restore drill (BAK-02, #163)

**Serves:** BAK-02 and the year-1 exit criterion "whole-box restore onto new hardware in under 60 minutes, green monthly for six months"; builds on BACKUP-WIRE-1 (`test/backup-wire`).

> **In plain words.** A backup you have never restored is a hope, not a backup. This drill plays the worst day: it builds a OneMind box with real data, backs it up to a USB-style disk, then **destroys that box**. A brand-new empty machine gets only two things, the backup disk and the owner key from the emergency kit (what you would still have after a fire). It installs OneMind, restores, and the data is compared byte for byte. A stopwatch runs from "new machine is up" to "data verified". More than 60 minutes, or any wrong byte, and the run goes red.

```sh
python3 -I test/restore-drill/drill.py --results test/restore-drill/results/run.json   # needs KVM, QEMU, cloud-image-utils, Go
```

CI runs it on the first of every month (`.github/workflows/restore-drill.yml`, GitHub's KVM runner, up to 3 hours allowed) and by hand (`workflow_dispatch`). A pull request runs it only when it changes `test/restore-drill/**` or the workflow itself. It is informational like `net-2vm`: it never blocks a merge, but a red monthly run is the signal that the exit criterion is not met. It refuses to count a run without KVM (the timing would mean nothing).

## What runs where

| File | Job |
|---|---|
| `drillcore.py` | The judge. Pure Python, no VM: parses the marker lines, computes the restore clock, decides `PASS`, `OVER_BUDGET` or `FAIL`, writes the step summary. Unit-tested by `test/unit/test_restore_drill.py` (runs on every PR). |
| `in-vm.sh` | The scenario inside a Debian 13 VM, as root. `source` half: install, data, backup, kit. `restore` half: clean install, restore, verify. Prints `DRILL-PHASE`, `DRILL-INFO`, `PASS`, `FAIL` lines. |
| `drill.py` | The host side: builds `onemindd` from the tree, boots the **source** VM, runs the source half, copies out the owner key and the expected hashes, kills the VM, boots a **clean** VM with the same USB disk, runs the restore half, judges. |

## The clock

| Phase | On the clock? | What it covers |
|---|---|---|
| `seed` | no | install, data, backup on the box being protected |
| `install` | yes | `deploy/install.sh --role hub` on the clean machine |
| `restore` | yes | reinstall the app, restore snapshots with the owner key |
| `verify` | yes | file, 256 MiB payload hash, database rows, system snapshot, gateway health |

The VM boot is measured and reported but not counted: the criterion starts when the new hardware is up. The clock is wall time from the first restore phase to the last, so gaps count. Exactly 3600 s passes; 3601 s is `OVER_BUDGET`, and `OVER_BUDGET` exits non-zero. A phase that never finished, a run with no passing check, or an early abort is `FAIL`, never a pass.

## Restore path today, and what changes

`onemind init --restore` (UMB-P08, #145) is not built yet; the gateway refuses a box-scope restore on a running box on purpose. So the drill restores **the way the emergency kit says anyone can**: plain `restic` with the owner key on a freshly installed box (`restore_mode=restic-owner-key` in the results). It restores the app's volume and its `pg_dump`, and the `system` snapshot (audit log, gateway state) to a scratch folder. When UMB-P08 lands, only `restore_box()` in `in-vm.sh` changes; the clock, data and checks stay, and the result's `restore_mode` records which path ran.

## Status

| Date | Run | Result |
|---|---|---|
| (none yet) | The judging core is unit-tested; the VM drill has **not** been run end to end by its author (no KVM runner on the author's machine). The first CI run is the first real timing. | UNVERIFIED |

If the first CI run shows a script bug (the in-VM script is adapted from the proven `test/backup-wire/in-vm.sh`, but the clean-box restore half is new), fix it in `in-vm.sh`; do not loosen `drillcore.py`.

**Not covered yet:** a second node, S3 or box destinations, restoring k3s's own datastore and the gateway database onto the new box (the `system` snapshot is only checked for presence), arm64 hardware.
