# QEMU battery, btrfs /data (E5-E7): pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 (ET, night of 11-24) for plan PR 5 of the Debian bones ("/data on LUKS2 + btrfs by default"), before E5, E6 and E7 had ever run. Its sha256 is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the harness's `results.json` and CI logs). It adds to, and never edits, `CRITERIA-DATAENC.md` (E1-E4, which keeps its own hash).

**Serves:** IMG-05 (#152), founder decision D-020, `docs/leap/core/IMAGES.md` data layout. Harness: `test/qemu/dataenc.py` (`make dataenc`), which runs E1-E4, then E5-E7 on the same fixtures.

## 1. Starting state and rules

- Image and fixtures: `make fixtures` with the **default** layout, which now ships the data partition **blank** for `x86_64-efi` (no `DATA_FS=luks2` needed). The partition carries OneMind's own type GUID `d6bbb545-ec40-5f2a-9cfe-3c397e4d8112`, not the generic Linux GUID.
- "Layout" means: `/data` mounts the default subvolume `@`; `@storage` is a second subvolume mounted at `/data/storage` (`subvol=/@storage`); `@storage/.snapshots` is a subvolume inside `@storage` (for snapper). There is no top-level `@snapshots`.
- E6 continues the encrypted disk of E1/E2 (software TPM #1). E5 and E7 each start from a **fresh copy** of the fixtures disk (blank data partition), so they do not depend on E1-E4.
- "Marker" means a file of 32 random bytes whose sha256 is compared before and after; "kept" means unchanged. "No failed units" means `systemctl --failed --no-legend` prints nothing after the gate has committed.
- No human input except what a test sends on the serial console. A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| E5 | No TPM, blank data partition, nobody types (the D-020 no-TPM branch) | The console prints `making it plain btrfs, NOT encrypted` and no `RECOVERY KEY` line; the gate commits; the raw data partition's signature is `btrfs` (no LUKS); `/data` is mounted from the partition (not `/dev/mapper`); the default subvolume of `/data` is `@`; `btrfs subvolume list /data` shows `@storage` and `@storage/.snapshots` and no `@snapshots`; `/data/storage` is a mount point of subvolume `@storage`; the partition's type GUID is the OneMind one; a marker written under `/data` and one under `/data/storage` are kept after a reboot with nobody typing; no failed units | A prompt, a recovery key, LUKS on the partition, a different layout, the marker changed, a failed unit, or the box not reaching the gate |
| E6 | Update and rollback keep the encrypted `/data` (TPM #1, the disk of E1/E2) | Install `good` (slot B, version 2): the box commits `mark-good` on B, unlocks with the TPM (`data disk unlocked (tpm2)`) without a prompt, and both markers (`/data` and `/data/storage`) are kept and `/data/storage` is still its own mount. Install `bad-k3s` (version 3) on A: the gate marks it bad and falls back to B; after the fall-back the box unlocks with the TPM again, both markers are kept | A prompt, an unlock other than the TPM, a changed or missing marker, `/data/storage` not mounted, or an update or rollback that does not end on the expected slot |
| E7 | Growth on a large disk, encrypted (TPM #3) | The fixtures disk is enlarged to 64 GiB before the first boot (the image is written to a bigger disk, nothing else changes). After the first boot: the data partition ends within 1 MiB of the last usable sector of the disk, the unlocked LUKS2 volume is at most 32 MiB smaller than the partition (its header), the btrfs filesystem is at least 98 % of the volume, the journal of `onemind-data-extend.service` says it grew the partition, there are no failed units, and a marker is kept after a reboot (unlocked by the TPM) with the sizes unchanged | The partition, the volume or the filesystem still at the build size, the data lost, a failed unit (the growth must not fail the boot), or a prompt |

## 3. What these tests do not cover (reported, never claimed)

- Real TPM hardware, Secure Boot and firmware updates that change PCR 7. The unlock binding is PCR 7 only; the recovery key is the strong fallback. The signed-PCR policy waits for UKIs (the Secure Boot lane).
- The cloud-proxmox board (checked by `cloudboot.py` C4, which now reads btrfs as well as ext4) and a Proxmox VM with a TPM.
- A box installed before this change (ext4 `/data`): it is left as it is (`CRITERIA-DATAENC.md` section 3; the unit tests cover the ext4 and `data-storage.mount` skip).
- Snapshots (snapper): plan PR 6 adds its own checks on top of this layout.

## 4. Amendment (2026-11-25, written before the second growth step of E7 ran)

E7 gets a second half, because the first growth happens on a boot where the volume was opened by the first-boot code, while every later boot opens it with `systemd-cryptsetup` and the TPM: with the box powered off after the checks above, the disk image is enlarged again to 80 GiB. **PASS** needs, after the next boot (unlocked by the TPM, no prompt): the data partition ends within 1 MiB of the last usable sector of the 80 GiB disk, is larger than before, the unlocked volume is at most 32 MiB smaller than the partition, the btrfs filesystem is at least 98 % of the volume, the journal of that boot's `onemind-data-extend.service` says it grew the partition, no unit is failed and the marker is kept. **FAIL**: any size still at the 64 GiB value, a prompt, a failed unit, or the marker changed. The original E7 text above stays as it was; both halves must pass for E7 to pass.
