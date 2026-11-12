<!-- SPDX-License-Identifier: Apache-2.0 -->
# Patch for the image stream: LUKS2 + btrfs data set, boot assembly, storage service

**Date:** 2026-11-12 · **From:** branch `feat/storage-actions` (STORAGE-ACT-1, STORAGE-LUKS-1, UMB-STOR-1/2) · **For:** the image stream, which owns `os/**` (WORKSTREAMS §1, §3) · **Status:** proposed, not applied. Nothing under `os/` was edited on the storage branch.
**Code it wires:** `onemindd storage init`, `onemindd storage assemble`, `onemindd storage serve` (`cmd/onemindd/storage.go`, `internal/storage/ops/`). **Evidence:** `research-output/evidence/lab/storage-actions/` (Debian 13 VM: power cuts, LUKS2 members, degraded boot). **Design:** [STORAGE-ACTIONS.md](STORAGE-ACTIONS.md).

> **Explain it like I am the founder**
> Today the image puts a plain ext4 data partition on every box, made when the image is built, so every box of a build has the same empty partition and nothing is encrypted. After this patch the image ships that partition blank. On the first boot, OneMind turns it into an encrypted disk with a key that is unique to the box. It also makes a recovery key that the owner sees once in the dashboard. From then on, every boot unlocks the data disks (with the TPM chip when the box has one, otherwise by asking for the recovery key once) and mounts them. When a disk is missing, the box starts in a safe degraded or recovery mode instead of failing. A new privileged service does the approved disk changes.

## 1. No initramfs change: unlock in the signed root

The image's initramfs mounts only the read-only root. `/data` is mounted later, from `/etc/fstab`, during `local-fs.target`. The data set is assembled at the same point, by a oneshot unit in the root (`DefaultDependencies=no`, `Before=local-fs.target`). Why that is the right place:

- **Same trust:** the root is the signed, read-only slot (verity and signed UKIs as SB-x land), so the unlock code is as trusted as in an initramfs. TPM2 unseal checks PCR 7 and the signed PCR 11 policy at that moment, wherever it runs.
- **Updates with the slot:** the assembly is `onemindd` from the slot, so a RAUC update ships a new assembly and a rollback brings the old one back. No initramfs rebuild hooks are needed (`os/rootfs/Containerfile` already runs `update-initramfs` only for watchdog drivers).
- **Proven:** the lab ran exactly this order (lab phases 9 to 11).

The initramfs stays as it is. Only if a later design puts the root itself on LUKS would the initramfs need `cryptsetup`; that is not planned (H-11 encrypts `onemind-data` only).

## 2. Layout and fstab

### 2.1 `os/boards/{x86_64-efi,arm64-efi,vm,vm-do}/layout.yaml`

```diff
-  - {label: onemind-data,     size: rest,   type: linux, fs: ext4}                       # LUKS2 planned (SB-5, BM2; findings F-04)
+  - {label: onemind-data,     size: rest,   type: linux, fs: none}                       # blank: first boot makes LUKS2 + btrfs (H-11, onemindd storage init)
```

`assemble.py` already writes nothing for `fs: none` (the recovery partition uses it). The partition keeps its label, so nothing that finds it by `PARTLABEL` changes.

**Partition id.** `assemble.py` gives every partition a fixed GPT id (`-u index:partuuid`), so every box flashed from one image shares the data partition's id. The storage code identifies members by partition id *within one box*, so this is safe until a disk from another OneMind box is plugged in. Recommended: the installer (P3) or first boot randomises the data partition's id (`sgdisk --partition-guid=<n>:R`) before `storage init`. That is a follow-up for the installer, not part of this patch.

### 2.2 `os/rootfs/layers/base/etc/fstab`

```diff
-PARTLABEL=onemind-data  /data      ext4  defaults                            0 2
+# /data (subvolume @) is unlocked and mounted by onemind-data-assemble.service (normal, degraded,
+# or a tmpfs in storage recovery mode); the other subvolumes follow it.
+LABEL=onemind-data  /data/onemind/storage  btrfs  subvol=@storage,noatime,compress=zstd:1,space_cache=v2,discard=async,nofail,x-systemd.requires=onemind-data-assemble.service  0 0
+LABEL=onemind-data  /data/.snapshots       btrfs  subvol=@snapshots,noatime,compress=zstd:1,space_cache=v2,discard=async,nofail,x-systemd.requires=onemind-data-assemble.service  0 0
```

