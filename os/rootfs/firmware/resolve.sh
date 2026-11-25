#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Resolve the firmware package list for one image build (the firmware layer).
#   resolve.sh <leg> <arch> <firmware yes|no> [board-package-file]
# Prints one package per line; prints nothing for the open variant (firmware=no). Fails when a package
# has no licence row, so nothing closed-source can ship without being recorded. POSIX sh, runs in the
# build container before Python exists. Why a separate layer: docs and tests in os/rootfs/firmware/README.md.
set -eu
LEG=$1; ARCH=$2; FW=$3; BOARDFILE=${4:-}
DIR=$(cd "$(dirname "$0")" && pwd)
case "$FW" in
yes) ;;
no) exit 0 ;;
*) echo "firmware must be yes or no, got '$FW'" >&2; exit 1 ;;
esac
FILES="$DIR/$LEG-$ARCH.txt"
[ -f "$FILES" ] || exit 0          # a leg or arch with no firmware list has no firmware layer (arm64 boards ship their own)
[ -z "$BOARDFILE" ] || [ ! -f "$BOARDFILE" ] || FILES="$FILES $BOARDFILE"
# shellcheck disable=SC2086
PKGS=$(cat $FILES | sed 's/#.*//' | tr -s ' \t\n' '\n' | sed '/^$/d' | sort -u)
for p in $PKGS; do
  grep -q "^$p|" "$DIR/licences.txt" || { echo "firmware package $p has no row in licences.txt" >&2; exit 1; }
done
echo "$PKGS"
