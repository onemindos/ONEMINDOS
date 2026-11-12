<!-- SPDX-License-Identifier: Apache-2.0 -->
# Storage safety: umbrelOS study and the OneMind design

**Status:** study and design for build agents (2026-11-12). Not built. Branch `feat/umbrel2-study`.
**Source studied:** umbrelOS tag `2.1.0-beta.1`, commit `6f357e18d0a4`, read-only. All umbrel paths below are relative to that tree.
**Founder focus served:** storage safety, backups, devices, AI agents via MCP (agents request, owner approves), deployments that never fail.

> **Explain it like I am the founder**
> umbrelOS keeps your data on ZFS. If you put two drives in, it can mirror them ("FailSafe"), check them every month, show each drive's temperature and wear, and if the drives cannot be mounted at boot it shows a rescue screen instead of a broken box. It is good work, and it is heavily tested in virtual machines.
> It also has gaps: the data is "encrypted" with a passphrase that is the same on every box, ZFS is an out-of-tree kernel module that holds back kernel updates, drives of different sizes waste space, USB disks and the Raspberry Pi get no protection, nothing warns you before a drive dies, and agents cannot see any of it.
> OneMind will use **btrfs mirroring inside LUKS2 encryption** on the existing `onemind-data` partition, plus the disks you add. It is part of the Linux kernel (no extra module, works with Secure Boot), handles mixed sizes, can add, replace and remove disks while running, and checks every block. Every disk-changing step is an action the owner approves with a passkey; agents can read health and ask, never do.

**Legal rule for this page.** umbrelOS is PolyForm Noncommercial 1.0.0 (checked at the tag above). This page describes umbrel's architecture and cites paths so reviewers can check claims. It copies no code, strings, UI text or assets, and no OneMind implementation may be derived line by line from umbrel's source. Every component OneMind ships is listed in §4.1 with its licence.

---

## 1. How umbrelOS does it

### 1.1 Technology in one table

| Concern | umbrel choice | Where |
|---|---|---|
| Base OS | Debian 13 (trixie) image built in a pinned Docker build; Rugix A/B system slots with a separate config partition and data partition | `packages/os/umbrelos.Dockerfile`, `packages/os/rugix/**` |
| Filesystem and RAID | **OpenZFS** (`zfs-dkms`, `zfsutils-linux` from trixie, built by DKMS into the image). No mdadm, no btrfs | `packages/os/umbrelos.Dockerfile` (ZFS install block, ~lines 150–190) |
| Pool topologies | `stripe` ("storage" mode, no redundancy), `raidz` (SSD FailSafe), `mirror` pairs (HDD FailSafe) | `packages/umbreld/source/modules/hardware/raid.ts` (`RaidType`, `Topology`, ~line 38) |
| HDD acceleration | One SSD (two in FailSafe) split into an L2ARC read-cache partition and a ZFS *special* vdev for metadata and small blocks | `raid.ts` `#partitionAcceleratorDevice` (~1370), `#addAccelerator` (~1763) |
| Encryption | ZFS native `aes-256-gcm` on the `data` dataset, with a **fixed passphrase that is the same on every box**. The code comments say this gives no security and only exists so real encryption can be switched on later without a data migration | `raid.ts` `#createDataset` (~1471), `packages/os/overlay/opt/umbrel-data/umbrel-data-mount` |
| Drive naming | A udev rule creates a stable namespace `/dev/disk/by-umbrel-id/<ID_SERIAL>[-partN]`; pools are always imported through it | `packages/os/overlay/etc/udev/rules.d/99-umbrel-disk-by-id.rules` |
| Drive health | `smartctl -a --json` per disk (temperature, overall SMART pass, NVMe `percentage_used`), `nvme id-ctrl` for vendor warning/critical temperature thresholds, PCIe slot numbers via `lspci` on their own hardware | `packages/umbreld/source/modules/hardware/internal-storage.ts` (`getSmartData` ~63, `getNvmeTemperatureThresholds` ~94, `isInternalStorageDisk` ~187) |
| Which disks qualify | Allowlist of transports `nvme`, `sata`, `sas`; **USB, iSCSI and unknown transports are excluded**; disks that back the running system are flagged and refused | `internal-storage.ts` (~181–190, ~293), `raid.ts` `#assertNotSystemDrives` (~1627) |
| API | tRPC router `hardware.raid.*`, `hardware.internalStorage.getDevices`, `hardware.gpu.getInfo`; owner session only (some read routes are public before a user exists, for onboarding and recovery) | `packages/umbreld/source/modules/hardware/routes.ts` |
| Tests | About 50 QEMU "vm" tests that build real pools and pull, replace, swap and resize drives, plus unit tests | `packages/umbreld/source/modules/hardware/*.vm.test.ts` |

### 1.2 Architecture and data flow

