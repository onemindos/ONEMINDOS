#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Release-keyed image for the installer stick (#234, D-010; os/boards/installer-x86_64/UPDATES.md): assemble <board>
# from a rootfs tar with the RELEASE CA as its RAUC keyring, so a box installed from it accepts every later release
# bundle of the channel. Runs in the tools container, like dev-image.sh (`make release-image`):
#   TRUSTDIR=/trust VERSION=0.1.20261112025704 BOARD=x86_64-efi ROOTFS=/out/rootfs.tar release-image.sh /out/image-x86_64-efi
# TRUSTDIR holds ONLY keyring.pem: the public CA certificate the release bundles verify against, as written by
# os/update/build-release.sh (<bundle>.keyring.pem) and picked by scripts/release/installer-payload.py.
# No signing key is used or accepted: the image is assembled without --cert/--key, so no bundle is made here (the
# channel's bundles come from build-release.sh). Refused: any other file in TRUSTDIR, a PEM block that is not a
# certificate, a development version, SECUREBOOT=1. Without release keys the image is `make image` (dev-image.sh).
set -eu
OUTDIR=$1; : "${BOARD:?}" "${ROOTFS:?}" "${VERSION:?}"
SRC=$(cd "$(dirname "$0")/../.." && pwd)
die() { echo "REFUSED: $*" >&2; exit 2; }
[ -n "${TRUSTDIR:-}" ] || die "TRUSTDIR (the release CA certificate) is not set; without release keys use dev-image.sh (make image)"
case "$VERSION" in *-dev*) die "'$VERSION' is a development version; a release-keyed image carries a release version" ;; esac
[ "${SECUREBOOT:-0}" = 0 ] || die "SECUREBOOT=1 needs the release Secure Boot key, which this path does not take (os/secureboot/README.md)"
# Names only: nothing in TRUSTDIR but keyring.pem is ever opened.
for f in "$TRUSTDIR"/* "$TRUSTDIR"/.[!.]*; do
  [ -e "$f" ] || continue
  [ "$(basename "$f")" = keyring.pem ] || die "TRUSTDIR holds $(basename "$f"); only keyring.pem (the public CA certificate) may be given"
done
CA=$TRUSTDIR/keyring.pem
[ -s "$CA" ] || die "TRUSTDIR has no keyring.pem"
# Certificates only (checked quietly, nothing from the file is printed): a private key is refused, not used.
if grep -q 'PRIVATE KEY' "$CA"; then die "keyring.pem holds a private key; give the CA certificate only"; fi
grep -q '^-----BEGIN CERTIFICATE-----' "$CA" || die "keyring.pem holds no certificate"
if grep '^-----BEGIN ' "$CA" | grep -qv '^-----BEGIN CERTIFICATE-----'; then die "keyring.pem holds a PEM block that is not a certificate"; fi
W=$(mktemp -d /tmp/work.XXXXXX); trap 'rm -rf "$W"' EXIT
mkdir -p "$OUTDIR"; rm -f "$OUTDIR/SHA256SUMS"
# A board may name its own assembler with the same CLI (board.yaml `assembler:`), as in dev-image.sh.
ASM=$(sed -n 's/^assembler: *\([^ #]*\).*/\1/p' "$SRC/os/boards/$BOARD/board.yaml"); ASM=${ASM:-os/assemble/assemble.py}
python3 -I "$SRC/$ASM" image --board "$BOARD" --rootfs "$ROOTFS" --work "$W" \
  --version "$VERSION" --keyring "$CA" --out-dir "$OUTDIR"
cp "$CA" "$OUTDIR/release-ca.cert.pem"
echo "release-keyed image ready in $OUTDIR (keyring: the release CA; no signing key used, no bundle made)"
