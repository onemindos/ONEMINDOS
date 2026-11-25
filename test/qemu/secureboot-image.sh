#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# A Secure Boot test image: the x86_64-efi image on the efi route (RAUC's efi backend picks the slot), with one signed
# UKI per slot, plus one update bundle that carries the signed UKIs (S-13, #148).
# Runs as root in the tools container:   secureboot-image.sh <rootfs.tar> <outdir>
# Outputs in <outdir>: disk.img (slot A = v1 + the battery's test overlay), bundles.img (ext4 "onemind-test" holding
# bundles/good.raucb, v2), db.crt (public). The signing keys (UKI db key, RAUC CA and signer) are THROWAWAYS made
# here in /tmp and deleted on exit; the real keys are made at the founder's signing ceremony (os/secureboot/README.md).
set -euo pipefail
ROOTFS=$1; OUT=$2; BOARD=x86_64-efi
SRC=$(cd "$(dirname "$0")/../.." && pwd)
A="python3 -I $SRC/os/assemble/assemble.py"
W=${WORK:-/work/sb-$BOARD}; K=$(mktemp -d /tmp/sbkeys.XXXXXX)
trap 'rm -rf "$K"' EXIT
rm -rf "$W"; mkdir -p "$OUT" "$W/bdisk/bundles"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -sha256 -keyout "$K/db.key" -out "$K/db.crt" \
  -subj "/O=OneMind TEST (throwaway)/CN=test-db" 2>/dev/null
# RAUC: a throwaway CA (the image's keyring) and a signer it issued, as test/qemu/mkfixtures.sh makes them.
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -sha256 -keyout "$K/ca.key" -out "$K/ca.pem" \
  -subj "/O=OneMind TEST (throwaway)/CN=sb-test-ca" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -sha256 -keyout "$K/signer.key" -out "$K/signer.csr" \
  -subj "/O=OneMind TEST (throwaway)/CN=sb-test-signer" 2>/dev/null
openssl x509 -req -in "$K/signer.csr" -CA "$K/ca.pem" -CAkey "$K/ca.key" -CAcreateserial -days 1 -sha256 \
  -out "$K/signer.pem" -extfile <(printf 'keyUsage=critical,digitalSignature\n') 2>/dev/null
# The battery's test overlay gives SB5 a root shell on the serial console (rauc install, efibootmgr).
$A tree --board "$BOARD" --rootfs "$ROOTFS" --work "$W" --version 1 --keyring "$K/ca.pem" --boot efi \
  --overlay "$SRC/test/qemu/overlay"
SIZE=$(( ( $(du -s -B1M --apparent-size "$W/tree" | cut -f1) * 13 / 10 + 384 + 63 ) / 64 * 64 ))
$A ext4 --work "$W" --out "$W/system.ext4" --size-mib "$SIZE" >/dev/null
$A disk --board "$BOARD" --work "$W" --system "$W/system.ext4" --out "$OUT/disk.img" \
  --sb-key "$K/db.key" --sb-cert "$K/db.crt"
# Update bundles for SB5-SB7: the same tree one version later, UKIs built and signed here and carried in the bundle.
T=$W/tree
setver() { sed -i "s/^ONEMIND_VERSION=.*/ONEMIND_VERSION=\"$1\"/" "$T/usr/lib/os-release"; }
bundle() {   # $1 version, $2 out name
  $A ext4 --work "$W" --out "$W/system.ext4" --size-mib "$SIZE" >/dev/null
  $A bundle --board "$BOARD" --system "$W/system.ext4" --version "$1" --cert "$K/signer.pem" --key "$K/signer.key" \
    --out "$W/bdisk/bundles/$2.raucb" --sb-key "$K/db.key" --sb-cert "$K/db.crt" --work "$W" >/dev/null
}
setver 2; bundle 2 good                                                  # SB5: a good update
# SB6: k3s exits at start, so the health gate rejects slot B and the box falls back to A (same fixture as T4).
setver 3; printf 'K3S_EXTRA_ARGS=%s\n' "--onemind-test-unknown-flag" > "$T/etc/default/k3s"; bundle 3 bad-k3s
printf 'K3S_EXTRA_ARGS=\n' > "$T/etc/default/k3s"
# SB7: PID 1 exits, the kernel panics in slot B's one trial boot (same fixture as T6).
mv "$T/sbin/init" "$T/sbin/init.real"; install -m 755 "$SRC/test/qemu/bad-boot-init" "$T/sbin/init"
setver 5; bundle 5 bad-boot
rauc info --keyring="$K/ca.pem" "$W/bdisk/bundles/good.raucb" 2>&1 | grep -E "Verified|Bundle Format|efi|rootfs" || true
BSIZE=$(( $(du -s -B1M "$W/bdisk/bundles" | cut -f1) + 256 ))
rm -f "$OUT/bundles.img"
mke2fs -q -t ext4 -L onemind-test -d "$W/bdisk" "$OUT/bundles.img" "${BSIZE}M"
cp "$K/db.crt" "$OUT/db.crt"
rm -rf "$W"
echo "Secure Boot test image and bundle ready in $OUT (throwaway keys destroyed)"
