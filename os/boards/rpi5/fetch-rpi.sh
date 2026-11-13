#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Board rpi5: Raspberry Pi's kernel packages from archive.raspberrypi.com, pinned by pool path and
# sha256 (os/versions.lock.yaml rpi5; test/unit/test_rpi5.py checks they match). The hashes were
# read from the trixie Packages index whose InRelease verified with the Raspberry Pi Archive
# Signing Key, fingerprint CF8A1AF502A2AA2D763BAE7E82B129927FA3303E (refresh: pin-rpi.sh).
# The pool keeps old versions, so a pin stays buildable after Raspberry Pi publishes a newer one.
#   fetch-rpi.sh <dest-dir>
set -eu
DEST=$1
BASE=https://archive.raspberrypi.com/debian
RPI_KERNEL=6.18.60-1+rpt1
PINS="
pool/main/l/linux/linux-base-6.18.60+rpt-rpi-2712_6.18.60-1+rpt1_arm64.deb c2406f32e9653b01095a3d9561d01bcf3f2960f204e42ce36ced8aab24fa9518
pool/main/l/linux/linux-image-6.18.60+rpt-rpi-2712_6.18.60-1+rpt1_arm64.deb 663099a4badd7e583ae28bbb0ef60fc3b6d1faafabbb8c6252a989730b9224e9
pool/main/l/linux/linux-base-6.18.60+rpt-rpi-v8_6.18.60-1+rpt1_arm64.deb 0d27ecbe7e8e48328d4c293e9c61e8e0e1b0536d63bb3194b8d0050b24b96626
pool/main/l/linux/linux-image-6.18.60+rpt-rpi-v8_6.18.60-1+rpt1_arm64.deb fbd80d4c6b488b099cfd17370a9b219b17215ee1c909c1839f8c040d098acf73
"
mkdir -p "$DEST"
echo "$PINS" | while read -r path sha; do
  [ -n "$path" ] || continue
  f=$DEST/$(basename "$path")
  curl -fsSL --retry 5 --proto '=https' -o "$f" "$BASE/$path"
  echo "$sha  $f" | sha256sum -c -
done
echo "Raspberry Pi kernel $RPI_KERNEL (2712 + v8): sha256 verified"
