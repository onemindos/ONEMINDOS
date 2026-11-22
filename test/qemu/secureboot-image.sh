#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# A Secure Boot test image: the x86_64-efi image with signed GRUB and signed per-slot UKIs (S-13).
# Runs as root in the tools container:   secureboot-image.sh <rootfs.tar> <outdir>
# Outputs in <outdir>: disk.img, db.crt (public). The signing key is a THROWAWAY made here in /tmp and
# deleted on exit; the real key is made at the founder's signing ceremony (os/secureboot/README.md).
set -euo pipefail
ROOTFS=$1; OUT=$2; BOARD=x86_64-efi
SRC=$(cd "$(dirname "$0")/../.." && pwd)
A="python3 -I $SRC/os/assemble/assemble.py"
W=${WORK:-/work/sb-$BOARD}; K=$(mktemp -d /tmp/sbkeys.XXXXXX)
trap 'rm -rf "$K"' EXIT
rm -rf "$W"; mkdir -p "$OUT"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -sha256 -keyout "$K/db.key" -out "$K/db.crt" \
  -subj "/O=OneMind TEST (throwaway)/CN=test-db" 2>/dev/null
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -sha256 -keyout "$K/ca.key" -out "$K/ca.pem" \
  -subj "/O=OneMind TEST (throwaway)/CN=sb-test-ca" 2>/dev/null   # RAUC keyring only; no bundle is built here
$A tree --board "$BOARD" --rootfs "$ROOTFS" --work "$W" --version sb-test --keyring "$K/ca.pem"
SIZE=$(( ( $(du -s -B1M --apparent-size "$W/tree" | cut -f1) * 13 / 10 + 384 + 63 ) / 64 * 64 ))
$A ext4 --work "$W" --out "$W/system.ext4" --size-mib "$SIZE" >/dev/null
$A disk --board "$BOARD" --work "$W" --system "$W/system.ext4" --out "$OUT/disk.img" \
  --sb-key "$K/db.key" --sb-cert "$K/db.crt"
cp "$K/db.crt" "$OUT/db.crt"
rm -f "$W/system.ext4"
echo "Secure Boot test image ready in $OUT (throwaway key destroyed)"