```
 boot:  firmware → Rugix init ──► mount-script (umbrel-data-mount) ──► root overlay ──► systemd ──► umbreld
                                   │ reads raid.* from the read-only config partition (YAML)
                                   │ waits ≤30 s for listed devices (starts udev itself if one is late)
                                   │ finishes an interrupted FailSafe migration (send/receive + pool rename)
                                   │ zpool import (by-umbrel-id, no cachefile, forced) → load key → mount data dataset
                                   │ write test: an unwritable pool counts as a failure
                                   └─ on failure: Rugix boots with an in-memory data overlay and writes an error log
 run:   umbreld hardware.raid ──► zpool/zfs CLI (JSON status) ──► 1 s monitor ──► event bus (progress, status change)
                                                              └─► daily tick ──► monthly scrub ──► notification on errors
 UI:    Settings → Storage Manager (tRPC queries + events)      /raid-error route when the mount-error log exists
```

Key points, each checked in the source:

1. **Boot ownership is outside the daemon.** The pool is imported by a shell script that Rugix runs before the root overlay exists (`packages/os/rugix/recipes/setup-rugix/files/system.toml` sets the mount script and pins "do not fail init on mount error"). The pool's dataset is mounted where the default data partition would be. With no RAID config, the script fscks and mounts the ordinary data partition.
2. **Pool configuration lives on the read-only config partition**, remounted read-write only for each write with retries, and a copy is mirrored onto the pool so a reflashed boot disk can find and re-adopt an old pool (`raid.ts` constructor ~447–505, `hasRecoverableInstall` / `recoverExistingInstall` ~1217–1300: read-only import, load key, read the copied config, export).
3. **Every pool mutation is serialised** by an in-memory reservation (`#withPoolMutation` ~508) and scrubs are refused while any mutation, rebuild or expansion runs (`getScrubConflict` ~101).
4. **Partitioning:** each member gets a GPT with a small reserved partition and a data partition whose size is rounded **down** into buckets (250 GB steps above 1 TB, 25 GB steps above 250 GB) so "the same size" drives from different vendors fit together (`getRoundedDeviceSize` ~29, `#partitionDevice` ~1307). Pools are created with `ashift=12`, `autotrim`, `autoexpand`, no cachefile and a **pinned feature set (`compatibility=openzfs-2.3`) so an OTA rollback can still import the pool** (`#createPool` ~1444). The dataset uses lz4, `atime=off`, POSIX ACLs and a legacy mountpoint.
5. **Growing:** SSD raidz grows one disk at a time with OpenZFS raidz expansion (`zpool attach` to the raidz vdev); stripes grow with `zpool add`; HDD mirrors grow by pairs (`addDevice` ~1649, `addMirror` ~1700).
6. **Single SSD to FailSafe without a spare disk** (`transitionToFailsafeRaidz` ~2040): build a raidz1 from the new disk plus a sparse temporary file, offline the file (a deliberately degraded pool), `zfs send --raw` a snapshot across while the box runs, then on the next boot the mount script sends the final increment and swaps pool names with a rollback path; after boot the daemon replaces the missing member with the old disk and waits for the resilver (`#completeFailsafeTransition` ~2444). The HDD path attaches a new disk to each existing one (`transitionToFailsafeMirror` ~2222).
7. **Replace** uses `zpool replace` (also in place for a same-slot swap), then `zpool online -e` to grow (`#replaceStorageDevice` ~1875).
8. **Space accounting is computed by hand** because OpenZFS reports the old parity ratio after raidz expansion (comment block in `getPoolStatus` ~763–1050 cites OpenZFS issue 17784).
9. **Memory:** the daemon lowers the ZFS ARC minimum and raises `zfs_arc_sys_free` at start so ZFS gives memory back to apps sooner (`start` ~550).
10. **Monitoring:** a 1-second poll of `zpool status --json` turns into events (expansion, resilver, scrub progress, a status-signature change) and a persistent notification when a scrub finishes with errors. The scrub deadline (30 days) is persisted so restarts do not reset it (`ensureScrubSchedule`, `runScrubSchedulerTick` ~127–185, `#startPoolMonitor`).
11. **Recovery mode:** `checkRaidMountFailure` is simply "does the Rugix mount-error log exist"; `checkRaidMountFailureDevices` runs a dry `zpool import` and marks which configured members are visible and online (~1201–1215).

### 1.3 GPU detection (same module)

`packages/umbreld/source/modules/hardware/gpu.ts` lists every PCI display controller (class `03xx`, not only `0300`, so APUs reporting `0380` are found), then detects three additive acceleration paths: DRI render nodes (Intel/AMD video and Vulkan), KFD plus DRI (ROCm), and NVIDIA via the container toolkit (probing `nvidia-smi` so hot-plugged eGPUs work). It patches each app's compose service with only the devices and groups it adds, and records them so a later probe can remove exactly those additions. `gpu-usage.ts` derives per-process GPU use from DRM `fdinfo` and `nvidia-smi pmon`. Thunderbolt device authorisation is a separate owner-only router (`thunderbolt.ts`).

### 1.4 What the user sees

- **Onboarding:** on hardware with several internal drives the user picks drives and a mode (`packages/ui/src/routes/onboarding/raid/**`, `.../hdd-raid/**`). Setup partitions the drives, creates the pool, stores the account details temporarily and **reboots into the new pool**; the account is created on the first boot from the pool and the temporary password is wiped from the config (`triggerInitialRaidSetupBootFlow` ~1125, `handlePostBootRaidSetupProcess`).
- **Storage Manager** (`packages/ui/src/features/storage/**`, ~10k lines): drive cards (slot pictures on their Pro hardware), capacity donut, mode display, per-drive health dialog (temperature, wear, SMART, ZFS error counters with a red/amber severity rule in `components/ssd-warnings.ts`), dialogs for add drive, enable FailSafe, add mirror pair, add accelerator, swap and replace failed drive, and a floating progress indicator driven by the events in §1.2.
- **Recovery screen** (`packages/ui/src/routes/raid-error/index.tsx`, route registered in `packages/ui/src/router.tsx`): shown when the pool did not mount; lists configured and detected drives with health, and offers retry, restart, shut down and factory reset.

