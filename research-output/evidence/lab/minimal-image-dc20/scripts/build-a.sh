#!/bin/bash
# LAB-minimal-image-dc20 leg A: Debian 13 x86_64 UEFI disk image via mkosi, timed.
# Run as root INSIDE the disposable Lima VM (arm64; amd64 maintainer scripts run via
# qemu-user binfmt):   sudo bash build-a.sh
set -euo pipefail
L=/var/lab/dc20/legA; OUT=/var/lab/dc20/out/legA; C=/var/lab/dc20/cache-a
mkdir -p "$OUT" "$L/mkosi.extra/usr/local/bin"
install -m 0755 /var/lab/dc20/in/k3s "$L/mkosi.extra/usr/local/bin/k3s"
rm -rf "$C"; mkdir -p "$C"
t(){ local name=$1; shift; local s=$(date +%s); "$@"; local e=$(date +%s); echo "$name $((e-s))" | tee -a "$OUT/times.txt"; }
: > "$OUT/times.txt"
mkosi --version > "$OUT/versions.txt"
cd "$L"
# M4(i) clean build, empty package cache (all .debs downloaded)
t clean_with_downloads mkosi --cache-dir="$C" -f build > "$OUT/build-clean.log" 2>&1
cp onemind-deb.raw "$OUT/disk.img"
mkosi --cache-dir="$C" summary > "$OUT/mkosi-summary.txt" 2>&1 || true
# M4(ii) clean build, packages cached
t clean_downloads_cached mkosi --cache-dir="$C" -f build > "$OUT/build-clean-cached.log" 2>&1
# M4(iii) incremental: warm the incremental base-tree cache, change one file, rebuild
mkosi --cache-dir="$C" --incremental=yes -f build > "$OUT/build-inc-warm.log" 2>&1
date -u > mkosi.extra/etc/onemind-build-stamp
t incremental_one_change mkosi --cache-dir="$C" --incremental=yes -f build > "$OUT/build-inc.log" 2>&1
rm -f mkosi.extra/etc/onemind-build-stamp
du -sh "$C" | tee -a "$OUT/times.txt"
echo DONE
