#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Download k3s + air-gap images for this arch and verify the pinned sha256 (os/versions.lock.yaml).
#   fetch-k3s.sh <amd64|arm64> <rootfs-dir>
set -eu
ARCH=$1; R=$2
URL=https://github.com/k3s-io/k3s/releases/download/v1.37.2%2Bk3s1
case "$ARCH" in
amd64) BIN=k3s;       BIN_SHA=265b3ee6a3198ef14033c63ef46cbb32370d83795199fb6d1b01f21575eddbda
       IMG=k3s-airgap-images-amd64.tar.zst; IMG_SHA=35a5af1e69b57b8b627a4f6b1c29ea104209b661067b8c97fd40dc3f860bfcd2 ;;
arm64) BIN=k3s-arm64; BIN_SHA=a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b
       IMG=k3s-airgap-images-arm64.tar.zst; IMG_SHA=ca384f1a77aa83024bd82ad26fa4774971adb038e656a3b5b9af926be445a442 ;;
*) echo "unsupported arch $ARCH" >&2; exit 1 ;;
esac
T=$(mktemp -d)
curl -fsSL --retry 5 -o "$T/$BIN" "$URL/$BIN"
curl -fsSL --retry 5 -o "$T/$IMG" "$URL/$IMG"
printf '%s  %s\n%s  %s\n' "$BIN_SHA" "$T/$BIN" "$IMG_SHA" "$T/$IMG" | sha256sum -c -
install -D -m 755 "$T/$BIN" "$R/usr/local/bin/k3s"
install -D -m 644 "$T/$IMG" "$R/usr/lib/onemind/k3s-airgap-images.tar.zst"
rm -rf "$T"
echo "k3s v1.37.2+k3s1 ($ARCH) installed, sha256 verified"
