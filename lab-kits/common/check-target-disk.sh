#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# 22 §2.3 rule 2: never write a test image to a disk you care about. Shows the target and asks
# for its size TWICE before anything is written. Mac: /dev/diskN; Linux: /dev/sdX or /dev/nvmeXnY.
#   sh check-target-disk.sh /dev/diskN
set -eu
T=${1:?usage: check-target-disk.sh <device>}
case "$(uname -s)" in
  Darwin) diskutil list "$T"; size=$(diskutil info "$T" | sed -n 's/.*Disk Size: *\([^(]*\).*/\1/p') ;;
  *)      lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS "$T"; size=$(lsblk -dno SIZE "$T") ;;
esac
echo; echo "Target $T reports size: $size"
printf 'Type the size you see above (first time): '; read -r a
printf 'Look at the disk label again, then type the size (second time): '; read -r b
[ "$a" = "$b" ] && [ -n "$a" ] && echo "$size" | grep -qF "$a" || { echo "Sizes do not match. Stopping; nothing was written."; exit 1; }
echo "OK: $T confirmed twice. It will be ERASED by the next step."
