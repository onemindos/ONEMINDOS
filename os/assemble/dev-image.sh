#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Development image: assemble <board> from a rootfs tar and sign its bundle with a THROWAWAY CA
# made here and deleted on exit (brief 30 SB-10: no key ever leaves the job). The public CA
# certificate is kept next to the image so a matching dev bundle can be checked.
# A production image is signed by the release pipeline (D-B1.7, release.yml), never by this.
#   VERSION=0.1.0-dev BOARD=x86_64-efi ROOTFS=/out/rootfs.tar dev-image.sh /out/image-x86_64-efi
# SECUREBOOT=1 (x86_64-efi only, off by default, #148): the Secure Boot route instead of GRUB: RAUC's efi backend and
# one signed UKI per slot, signed with a THROWAWAY db key made here and deleted on exit. The public certificate is
# kept as db.crt next to the image so a test can enrol it. The real key is the founder's ceremony (os/secureboot/README.md).
# KEYRING=<public RAUC CA cert> (Step 5, os/update/STEP5-SIGNED-UPDATE.md): the image trusts THAT CA instead of a throwaway
# one, so it accepts bundles signed by the real release signer. Only the public certificate is needed: no signing key is
# made or read, and no bundle is written next to the image (only the release pipeline signs bundles). Not with SECUREBOOT=1.
set -eu
OUTDIR=$1; : "${BOARD:?}" "${ROOTFS:?}" "${VERSION:?}"
SRC=$(cd "$(dirname "$0")/../.." && pwd)
K=$(mktemp -d); W=$(mktemp -d /tmp/work.XXXXXX); trap 'rm -rf "$K" "$W"' EXIT
ASM=$(sed -n 's/^assembler: *\([^ #]*\).*/\1/p' "$SRC/os/boards/$BOARD/board.yaml"); ASM=${ASM:-os/assemble/assemble.py}
if [ -n "${KEYRING:-}" ]; then
  [ "${SECUREBOOT:-0}" != 1 ] || { echo "ERROR: KEYRING= with SECUREBOOT=1 is not supported (the db key would be a throwaway)" >&2; exit 2; }
  openssl x509 -in "$KEYRING" -noout 2>/dev/null || { echo "ERROR: KEYRING=$KEYRING is not a PEM certificate" >&2; exit 2; }
  if grep -q "PRIVATE KEY" "$KEYRING"; then echo "ERROR: KEYRING must be the public CA certificate only" >&2; exit 2; fi
  mkdir -p "$OUTDIR"; rm -f "$OUTDIR/SHA256SUMS"
  python3 -I "$SRC/$ASM" image --board "$BOARD" --rootfs "$ROOTFS" --work "$W" --version "$VERSION" --keyring "$KEYRING" --out-dir "$OUTDIR"
  cp "$KEYRING" "$OUTDIR/keyring.cert.pem"
  echo "image ready in $OUTDIR: trusts the RAUC CA $(openssl x509 -in "$KEYRING" -noout -fingerprint -sha256 | cut -d= -f2) (no bundle made)"
  exit 0
fi
openssl req -x509 -newkey rsa:3072 -nodes -days 30 -sha256 -keyout "$K/ca.key" -out "$K/ca.pem" \
  -subj "/O=OneMind DEV (throwaway)/CN=dev-ca" 2>/dev/null
openssl req -newkey rsa:3072 -nodes -sha256 -keyout "$K/signer.key" -out "$K/signer.csr" \
  -subj "/O=OneMind DEV (throwaway)/CN=dev-signer" 2>/dev/null
openssl x509 -req -in "$K/signer.csr" -CA "$K/ca.pem" -CAkey "$K/ca.key" -CAcreateserial -days 30 -sha256 \
  -out "$K/signer.pem" -extfile "$SRC/os/assemble/signer.ext" 2>/dev/null
mkdir -p "$OUTDIR"; rm -f "$OUTDIR/SHA256SUMS"
SB=""
if [ "${SECUREBOOT:-0}" = 1 ]; then
  [ "$BOARD" = x86_64-efi ] || { echo "ERROR: SECUREBOOT=1 is only for BOARD=x86_64-efi (got $BOARD)" >&2; exit 2; }
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -sha256 -keyout "$K/db.key" -out "$K/db.crt" \
    -subj "/O=OneMind DEV (throwaway)/CN=dev-db" 2>/dev/null
  SB="--sb-key $K/db.key --sb-cert $K/db.crt"
fi
# A board may name its own assembler with the same CLI (board.yaml `assembler:`, e.g. rpi5): $ASM, set above.
python3 -I "$SRC/$ASM" image --board "$BOARD" --rootfs "$ROOTFS" --work "$W" \
  --version "$VERSION" --keyring "$K/ca.pem" --cert "$K/signer.pem" --key "$K/signer.key" --out-dir "$OUTDIR" $SB
cp "$K/ca.pem" "$OUTDIR/dev-ca.cert.pem"
[ -z "$SB" ] || cp "$K/db.crt" "$OUTDIR/db.crt"
echo "dev image ready in $OUTDIR (throwaway keys destroyed)"
