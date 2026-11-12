#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Phase 4b: member back. Without the marker, btrfs looks fully protected
# although the returned disk is stale; with it, status says DEGRADED and the
# repair plan scrubs.
. "$(dirname "$0")/common.sh"
run cryptsetup open --key-file "$KEY" /dev/vdb1 onemind-data-vdb
run cryptsetup open --key-file "$KEY" /dev/vdc1 onemind-data-vdc
btrfs device scan >/dev/null
run mount -o noatime,compress=zstd:1 /dev/mapper/onemind-data-vdb /data
say "without the marker (moved aside): btrfs alone"
mv /data/onemind/storage/needs-scrub /root/needs-scrub.aside
run onemind storage status
capture stale-no-marker
mv /root/needs-scrub.aside /data/onemind/storage/needs-scrub
say "with the marker"
run onemind storage status
say "resync"
apply_plan repair --mount /data
run onemind storage status
(cd /data/@/corpus && sha256sum -c --quiet /root/corpus.sha256 && sha256sum -c --quiet /root/degraded.sha256 && sha256sum -c --quiet /root/stale.sha256) && echo "corpus OK (all files)"
umount /data
