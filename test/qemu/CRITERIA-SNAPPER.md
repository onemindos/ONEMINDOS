# QEMU battery, snapshots of the owner's files (E8): pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 (ET) for plan PR 6 of the Debian bones (snapper + btrfsmaintenance), before E8 had ever run. Its sha256 is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the harness's `results.json` and CI logs). It builds on `CRITERIA-DATABTRFS.md` (the `@` / `@storage` / `@storage/.snapshots` layout) and never edits it.

**Serves:** IMG-05 (#152), founder decision D-020 and the Debian-bones plan decision "snapper, not the scheduler of #833". Harness: `test/qemu/dataenc.py` (`make dataenc`), which runs E8 right after E6 on the same encrypted disk (software TPM #1, slot B committed, slot A free).

## 1. Starting state and rules

- The disk is the encrypted one of E1/E2/E6: LUKS2 + btrfs, unlocked by the software TPM. `/data` is subvolume `@`, `/data/storage` is `@storage`, and `@storage/.snapshots` exists inside it.
- "Timeline snapshot" means a directory `/data/storage/.snapshots/<N>/` whose `info.xml` has `<type>single</type>` and `<cleanup>timeline</cleanup>` and whose `snapshot/` is a read-only btrfs subvolume. It must come from the real unit, `systemctl start snapper-timeline.service` (what `snapper-timeline.timer` starts every hour), not from `snapper create`.
- "Payload" means a file `/data/storage/payload.bin` of 1 MiB of random bytes, written and synced before the snapshot; "matches byte for byte" means the sha256 of the copy equals the sha256 taken before the snapshot.
- No human input except what a test sends on the serial console. A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| E8 | Timeline snapshot, restore, scrub, and survival of an A/B update | (a) `snapper-timeline.timer`, `snapper-cleanup.timer` and `btrfs-scrub.timer` are enabled and active, `snapper-boot.timer`, `btrfs-balance.timer`, `btrfs-defrag.timer`, `btrfs-trim.timer` and `btrfsmaintenance-refresh.path` are masked, `snapper --no-dbus list-configs` lists exactly one config, `storage`, for `/data/storage`, and `btrfs-scrub.timer` is `OnCalendar=monthly`; (b) after the payload is written, starting `snapper-timeline.service` ends with Result=success and a new timeline snapshot directory appears; (c) the payload is then changed and a copy of it taken from the snapshot matches the original byte for byte while the live file no longer does; (d) `btrfs-scrub.service` started by hand ends with Result=success and `btrfs scrub status /data` says `finished` with `no errors found`; (e) installing `good` to slot A and rebooting commits `mark-good` on A with the TPM unlock and no prompt, the same snapshot directory is still there with the same `info.xml` and a payload copy from it still matches byte for byte, `snapper --no-dbus -c storage list` still lists it, and no unit is failed | No snapshot, a snapshot of `/data` or of the k3s data (anything but `storage`), a snapshot whose payload differs, a scrub that fails or finds errors, a snapshot lost or changed by the update, a prompt, or a failed unit |

## 3. What this test does not cover (reported, never claimed)

- That a snapshot is a backup: it is on the same disk and the same TPM-bound LUKS2 volume as the data. restic and the app dumps are the backups.
- Cleanup (`snapper-cleanup.service`) after weeks of timeline snapshots: the limits are in the config and checked by a unit test; no QEMU run lasts that long.
- A scrub that finds and repairs a damaged block: one disk has no second copy, so the scrub can only report.
- Real hardware, Secure Boot and the PCR 7 binding of the unlock (see `CRITERIA-DATABTRFS.md` section 3).
