#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Phase 2: boot with the second member removed; mount degraded; write new data.
. "$(dirname "$0")/common.sh"
say "inventory with one member pulled"; run onemind storage disks
run cryptsetup open --key-file "$KEY" /dev/vdb1 onemind-data-vdb
btrfs device scan
say "normal mount refuses a set with a missing member"
mount -o noatime /dev/mapper/onemind-data-vdb /data && echo "UNEXPECTED: mounted" || echo "mount refused (expected)"
dmesg | grep -i btrfs | tail -3
say "mount degraded (what the initrd policy will do when a full copy remains)"
run mount -o degraded,noatime,compress=zstd:1 /dev/mapper/onemind-data-vdb /data
capture degraded-mounted
run onemind storage status
say "write 1.5 GiB while degraded (forces new chunk allocation)"
for i in $(seq -w 1 6); do head -c 256M /dev/urandom > /data/@/corpus/degraded$i; done; sync
(cd /data/@/corpus && sha256sum degraded* > /root/degraded.sha256)
run btrfs filesystem df /data
run onemind storage status
capture degraded-written; run onemind storage status --json
say "repair plan while a member is still missing"; onemind storage plan repair --mount /data || true
(cd /data/@/corpus && sha256sum -c --quiet /root/corpus.sha256) && echo "corpus OK"
umount /data
