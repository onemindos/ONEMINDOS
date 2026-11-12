#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Phase 1: inventory, health, refused plans, one-disk set, protect to raid1.
. "$(dirname "$0")/common.sh"
[ -f "$KEY" ] || { head -c 64 /dev/urandom > "$KEY"; chmod 0400 "$KEY"; }
say "tool versions"; dpkg-query -W btrfs-progs cryptsetup-bin smartmontools gdisk util-linux; uname -r
say "inventory"; run onemind storage disks
say "health"; run onemind storage health
say "refused: system disk"; onemind storage plan create --device /dev/vda --mount /data || true
say "refused: read-only cloud-init disk"; onemind storage plan create --device /dev/vdd --mount /data || true
say "create a one-disk encrypted set on vdb"
apply_plan create --device /dev/vdb --encrypt --key-file "$KEY" --mount /data
run onemind storage status
say "refused: protect with a disk that is already a member"; onemind storage plan protect --device /dev/vdb --mount /data || true
say "checksummed corpus (400 MiB)"
mkdir -p /data/@/corpus
for i in $(seq -w 1 100); do head -c 4M /dev/urandom > /data/@/corpus/f$i; done
(cd /data/@/corpus && sha256sum f* > /root/corpus.sha256); sync
run onemind storage status
say "protect: add vdc and convert to raid1"
apply_plan protect --device /dev/vdc --key-file "$KEY" --mount /data
run onemind storage status
run onemind storage disks
run btrfs scrub start -B /data
(cd /data/@/corpus && sha256sum -c --quiet /root/corpus.sha256) && echo "corpus OK"
umount /data
