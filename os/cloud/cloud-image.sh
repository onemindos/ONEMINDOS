#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Cloud image for one cloud (docs/leap/core/CLOUD-IMAGES.md): assemble board cloud-<cloud> from the
# `cloud` rootfs plus the board's overlay/, sign its bundles with a THROWAWAY CA made here and
# deleted on exit (as os/assemble/dev-image.sh, brief 30 SB-10), then package the disk in the
# format that cloud imports (package.sh). Runs in the tools container:
#   VERSION=0.1.0-dev ROOTFS=/out/rootfs-debian-cloud.tar cloud-image.sh aws /out/image-cloud-aws
set -eu
CLOUD=$1; OUTDIR=$2; : "${ROOTFS:?}" "${VERSION:?}"
BOARD=cloud-$CLOUD
SRC=$(cd "$(dirname "$0")/../.." && pwd)
B=$SRC/os/boards/$BOARD
[ -f "$B/board.yaml" ] || { echo "unknown cloud '$CLOUD' (no os/boards/$BOARD)" >&2; exit 2; }
from=$(sed -n 's/^rootfs_from: *//p' "$B/board.yaml")
ovl=$(sed -n 's/^overlay: *//p' "$B/board.yaml")
# The rootfs must be the one this board is assembled from (its build-info names the board).
info=$(tar -xOf "$ROOTFS" --wildcards '*usr/lib/onemind/build-info.txt' 2>/dev/null || true)
case "$info" in *"board=$from "*) ;; *) echo "ERROR: $ROOTFS is not the '$from' rootfs ($info)" >&2; exit 2 ;; esac
K=$(mktemp -d); W=$(mktemp -d /tmp/work.XXXXXX); trap 'rm -rf "$K" "$W"' EXIT
openssl req -x509 -newkey rsa:3072 -nodes -days 30 -sha256 -keyout "$K/ca.key" -out "$K/ca.pem" \
  -subj "/O=OneMind DEV (throwaway)/CN=dev-ca" 2>/dev/null
openssl req -newkey rsa:3072 -nodes -sha256 -keyout "$K/signer.key" -out "$K/signer.csr" \
  -subj "/O=OneMind DEV (throwaway)/CN=dev-signer" 2>/dev/null
openssl x509 -req -in "$K/signer.csr" -CA "$K/ca.pem" -CAkey "$K/ca.key" -CAcreateserial -days 30 -sha256 \
  -out "$K/signer.pem" -extfile "$SRC/os/assemble/signer.ext" 2>/dev/null
mkdir -p "$OUTDIR"; rm -f "$OUTDIR/SHA256SUMS"
python3 -I "$SRC/os/assemble/assemble.py" image --board "$BOARD" --rootfs "$ROOTFS" --work "$W" \
  --version "$VERSION" --keyring "$K/ca.pem" --cert "$K/signer.pem" --key "$K/signer.key" \
  --out-dir "$OUTDIR" --overlay "$B/$ovl"
cp "$K/ca.pem" "$OUTDIR/dev-ca.cert.pem"
"$SRC/os/cloud/package.sh" "$CLOUD" "$OUTDIR"
echo "cloud image $BOARD ready in $OUTDIR (throwaway keys destroyed)"