### 1.5 Strengths and gaps (our assessment)

| Strengths to match | Gaps OneMind can beat |
|---|---|
| Checksumming filesystem with self-heal on redundant members | Encryption is cosmetic: one public passphrase on every box (§1.1) |
| Boot never bricks on a bad pool; a recovery screen instead | ZFS is out-of-tree (CDDL): DKMS build in the image, the kernel version is capped by the ZFS release (Dockerfile comment), module signing needed for Secure Boot |
| Write test after mount catches "imported but read-only" | "Storage" mode with 2+ drives is a stripe: one dead drive loses everything |
| Stable disk naming; foreign-pool safety (random pool suffix) | Size rounding wastes capacity; raidz/mirror use the smallest member |
| Online single-disk → redundant conversion | USB disks excluded; the Raspberry Pi image gets no redundancy at all |
| Monthly scrub with persisted deadline and error notification | No proactive SMART, temperature or wear alerts (only scrub errors notify) |
| Pinned pool feature set so rollback still imports | No snapshots offered to the user (ZFS snapshots are only used for migration) |
| Large QEMU test battery for every drive scenario | MCP has no storage tools; storage changes have no approval or audit trail; one tRPC mutation (`raid.setup`) is marked in code as a development leftover |

---

## 2. What OneMind has today