`LABEL=onemind-data` is the btrfs label; udev points it at any member, and any member mounts the whole set after the assembly's `btrfs device scan`. Both lines use `nofail`, so storage recovery mode (a tmpfs on `/data`) still boots. Mount options are `MountOptions` in `internal/storage/plan.go`. Whether `discard=async` should stay on encrypted disks is open (lab finding 5 of LAB-storage-mirror). dm-crypt passes discards down only with `--allow-discards`, which reveals which blocks are free.

## 3. Units

### 3.1 New `os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-assemble.service`

```ini
# SPDX-License-Identifier: Apache-2.0
# Unlocks the data set's members (TPM2, else the recovery key asked once) and mounts @ at /data:
# normal, degraded (markers /run/onemind/storage/degraded and <data>/onemind/storage/needs-scrub),
# or a tmpfs with /run/onemind/storage/unavailable (storage recovery mode). First boot formats the
# blank onemind-data partition (LUKS2 + btrfs; the recovery key waits in /run for the dashboard).
[Unit]
Description=OneMind: unlock and mount the data set
DefaultDependencies=no
Wants=systemd-udev-settle.service systemd-modules-load.service
After=systemd-udev-settle.service systemd-modules-load.service systemd-ask-password-console.path
Before=local-fs.target onemind-data-layout.service
Conflicts=shutdown.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/onemindd storage assemble --init --mount-normal --wait 30s
# The recovery-key prompt may wait for a person.
TimeoutStartSec=infinity
StandardOutput=journal+console

[Install]
WantedBy=local-fs.target
```

New `os/rootfs/layers/base/usr/lib/modules-load.d/onemind-storage.conf`, so the modules are there before the assembly:

```
# SPDX-License-Identifier: Apache-2.0
dm_crypt
btrfs
```

### 3.2 `onemind-data-layout.service` (exists)

```diff
 [Unit]
 Description=OneMind: create state directories on the data partition
 DefaultDependencies=no
-RequiresMountsFor=/data
+Requires=onemind-data-assemble.service
+After=onemind-data-assemble.service
 Before=local-fs.target
```

The bind mounts in `fstab` already require this unit, so they follow the assembly. In recovery mode the state directories are created on the tmpfs and the box boots. Nothing is written to the disks.

### 3.3 `k3s.service` (exists): do not start on recovery tmpfs (storage.md §4.4)

```diff
 [Unit]
+ConditionPathExists=!/run/onemind/storage/unavailable
```

### 3.4 New `os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-storage.service`

```ini
# SPDX-License-Identifier: Apache-2.0
# The storage operation service (onemindd storage serve): runs owner-approved storage plans from its
# journal on /data and resumes or rolls them back after a power cut. Local Unix socket only
# (/run/onemind/storage.sock, mode 0660, group onemind: the gateway). Root with raw block devices,
# device-mapper and mount: it partitions, encrypts and adds disks, so it is not sandboxed like
# onemindd.service. It never runs a command it is sent; it renders every plan itself.
[Unit]
Description=OneMind storage operations
After=onemind-data-assemble.service local-fs.target

[Service]
Type=simple
ExecStart=/usr/bin/onemindd storage serve --group onemind
Restart=always
RestartSec=2s
User=root
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes
ProtectKernelLogs=yes
ProtectClock=yes
ProtectHostname=yes
LockPersonality=yes
RestrictRealtime=yes
RestrictAddressFamilies=AF_UNIX AF_NETLINK
SystemCallArchitectures=native
UMask=0077

[Install]
WantedBy=multi-user.target
```

`onemind-firstboot` adds it to the hub and node unit lists (`onemind_firstboot.py`, `ROLE_UNITS`). It also writes `ONEMIND_STORAGE_ENABLED=1` into the hub's `gateway.env`, so the gateway talks to the socket. The gateway already runs as `onemind:onemind` and is allowed `AF_UNIX`.

### 3.5 Cloud grow (`os/boards/vm-do/rootfs/.../onemind-data-grow.service`)

```diff
-RequiresMountsFor=/data
+After=onemind-data-assemble.service
+RequiresMountsFor=/data
 [Service]
 Type=oneshot
-ExecStart=/sbin/resize2fs /dev/disk/by-partlabel/onemind-data
+ExecStart=/sbin/cryptsetup resize --key-file /data/onemind/secrets/storage-set.key onemind-data
+ExecStart=/bin/btrfs filesystem resize max /data
```

