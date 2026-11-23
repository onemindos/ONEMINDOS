<!-- SPDX-License-Identifier: Apache-2.0 -->
# Test fixtures

**Recorded** (real tool output, Debian 13 arm64 Lima VM, kernel 6.12.115, btrfs-progs 6.14, util-linux 2.41.5, smartmontools 7.4; lab notes in `research-output/evidence/lab/storage-mirror/`):

| Prefix | State when recorded |
|---|---|
| `blank.lsblk.json` | before the lab: system disk vda, blank vdb/vdc, read-only cloud-init disk vdd (re-indented, values unchanged) |
| `unprotected.*` | one-device btrfs on a loop file (single data, dup metadata) |
| `degraded-mounted.*` | raid1 set, member 2 pulled, mounted `-o degraded`, nothing written yet |
| `degraded-written.*` | same after 1.5 GiB written: `Data, single` chunks appear |
| `returned.*` | member 2 reconnected, normal mount, before repair |
| `repaired.*` | after the repair plan (scrub + soft-convert): fully raid1 |
| `stale-no-marker.*` | second pull, 64 MiB written into existing raid1 chunks, member back: btrfs shows nothing wrong, yet the scrub then corrected 16 384 stale blocks |
| `virtio.smartctl.json` | smartctl on a virtio disk (no SMART: exit status 1) |

**Recorded for free space** (`*-usage.*`, issue #841; Debian 13 trixie container, btrfs-progs 6.14, on an x86_64 Ubuntu 24.04 build worker's kernel 6.8.0, 3 GiB loop files). Each set also has `btrfs filesystem usage -b` (`.usage.txt`) and `stat -f` of the mount (`.statfs.txt`: the statfs(2) block counts). The earlier recordings above have no usage output, so their free space is unknown.

| Prefix | State when recorded |
|---|---|
| `single-usage.*` | one device, single data, dup metadata, 512 MiB written |
| `mirror-usage.*` | two devices, raid1 data and metadata, 1 GiB written |
| `degraded-usage.*` | the same raid1 set with member 2 gone, mounted `-o degraded`, 768 MiB more written: `Data, single` chunks appear |

**Synthetic** (`synthetic-*.smartctl.json`): hand-written in the smartmontools 7.4 JSON field names (`smart_status`, `temperature`, `power_on_time`, `nvme_smart_health_information_log`, `ata_smart_attributes`), values invented. A VM has no SMART, so real NVMe, SATA and USB-SAT recordings come from the hardware lab (STOR-10) and replace these.
