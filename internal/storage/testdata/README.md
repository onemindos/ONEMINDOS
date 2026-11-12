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

**Synthetic** (`synthetic-*.smartctl.json`): hand-written in the smartmontools 7.4 JSON field names (`smart_status`, `temperature`, `power_on_time`, `nvme_smart_health_information_log`, `ata_smart_attributes`), values invented. A VM has no SMART, so real NVMe, SATA and USB-SAT recordings come from the hardware lab (STOR-10) and replace these.