`cryptsetup resize` of an open LUKS2 mapping needs a key when the volume key is in the kernel keyring (the default); the set key inside the set serves. This was not lab-checked on DigitalOcean; the cloud-image battery (C0–C6) covers it. (`rpi5` and `jetson-orin` have no `layout.yaml` with `onemind-data` yet; they take the same line when they get one.)

## 4. Packages (`os/rootfs/packages/debian-common.txt`) and pins

Add, run as separate processes (GPL-family, Debian main; candidate versions from `docs/umbrel2/storage.md` §4.1, UNVERIFIED until pinned against the image snapshot in `os/versions.lock.yaml`):

```
btrfs-progs cryptsetup-bin systemd-cryptsetup gdisk smartmontools nvme-cli
```

`systemd-cryptsetup` carries `systemd-cryptenroll` and the libcryptsetup `systemd-tpm2` token plugin, which `cryptsetup open --token-only` uses to unseal with the TPM2. `systemd-ask-password` is in `systemd`. Check that the TPM2 software stack `systemd-cryptenroll` loads at runtime (the `libtss2-*` libraries) is pulled in by the snapshot's dependencies.

## 5. A/B rollback barrier (decision needed, DECISIONS-NEEDED F-61)

A slot from before this patch mounts `/data` as ext4 from `fstab`. After the first boot of a patched slot, `/data` is LUKS2 + btrfs, so **rolling back to an unpatched slot cannot mount the data**. The first release with this patch must therefore be a rollback barrier: RAUC refuses to boot an older slot (a compatible-version floor in `os/rauc/system.conf.in` or the health gate). Existing boxes have ext4 data and no in-place conversion. Only the founder's development boxes exist today: reinstall them, or back up and restore with restic (BACKUPS). The storage stream does not build a converter.

Rollback between patched slots is safe as long as no newer btrfs features are enabled (storage.md §4.6). `storage init` uses `mkfs.btrfs` defaults; the image stream records the feature list in `versions.lock.yaml` (`storage.features`).

## 6. Boxes without a TPM2 (decision needed, DECISIONS-NEEDED F-62)

With no TPM2 the assembly asks for the recovery key at every boot, on the console. Fine for a desk box with a screen, impossible for a headless VM or a droplet. Options, per board:

| Option | Security | Fit |
|---|---|---|
| Ask at every boot (default without TPM2) | strongest | boxes with a console |
| Network unlock (Tang/Clevis-style, from another OneMind node) | strong once two nodes exist | multi-node, later |
| No LUKS on cloud boards; the provider's disk encryption | the provider holds the keys | droplets, cloud VMs |
| Key file on the ESP | none against disk theft | rejected |

Proposed: `x86_64-efi`, `arm64-efi`, `rpi5`, `jetson-orin`: TPM2 where present, else ask. `vm-do` and `cloud-*`: no LUKS until network unlock exists. That needs a `storage init --plain` mode and plain-btrfs handling in the assembly, both small follow-ups on the storage branch once the founder decides.

## 7. Acceptance (test/qemu, owned by the image stream)

STOR-1 and STOR-2 criteria, as QEMU checks (the lab did each on Lima first):

1. Fresh image, first boot: `cryptsetup luksDump /dev/disk/by-partlabel/onemind-data` shows the recovery and set-key keyslots, a `systemd-tpm2` token when the VM has a vTPM (swtpm), and the `onemind-storage` token. `findmnt /data` shows `[/@]` on btrfs over dm-crypt. `POST /v1/storage/recovery-key` returns the key once.
2. Second disk attached, `storage.mirror.create` approved: `GET /v1/storage` shows `protected`. A reboot unlocks both members from the TPM2 with no prompt.
3. One member detached: boots `degraded`, markers present, the alert raised. Re-attached: `needs_scrub` until `storage.mirror.repair`, then `protected`.
4. Both members detached: `/data` is a tmpfs, `/run/onemind/storage/unavailable` exists, `k3s` is not running, and `GET /v1/storage` answers with `available` and `state: unavailable`.
5. Power cut (QEMU `system_reset`) during `storage.mirror.add`'s balance: the next boot finishes the operation, and the scrub finds no uncorrectable errors.
