#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Security-channel release for one board: rootfs tar -> system tree -> ext4 -> signed RAUC bundle
# (verity), plus release-<board>.json for os/update/tuf-repo.py. Runs in the tools container
# (os/rootfs/Containerfile target "tools"), like os/assemble/dev-image.sh.
#
# Keys (brief 30 B4.6, SB-10):
#   KEYDIR=/keys with signer.pem + signer.key (+ keyring.pem, the CA the image trusts; defaults to
#   signer.pem): the release keys, written there by CI from the ONEMIND_RAUC_* secrets.
#   No KEYDIR: a THROWAWAY CA and signer are made here and deleted on exit; the output is then a
#   dry run (release-<board>.json says "dry_run": true) and must never be published.
# OVERLAY=/dir (optional): extra files laid over the tree, e.g. a dry-run TUF root at
#   /usr/lib/onemind/tuf/security/root.json.
#
#   BOARD=x86_64-efi VERSION=0.1.20261112025704 SNAPSHOT=20261112T025704Z ROOTFS=/out/rootfs.tar \
#     build-release.sh /out/release-x86_64-efi
set -eu
OUTDIR=$1; : "${BOARD:?}" "${ROOTFS:?}" "${VERSION:?}" "${SNAPSHOT:?}"
SRC=$(cd "$(dirname "$0")/../.." && pwd)
W=$(mktemp -d /tmp/rel.XXXXXX); K=$(mktemp -d); trap 'rm -rf "$W" "$K"' EXIT
chmod 700 "$K"
DRY=true
if [ -n "${KEYDIR:-}" ] && [ -s "$KEYDIR/signer.pem" ] && [ -s "$KEYDIR/signer.key" ]; then
  cp "$KEYDIR/signer.pem" "$KEYDIR/signer.key" "$K/"
  if [ -s "$KEYDIR/keyring.pem" ]; then cp "$KEYDIR/keyring.pem" "$K/ca.pem"; else cp "$KEYDIR/signer.pem" "$K/ca.pem"; fi
  DRY=false
  echo "signing with the release key (subject: $(openssl x509 -in "$K/signer.pem" -noout -subject))"
else
  openssl req -x509 -newkey rsa:3072 -nodes -days 30 -sha256 -keyout "$K/ca.key" -out "$K/ca.pem" \
    -subj "/O=OneMind DEV (throwaway)/CN=dev-ca" 2>/dev/null
  openssl req -newkey rsa:3072 -nodes -sha256 -keyout "$K/signer.key" -out "$K/signer.csr" \
    -subj "/O=OneMind DEV (throwaway)/CN=dev-signer" 2>/dev/null
  openssl x509 -req -in "$K/signer.csr" -CA "$K/ca.pem" -CAkey "$K/ca.key" -CAcreateserial -days 30 -sha256 \
    -out "$K/signer.pem" -extfile "$SRC/os/assemble/signer.ext" 2>/dev/null
  echo "DRY RUN: no release key; signing with a throwaway CA (destroyed on exit)"
fi
set --
if [ -n "${OVERLAY:-}" ]; then set -- --overlay "$OVERLAY"; fi
A="python3 -I $SRC/os/assemble/assemble.py"
$A tree --board "$BOARD" --rootfs "$ROOTFS" --work "$W" --version "$VERSION" --keyring "$K/ca.pem" "$@"
$A ext4 --work "$W" --out "$W/system.ext4"
mkdir -p "$OUTDIR"
B="onemind-$BOARD-$VERSION"
$A bundle --board "$BOARD" --system "$W/system.ext4" --version "$VERSION" --cert "$K/signer.pem" \
  --key "$K/signer.key" --out "$OUTDIR/$B.raucb"
# The bundle must verify against the keyring the image ships (what a box will check).
rauc info --keyring="$K/ca.pem" "$OUTDIR/$B.raucb" > "$OUTDIR/$B.rauc-info.txt"
cp "$K/ca.pem" "$OUTDIR/$B.keyring.pem"
cp "$W/tree/usr/lib/onemind/packages.txt" "$OUTDIR/$B.packages.txt"
COMPAT=$(sed -n 's/^compatible: *//p' "$SRC/os/boards/$BOARD/board.yaml")
MINFROM=$(sed -n 's/.*"min_from_version": *"\([^"]*\)".*/\1/p' "$SRC/os/update/channel.json")
cat > "$OUTDIR/release-$BOARD.json" <<EOF
{
  "schema": "onemind.release/v1",
  "board": "$BOARD",
  "version": "$VERSION",
  "compatible": "$COMPAT",
  "min_from_version": "$MINFROM",
  "security": true,
  "snapshot": "$SNAPSHOT",
  "dry_run": $DRY,
  "files": {"bundle": "$B.raucb", "sbom": "$B.spdx.json", "cve_report": "$B.cve-report.json"}
}
EOF
(cd "$OUTDIR" && sha256sum "$B.raucb" > "$B.raucb.sha256")
echo "release ready: $OUTDIR/$B.raucb (dry_run=$DRY; keys destroyed)"
