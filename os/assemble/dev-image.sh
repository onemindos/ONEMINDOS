#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Development image: assemble <board> from a rootfs tar and sign its bundle with a THROWAWAY CA
# made here and deleted on exit (brief 30 SB-10: no key ever leaves the job). The public CA
# certificate is kept next to the image so a matching dev bundle can be checked.
# A production image is signed by the release pipeline (D-B1.7, release.yml), never by this.
#   VERSION=0.1.0-dev BOARD=x86_64-efi ROOTFS=/out/rootfs.tar dev-image.sh /out/image-x86_64-efi
set -eu
OUTDIR=$1; : "${BOARD:?}" "${ROOTFS:?}" "${VERSION:?}"
SRC=$(cd "$(dirname "$0")/../.." && pwd)
K=$(mktemp -d); W=$(mktemp -d /tmp/work.XXXXXX); trap 'rm -rf "$K" "$W"' EXIT
openssl req -x509 -newkey rsa:3072 -nodes -days 30 -sha256 -keyout "$K/ca.key" -out "$K/ca.pem" \
  -subj "/O=OneMind DEV (throwaway)/CN=dev-ca" 2>/dev/null
openssl req -newkey rsa:3072 -nodes -sha256 -keyout "$K/signer.key" -out "$K/signer.csr" \
  -subj "/O=OneMind DEV (throwaway)/CN=dev-signer" 2>/dev/null
openssl x509 -req -in "$K/signer.csr" -CA "$K/ca.pem" -CAkey "$K/ca.key" -CAcreateserial -days 30 -sha256 \
  -out "$K/signer.pem" -extfile "$SRC/os/assemble/signer.ext" 2>/dev/null
mkdir -p "$OUTDIR"; rm -f "$OUTDIR/SHA256SUMS"
# A board may name its own assembler with the same CLI (board.yaml `assembler:`, e.g. rpi5).
ASM=$(sed -n 's/^assembler: *\([^ #]*\).*/\1/p' "$SRC/os/boards/$BOARD/board.yaml"); ASM=${ASM:-os/assemble/assemble.py}
python3 -I "$SRC/$ASM" image --board "$BOARD" --rootfs "$ROOTFS" --work "$W" \
  --version "$VERSION" --keyring "$K/ca.pem" --cert "$K/signer.pem" --key "$K/signer.key" --out-dir "$OUTDIR"
cp "$K/ca.pem" "$OUTDIR/dev-ca.cert.pem"
echo "dev image ready in $OUTDIR (throwaway keys destroyed)"
