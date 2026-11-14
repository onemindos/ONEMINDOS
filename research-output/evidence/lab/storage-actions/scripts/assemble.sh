#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Lab stand-in for the image's onemind-data-assemble unit (docs/leap/core/STORAGE-ACT-os.patch.md §3):
# unlock the current members of the data set, then mount subvolume @ at /data.
# The rules are the patch's: a member's token must name the member's own partition id, and only the
# newest generation is unlocked. /root/lab/recovery.key stands in for the owner typing the key once.
set -u
KEY=/root/lab/recovery.key
best=0
list=""
stale=""
for dev in $(blkid -o device -t PARTLABEL=onemind-data); do
  [ "$(blkid -s TYPE -o value "$dev")" = crypto_LUKS ] || continue
  tok=$(cryptsetup token export --token-id 30 "$dev" 2>/dev/null) || { echo "assemble: $dev has no OneMind token: skipped"; continue; }
  own=$(blkid -s PARTUUID -o value "$dev")
  if [ "$(echo "$tok" | jq -r .partuuid)" != "$own" ]; then
    echo "assemble: $dev carries another member's token (a half-prepared copy): skipped"
    continue
  fi
  gen=$(echo "$tok" | jq -r .generation)
  [ "$gen" -gt "$best" ] && best=$gen
  list="$list $dev:$gen"
done
first=""
for e in $list; do
  dev=${e%:*}
  gen=${e#*:}
  if [ "$gen" -ne "$best" ]; then
    echo "assemble: $dev is generation $gen, the set is at $best (it left the set): skipped"
    stale="$stale $dev"
    continue
  fi
  name=luks-$(cryptsetup luksUUID "$dev")
  cryptsetup status "$name" >/dev/null 2>&1 || cryptsetup open --key-file "$KEY" "$dev" "$name" || echo "assemble: cannot unlock $dev"
  [ -z "$first" ] && first=/dev/mapper/$name
  echo "assemble: $dev unlocked as $name (generation $gen)"
done
if [ -z "$first" ]; then echo "assemble: no members: /data stays unmounted (storage recovery mode)"; exit 0; fi
btrfs device scan >/dev/null
mkdir -p /data
opts=subvol=@,noatime,compress=zstd:1,space_cache=v2,discard=async
if mount -o "$opts" "$first" /data; then echo "assemble: /data mounted"; exit 0; fi
# Before running degraded: a member whose token fell behind (an interrupted operation) may still hold
# chunks. btrfs ignores a disk that really left (its superblock is wiped), so opening these is safe.
if [ -n "$stale" ]; then
  for dev in $stale; do
    name=luks-$(cryptsetup luksUUID "$dev")
    cryptsetup status "$name" >/dev/null 2>&1 || cryptsetup open --key-file "$KEY" "$dev" "$name" && echo "assemble: retry with $dev (older generation)"
  done
  btrfs device scan >/dev/null
  if mount -o "$opts" "$first" /data; then echo "assemble: /data mounted with an older-generation member: run a repair"; exit 0; fi
fi
if mount -o "$opts,degraded" "$first" /data; then
  mkdir -p /data/onemind/storage && : > /data/onemind/storage/needs-scrub
  echo "assemble: /data mounted DEGRADED (needs-scrub marker written)"
  exit 0
fi
echo "assemble: /data not mountable: storage recovery mode"
