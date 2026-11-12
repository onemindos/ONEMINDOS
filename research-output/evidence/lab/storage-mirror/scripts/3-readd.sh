#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Phase 3: member reconnected; status, repair plan, resync, verify.
. "$(dirname "$0")/common.sh"
say "inventory with the member back"; run onemind storage disks
run cryptsetup open --key-file "$KEY" /dev/vdb1 onemind-data-vdb
run cryptsetup open --key-file "$KEY" /dev/vdc1 onemind-data-vdc
btrfs device scan
run mount -o noatime,compress=zstd:1 /dev/mapper/onemind-data-vdb /data
capture returned; run onemind storage status
say "resync: apply the repair plan"
apply_plan repair --mount /data
run onemind storage status
capture repaired; run onemind storage status --json
(cd /data/@/corpus && sha256sum -c --quiet /root/corpus.sha256 && sha256sum -c --quiet /root/degraded.sha256) && echo "corpus OK (original and degraded-period files)"
say "second scrub: expect zero errors"; run btrfs scrub start -B /data