| Piece | Path | State |
|---|---|---|
| Disk layout contract (ESP, boot A/B, system A/B read-only, recovery, `onemind-data` = rest, ext4) | `os/boards/x86_64-efi/layout.yaml`, `os/boards/arm64-efi/layout.yaml`, `os/boards/vm-do/layout.yaml` | On `main`. Comment: "LUKS2 planned (SB-5)" |
| Image assembly: `mke2fs -t ext4 -L onemind-data` | `os/assemble/assemble.py` (`cmd_disk`) | On `main` |
| RAUC A/B slots (ext4, verity bundles only) | `os/rauc/system.conf.in` | On `main` |
| Data grow at first boot (droplets) | `os/boards/vm-do/rootfs/usr/lib/systemd/system/onemind-data-grow.service` | On `main` |
| Node disk facts: `statfs` total/free only | `internal/detect/disk_unix.go` | On `main` |
| Disk meter on the node card | `ui/src/components/NodeCard.tsx`; IA in `docs/design/IA.md` | On `main` / `feat/ui-leap` |
| Retain StorageClass `onemind-local` on `/data/onemind/storage`; restic backups, pre-update snapshot | `docs/architecture/BACKUPS.md`, `docs/leap/core/BACKUPS.md` (CORE-BACKUP-1…8), `internal/update/` | Spec; updater merged (#15) |
| LUKS2 on `onemind-data`, TPM2 unlock, recovery key shown once | `docs/leap/core/SECURITY.md` (CORE-SEC-5) | Spec |
| GPU: NVIDIA detection only; toolkit and device plugin planned | `docs/leap/core/DOGFOOD.md` §4.4 (CORE-DOGFOOD-5) | Spec |
| Storage daemon branch | `feat/onemindd-storage` | Branch cut, **no commits** |
| Raspberry Pi 5 | `docs/HARDWARE.md` (bake-off board, Edge tier) | No `rpi` board directory yet |

So OneMind today has **one disk, one ext4 data partition, no redundancy, no health data, no encryption yet**. The good news: the A/B read-only root and a single labelled data partition are exactly the shape this design needs; nothing in the slot layout has to change.

---

## 3. Match and beat

| Area | Match umbrel | Beat umbrel |
|---|---|---|
| Integrity | Checksums on every block, monthly scrub, self-heal from the mirror copy | Scrub results, corrected-error counts and per-device error counters feed alerts *and* the audit log |
| Redundancy | Turn one disk into a mirror while running; replace a failed disk; recovery screen when data will not mount | Never offer a multi-disk stripe; mixed sizes count fully (btrfs raid1 uses `min(total/2, total − largest)`); remove a disk online when space allows |
| Encryption | – | Real LUKS2 on every member, TPM2 unlock where present, one recovery key for the whole set, shown once (CORE-SEC-5) |
| Kernel and boot | Pinned on-disk format so rollback still mounts | In-kernel filesystem: no DKMS, no kernel cap, Secure Boot and signed UKIs unaffected; RAUC rollback is always safe because data features are pinned (§4.6) |
| Health | Temperature, wear, SMART status, NVMe thresholds | Proactive alerts with trends (wear rate, reallocated/media errors, temperature excursions), USB disks supported (with UAS quirks recorded), "this disk is the one to replace" by bay, model and serial tail |
| Snapshots | – | Read-only btrfs snapshot before each app update and OS update (instant local undo), and restic backs up from a snapshot so backups are crash-consistent (BACKUPS.md) |
| Hardware reach | x86 boxes with internal drives | Same on Raspberry Pi 5 (dual-NVMe HAT, or NVMe + USB SSD) and VMs; multi-node: each node reports its own storage to the hub |
| Agents and safety | – | MCP read tools for storage health; every disk-changing step is an owner-approved action with a computed plan (which disk is wiped, by serial), passkey step-up, audit entry |
| Testing | QEMU battery for each drive scenario | Same battery in `test/qemu/`, plus power-cut tests during convert/replace and a Pi lab run |
| Not matched in v1 | HDD + SSD acceleration (L2ARC + special vdev) | Deferred (STOR-12); btrfs has no tiering, so this needs bcache or dm-cache and a separate decision |

---

## 4. OneMind design

### 4.1 Filesystem decision (Debian 13)

| Criterion | **btrfs raid1** | mdadm RAID1 + ext4 | OpenZFS mirror/raidz |
|---|---|---|---|
| Licence and delivery | GPL-2.0, in the kernel | GPL-2.0, in the kernel | CDDL-1.0, out-of-tree; Debian ships it as DKMS source in `contrib`. Shipping a prebuilt module in a commercial image needs legal review |
| Secure Boot, signed UKIs, verity root | Nothing extra | Nothing extra | Module must be built and signed for every kernel; a kernel update can be blocked by the ZFS release (umbrel's Dockerfile documents this cap) |
| Silent corruption | Detected and repaired from the good copy | **Not detected**: mdadm cannot tell which copy is right (dm-integrity fixes this at a write cost) | Detected and repaired |
| Mixed disk sizes | Uses the space (raid1 chunk allocator) | Smallest member | Smallest member |
| Add / replace / remove online | All three; profile conversion online (`balance -dconvert`) | Add and replace; shrink is awkward | Add and replace; removal limited, raidz members cannot be removed |
| Parity RAID (5/6) | **Not safe; never offered** | Yes | raidz, safe |
| Snapshots, send/receive | Yes (subvolumes) | No (needs LVM thin) | Yes |
| RAM | Low | Low | ARC wants memory; umbrel tunes it down |
| Degraded boot | Needs an explicit `degraded` mount option (we control it, §4.4) | Automatic | Automatic |
| Raspberry Pi 5 | Raspberry Pi kernel builds btrfs (UNVERIFIED; checked in STOR-10) | Fine | DKMS against the Raspberry Pi kernel on every update; RAM pressure on 8 GB |

**Decision:** `onemind-data` becomes **btrfs inside LUKS2**. One disk: profile `single` data, `dup` metadata. Two disks: `raid1` data and metadata. Three or more: `raid1` data, `raid1c3` metadata. RAID5/6 profiles are refused by code. mdadm is rejected (no integrity). ZFS is rejected for v1; it can come back later only as an optional large-HDD "NAS tier" needing parity, after a licence review (recorded in `docs/DECISIONS.md` when STOR-0 lands).

Components (all already in Debian 13; exact versions are pinned in `os/versions.lock.yaml` by STOR-1, values below are trixie candidates, UNVERIFIED until checked against the image snapshot):

| Component | Use | Licence | Candidate pin |
|---|---|---|---|
| Linux btrfs, dm-crypt | Filesystem, encryption | GPL-2.0 | the image kernel |
| btrfs-progs | `mkfs`, `device add/remove/replace`, `balance`, `scrub` | GPL-2.0 | 6.14 (trixie) |
| cryptsetup | LUKS2 format/open, LUKS2 tokens | GPL-2.0-or-later | 2.7.5 (trixie) |
| systemd (`systemd-cryptenroll`, `systemd-cryptsetup`, udev) | TPM2 enrolment, initrd unlock, stable device links | LGPL-2.1-or-later | 257 (trixie) |
| smartmontools (`smartctl --json`) | SMART, temperature, wear | GPL-2.0-or-later | 7.4 (trixie) |
| nvme-cli | NVMe thresholds and health log | GPL-2.0-only | 2.13 (trixie) |
| util-linux (`lsblk --json`, `wipefs`) | Inventory, signature checks | GPL-2.0-or-later | 2.41 (trixie) |
| gdisk (`sgdisk`) | Partitioning new members | GPL-2.0-or-later | 1.0.10 (trixie) |
| pciutils (`lspci`) | GPU and slot detection | GPL-2.0-or-later | 3.13 (trixie) |

All are run as separate processes by `onemindd` (no linking), and all ship in Debian main.

### 4.2 Layout and volumes

```
system disk:  esp | boot-a | boot-b | system-a (ro) | system-b (ro) | recovery | onemind-data ── LUKS2 ── btrfs member 1
added disk:   GPT: onemind-data (whole disk) ── LUKS2 ── btrfs member 2
btrfs (one filesystem, label onemind-data):
  @           → /data              (onemindd state, secrets, k3s datastore)
  @storage    → /data/onemind/storage   (onemind-local PVs: one subvolume per PV)
  @snapshots  → /data/.snapshots   (read-only snapshots, pruned by policy)
```

- The **slot layout does not change**: `onemind-data` keeps its label; only `fs: ext4` becomes `fs: btrfs` with LUKS2 below it (merged with CORE-SEC-5 so the image is formatted once).
- Added disks get one partition labelled `onemind-data` (GPT partlabel), so `/dev/disk/by-partlabel` finds them and nothing depends on `sdX` order. Device identity in our records is the **WWN or serial** (as udev's `ID_WWN`/`ID_SERIAL`), never the kernel name.
- **One subvolume per PersistentVolume**: the local-path provisioner supports custom setup/teardown scripts in its ConfigMap; ours creates a subvolume instead of a directory. That gives per-app snapshots for app-update rollback without touching other apps.
- Copy-on-write stays on (checksums need it). Only VM disk images (later, if VMs ship) get `nodatacow`, and the UI says those files lose self-heal.
- Mount options: `noatime,compress=zstd:1,space_cache=v2,discard=async`.

### 4.3 Where the storage set is recorded (no new partition)

umbrel needs a config partition to know which disks to import before data is mounted. OneMind avoids a new partition: **each member's LUKS2 header carries a OneMind token** (LUKS2 supports JSON tokens in the header):

```json
{"type": "onemind-storage", "keyslots": [], "set_uuid": "<btrfs fsid>", "member": 2, "members": 2, "profile": "raid1", "generation": 7}
```

The initrd reads tokens from every LUKS2 device labelled `onemind-data`, picks the set whose `set_uuid` matches the system disk's member, and knows how many members to wait for. `generation` increments on every membership change so a stale disk from an older set (or another box) is never mixed in; a disk from another OneMind box is reported as **foreign** and left alone.

### 4.4 Boot and mount (never brick, never guess)

A systemd unit in the initrd (`onemind-data-assemble`, shipped by the image stream):

1. Unlock the system-disk member (TPM2 policy where present, else passphrase prompt; recovery key always works).
2. Read its token; wait up to 30 s for the other members (late SAS/USB disks), unlocking each with the same mechanism. Each member is enrolled with the same TPM2 policy and the same recovery passphrase, so one key opens the set.
3. `btrfs device scan`, then mount:
   - all members present → normal mount;
   - one member missing **and** the profile still has a full copy (raid1 with ≥2, raid1c3 with ≥3) → mount `degraded`, write the marker `/run/onemind/storage/degraded`, continue booting;
   - otherwise → do **not** mount. Boot continues with `/data` on tmpfs and the marker `/run/onemind/storage/unavailable`, and `onemindd` starts in **storage recovery mode** (§4.8). k3s does not start on tmpfs data.
4. **Write test** after mount (create, fsync, remove a file in `@`); a read-only mount counts as unavailable.
5. After boot, if the set was degraded and the member returns, `onemindd` runs `btrfs scrub` and a `balance -dconvert=raid1,soft -mconvert=raid1,soft` to rewrite any chunks created while degraded (btrfs writes `single` chunks during a degraded read-write mount; this step is mandatory, not optional).

### 4.5 Operations (all journaled, all resumable)

Every operation is a journal row in `/data/onemind/storage/ops.db` (SQLite) with ordered steps; `onemindd` resumes or rolls back after a crash or power cut at any step. Steps per operation:

| Operation | Steps (simplified) | Rollback point |
|---|---|---|
| **Protect** (1 → 2 disks) | check disk is not system/foreign, show plan → wipe signatures → GPT + partlabel → LUKS2 format + enrol TPM2 + recovery key slot + token → `btrfs device add` → `balance -dconvert=raid1 -mconvert=raid1` → bump `generation` in all tokens | Until the balance starts, removing the new device restores the old state; the balance itself is restartable |
| **Add** (n → n+1, already raid1) | as above, then `balance` with `-dusage` filters to spread new writes | same |
| **Replace** (failed or healthy) | prepare new disk → `btrfs replace start <devid> <new>` (works with the old disk missing) → resize to the new size → convert-soft balance → update tokens | `replace cancel` before completion |
| **Remove** (shrink) | refuse if the remaining disks cannot hold the data with the profile; refuse below 2 members if protection would be lost unless the owner chose "unprotect" → `btrfs device remove` (moves data) → wipe LUKS header of the removed disk on request | the remove itself is restartable |
| **Scrub** | `btrfs scrub start -B`; record corrected/uncorrectable errors | none needed |
| **Separate disk** | a disk not in the set, formatted LUKS2 + btrfs single, mounted under `/data/volumes/<id>`; usable as a backup target (BACKUPS.md `usb` destination) | – |

One operation at a time per node (a lock file plus the journal); scrubs are skipped while any operation, balance or replace runs, and rescheduled.

### 4.6 Rollback safety with A/B

RAUC can boot the previous slot. The data filesystem must stay mountable by the **oldest kernel and btrfs-progs that a supported rollback can reach**. Rule: the image records `storage.features` (the btrfs feature flags it creates, from `mkfs.btrfs -O list-all` minus anything newer than the floor) in `os/versions.lock.yaml`; `onemindd` never enables a new btrfs feature (`btrfstune`, new `-O` flags) until the update that introduces it is committed and the previous slot is also on a version that supports it. This is the btrfs counterpart of umbrel's pinned `compatibility=openzfs-2.3`.

### 4.7 Health monitoring

`onemindd` collects every 10 minutes (and on demand):

| Source | Fields |
|---|---|
| `lsblk --json -b -O` | id (WWN or serial), model, size, rotational, transport (`nvme`, `sata`, `sas`, `usb`), removable, partitions, role |
| `smartctl -a --json` (USB with `-d sat` fallback) | SMART pass, temperature, power-on hours, NVMe `percentage_used`, `media_errors`, `available_spare`; ATA reallocated/pending/uncorrectable counts |
| `nvme id-ctrl --output-format=json` | vendor warning and critical temperatures |
| `/sys/fs/btrfs/<fsid>/devinfo/<devid>/error_stats` and `btrfs device stats` | read, write, flush, corruption, generation errors per member |
| `btrfs scrub status -R` | last scrub time, bytes, corrected and uncorrectable errors |
| `/sys/fs/btrfs/<fsid>/allocation` | raw, usable and free space per profile |

Alert rules (NOTIFICATIONS.md severities; thresholds are settings): SMART fail → critical; uncorrectable scrub error → critical; any new corruption/write error on a member → warning, critical if it repeats within 24 h; NVMe wear ≥ 80 % → warning, ≥ 95 % → critical, plus a projected "replace by" month from the wear trend; temperature above the vendor warning for 10 minutes → warning, above critical → critical; degraded → critical until repaired; free space < 10 % → warning (btrfs needs headroom for balance). Each alert names the disk by bay or port, model and the last four characters of its serial.

### 4.8 API, CLI and MCP surface

Same style as `docs/leap/dev/API.md`: reads are direct, every change is an **action** with a computed plan (`effects`, `plan_sha256`) that the owner approves. Lands through a contract PR (STOR-0); names below are proposals for that PR.

**Reads**

| Route | Returns | Scope |
|---|---|---|
| `GET /v1/storage` | per node: set (`set_uuid`, `profile_data`, `profile_meta`, `state`: `protected` \| `unprotected` \| `degraded` \| `repairing` \| `unavailable`, capacity, last/next scrub, running operation) | `storage:read` |
| `GET /v1/storage/devices?node_id=` | devices with role (`system-member`, `member`, `separate`, `backup-target`, `unused`, `foreign`), health, error counters | `storage:read` |
| `GET /v1/storage/devices/{id}` | one device with health history (30 days) | `storage:read` |
| `GET /v1/storage/operations/{id}` | journal state, step, progress, ETA | `storage:read` |

**Action types** (added to API.md §5.12 by the contract PR)

| Type | Class | Params | Who may request |
|---|---|---|---|
| `storage.scrub` | write | `{node_id}` | owner, agent, automation |
| `storage.protect` | destructive (wipes the new disk) | `{node_id, device_id}` | owner, agent |
| `storage.device.add` | destructive | `{node_id, device_id}` | owner, agent |
| `storage.device.replace` | destructive | `{node_id, old_device_id, new_device_id}` | owner, agent |
| `storage.device.remove` | destructive | `{node_id, device_id, unprotect?}` | owner |
| `storage.volume.create` | destructive | `{node_id, device_id, use: data \| backup-target}` | owner |
| `storage.settings` | sensitive | `{scrub_interval_days, alert_thresholds}` | owner |

The plan for any wiping action lists the disk's model, size, serial tail, bay/port, and any filesystem signatures found on it ("this disk holds an ext4 filesystem labelled …"). `plan_sha256` binds that exact disk, so swapping a cable after approval makes the action fail with `stale_precondition`. Destructive types need the owner's passkey step-up and are never covered by standing approvals. Agents can request; only a person owner approves.

**Node side:** `onemindd` exposes the operations on its local socket only; the gateway dispatches approved actions to it. The heartbeat gains an optional `storage` summary (`state`, `free_bytes`, `alerts`), via the same contract PR.

**CLI** (`cmd/onemind/cli/storage.go`): `onemind storage status`, `onemind storage disks`, `onemind storage scrub`, `onemind storage protect <disk>`, `add`, `replace <old> <new>`, `remove <disk>`. Wiping commands file the action and ask the operator to type the disk's serial tail; they print the action id and wait for approval.

**MCP** (`docs/leap/dev/MCP.md` catalog): read tools `get_storage_status` and `list_storage_devices` (`storage:read`); `preview_action` and `request_action` accept the `storage.*` types; a prompt `diagnose_storage` (read-only: status, alerts, last scrub, which disk to replace and why). No storage tool can approve or run anything.

### 4.9 UI screens (OneMind's own design system, `docs/design/**`)

1. **Settings → Storage** (per node; the hub shows all nodes): a status headline (Protected / Not protected / Needs attention / Repairing) with one sentence of why; capacity bar showing used, free and "space if mirrored"; a list of disks with bay or port, model, size, temperature, wear and a health dot; a running-operation strip with progress and ETA.
2. **Disk detail:** health with 30-day temperature and wear sparklines, error counters, SMART summary, "replace by" estimate, actions (Replace, Remove, Use as backup disk).
3. **Protect my data** flow: shown when an unused disk appears on an unprotected set; explains in plain words what mirroring gives and costs, shows the plan, ends on the approval card.
4. **Approval card** (shared component): the plan with the disk picture, the wipe warning, passkey step-up.
5. **Storage recovery** (served by `onemindd` in recovery mode, also reachable on the mobile app): which disks were expected, which are present, unlocked or missing, the boot log excerpt, and actions: retry, shut down, mount degraded read-only to copy data out, start a restore from backup (BACKUPS.md §7.3). Factory reset is **not** on this screen; it lives in the rescue system with its own confirmation.
6. **Node card** (`ui/src/components/NodeCard.tsx`): adds the storage state pill next to the disk meter.

All text is OneMind's own; nothing is taken from umbrel's UI.

### 4.10 Security

- **Encryption at rest on every member** (LUKS2, aes-xts-plain64, argon2id); TPM2 unlock bound to PCR 7 and the signed PCR 11 policy (SECURITY.md); the recovery key is the same for all members of a set and part of the emergency kit (BACKUPS.md §5).
- **Disk-wiping is never automatic.** No code path formats a disk without an approved action whose plan names it; foreign OneMind sets and disks with signatures are flagged in the plan.
- **System disk protection:** the system disk's slots, ESP and recovery partitions are never offered; `onemind-data` on the system disk can only be a member, never wiped.
- **Least privilege:** storage commands run inside `onemindd` (root); the gateway never runs shell commands and never receives key material. Serial numbers are shown in full only to owners; agents see the last four characters.
- **Audit:** every operation start, step and result is an audit event (`storage.*`), including scrub results.
- **Threat entries** for `docs/security/THREAT-MODEL.md` (owned by that stream): evil disk (malicious filesystem image auto-mounted: we never auto-mount unknown filesystems, and separate volumes are only mounted after the owner adopts and reformats them); disk swap attack (`plan_sha256` binding); stolen disk (LUKS2).

### 4.11 GPU detection (same hardware area)

Match umbrel's breadth inside the fabric's capability model: `internal/detect` reports every PCI display controller (class `03xx`), `/dev/dri` render nodes, `/dev/kfd`, and NVIDIA through `nvidia-smi`. Labels (owned by CORE-FABRIC-4): `onemind.io/gpu=nvidia|amd|intel`, `onemind.io/gpu.compute=cuda|rocm|none`, `onemind.io/gpu.video=vaapi|nvenc|none`. Apps never map devices themselves (SANDBOX); the executor adds the device plugin resource (`nvidia.com/gpu`, `amd.com/gpu`, `gpu.intel.com/i915`) when `requires.gpu` is set, which beats umbrel's compose patching on isolation. The vendor device plugins are permissive (Apache-2.0); exact versions are pinned by CORE-DOGFOOD-5.

### 4.12 Raspberry Pi 5 feasibility

| Option | Redundancy | Notes |
|---|---|---|
| Single NVMe on a HAT | none (`single`/`dup`) | Encrypted, checksummed, snapshots; corruption detected but not repaired. UI says "Not protected" and suggests a second disk |
| Dual-NVMe HAT (PCIe switch on the single lane) | raid1 | Both disks share one PCIe lane: throughput roughly halves on writes, fine for a home box. **Recommended Edge configuration** |
| NVMe + USB 3 SSD | raid1 | Works; USB bridges vary (UAS resets, missing SMART passthrough). Bridge model recorded; known-bad bridges refused |
| SD card as system disk | – | Not supported for `onemind-data`; system on NVMe |

CPU cost: AES on the Pi 5 has ARMv8 crypto extensions, so LUKS2 at NVMe-over-one-lane speeds is not the bottleneck; zstd:1 compression is cheap. Power cuts are the main Pi risk: btrfs copy-on-write keeps the filesystem consistent, and the operation journal makes convert/replace resumable. A Pi board directory (`os/boards/rpi5/`) does not exist yet; STOR-10 measures all of this before we promise it.

---

## 5. Epics

New stream **Storage** on branch `feat/onemindd-storage` (already cut, empty) and follow-up branches `feat/storage-<slug>`. It owns `internal/storage/**`, `core/onemind_core/storage.py`, `dashboard/src/pages/Storage.tsx`, `cmd/onemind/cli/storage.go` (a group only this spec defines, so the core branch writes it, WORKSTREAMS §3), `test/qemu/storage-*`. Hotspots follow WORKSTREAMS §4: one line each in `cmd/onemindd/main.go`, `core/onemind_core/routes.py`, `dashboard/src/App.tsx`, `cmd/onemind/cli/root.go`; one ledger migration; pins in `os/versions.lock.yaml`; `os/**` pieces merged by the image stream (as for LUKS2 and GPU).

| ID | Title | Size | Owner paths | Depends on | Acceptance test |
|---|---|---|---|---|---|
| STOR-0 | Contract PR: storage reads, `storage.*` action types, heartbeat `storage` object, `storage:*` scopes; decision record (btrfs, no ZFS in v1) | S | `sdk/contracts/poc-v0.md` (contract owner), `docs/DECISIONS.md` | contract 12-a | Contract merged; OpenAPI export lists the routes; schema test validates a sample heartbeat with and without `storage` |
| STOR-1 | Image: `onemind-data` as LUKS2 + btrfs with `@`, `@storage`, `@snapshots`; tools pinned | M | image stream: `os/boards/*/layout.yaml`, `os/assemble/**`, `os/rootfs/packages/*`, `os/versions.lock.yaml` | CORE-SEC-5 (lands together) | QEMU: fresh image boots, `/data` is btrfs on dm-crypt, `findmnt` shows the three subvolumes, `cryptsetup luksDump` shows the TPM2 and recovery slots |
| STOR-2 | Initrd assembly and recovery mode markers (§4.3, §4.4) | M | image stream: `os/rootfs/layers/base/**` (initrd unit), `internal/storage/token/**` | STOR-1 | QEMU: (a) both members → normal; (b) one member detached → boots degraded, marker present, alert raised; (c) both missing → boots with tmpfs `/data`, k3s not started, recovery screen served; (d) member re-attached → scrub and soft convert run, no `single` chunks remain (`btrfs filesystem df`) |
| STOR-3 | `onemindd` storage inventory and health collector | M | `internal/storage/{inventory,health}/**`, one line in `cmd/onemindd/main.go` | STOR-0 | Unit tests parse recorded `lsblk`, `smartctl` (NVMe, SATA, USB-SAT) and `nvme` JSON fixtures; system/foreign roles correct; on a QEMU VM the heartbeat carries `storage.state=unprotected` |
| STOR-4 | Operation engine: protect, add, replace, remove, scrub, separate volume; journal, lock, resume | L | `internal/storage/ops/**`, `internal/storage/socket.go` | STOR-2, STOR-3 | QEMU battery: each operation completes; **power cut injected at every step** (VM reset) resumes or rolls back with data intact (checksummed test corpus); a second operation while one runs is refused; scrub during balance is deferred |
| STOR-5 | Gateway storage API and action executor wiring | M | `core/onemind_core/storage.py`, one line in `routes.py`, one ledger migration | STOR-0, STOR-4, DEV-API-7 | API tests: reads match the node report; `storage.protect` plan names the disk serial tail; approving after the disk changed returns 409 `stale_precondition`; agent approve returns 403; destructive approve without step-up returns 401 `step_up_required` |
| STOR-6 | Scrub scheduler and health alerts (§4.7) | M | `internal/storage/schedule/**`; alert rules registered with CORE-NOTIFY-1 | STOR-3, CORE-NOTIFY-1 | Fake clock: monthly scrub persists across restarts; injected corruption on one member is repaired and reported; SMART-fail and wear fixtures raise the right severities exactly once |
| STOR-7 | App snapshots: one subvolume per PV, snapshot before app/OS update, prune policy | M | `internal/storage/snapshot/**`; provisioner setup/teardown scripts merged by the image stream | STOR-1, CORE-BACKUP-1 | Installing an app creates a subvolume PV; `app.update` leaves a read-only snapshot; reverting restores the data byte-for-byte; restic backup reads from the snapshot (BACKUPS.md BT-1 still passes) |
| STOR-8 | Dashboard: Storage page, disk detail, protect flow, recovery screen, node-card pill | L | `dashboard/src/pages/Storage.tsx`, `dashboard/src/pages/storage/**`, route line in `App.tsx`; components in `ui/**` via the design-system owner | STOR-5, PA-UI | Playwright against a fake gateway: every state renders (protected, unprotected, degraded, repairing, unavailable); the wipe plan shows model, size, serial tail; text passes the plain-language check in `docs/design/PRINCIPLES.md` |
| STOR-9 | CLI and MCP | S | `cmd/onemind/cli/storage.go` + one line in `root.go`; MCP tool entries via the MCP owner (`core/onemind_core/mcp/catalog.py`) | STOR-5, DEV-CLI-1, DEV-MCP-3 | `onemind storage status --json` matches the API; wiping commands require the typed serial tail; MCP conformance: `get_storage_status` works with `storage:read`, `request_action storage.protect` files an action, no tool approves |
| STOR-10 | Raspberry Pi 5 lab: dual-NVMe HAT and NVMe + USB raid1, throughput, power-cut loop | M | `lab-kits/**`, report in `docs/umbrel2/` | STOR-4 | 100 power cuts during write load and during `replace`: zero uncorrectable errors on the next scrub; measured MB/s recorded; USB bridge allow/deny list written |
| STOR-11 | GPU detection breadth (§4.11) | S | `internal/detect/**` | CORE-FABRIC-4 (WORKSTREAMS §3 rule) | Fixtures for `lspci` output with `0300` and `0380` controllers, AMD with `/dev/kfd`, NVIDIA via `nvidia-smi`; labels as specified; a GPU app lands only on a labelled node (DOGFOOD-5 test) |
| STOR-12 | Decision: HDD + SSD acceleration (bcache vs dm-cache vs none) and a ZFS "NAS tier" licence review | S | `docs/DECISIONS.md`, `docs/umbrel2/` | STOR-10 | Written decision with measurements on an HDD box; no code until accepted |

**Order:** STOR-0 → STOR-1 (with CORE-SEC-5) → STOR-2 and STOR-3 in parallel → STOR-4 → STOR-5, STOR-6, STOR-7 → STOR-8, STOR-9 → STOR-10 (can start on hardware once STOR-4 runs in QEMU). STOR-11 waits only for FABRIC-4. Each epic gets a STATUS.md row and a CHANGELOG entry when it merges.
