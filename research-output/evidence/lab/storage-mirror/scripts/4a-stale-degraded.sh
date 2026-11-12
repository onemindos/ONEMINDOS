#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Phase 4a: second pull. A small write fits into existing raid1 chunks, so no
# single chunks appear; the initrd's job (STOR-2) of writing the marker is done by hand.
. "$(dirname "$0")/common.sh"
umount /data 2>/dev/null || true
run cryptsetup open --key-file "$KEY" /dev/vdb1 onemind-data-vdb
btrfs device scan >/dev/null
run mount -o degraded,noatime /dev/mapper/onemind-data-vdb /data
mkdir -p /data/onemind/storage && touch /data/onemind/storage/needs-scrub   # what onemind-data-assemble will do
say "write 64 MiB while degraded"
head -c 64M /dev/urandom > /data/@/corpus/stale-test; sync
(cd /data/@/corpus && sha256sum stale-test > /root/stale.sha256)
run btrfs filesystem df /data
run onemind storage status
umount /data
