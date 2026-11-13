#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Pinned downloads for the OneMind layer (version + sha256 in os/versions.lock.yaml, onemind_layer).
#   fetch-onemind.sh go|node|uv|nats <amd64|arm64> <dest-dir>
# go/node/uv are build toolchains (builder stages only); nats-server ships in the image.
set -eu
WHAT=$1; ARCH=$2; DEST=$3
GO_VERSION=1.26.11
NODE_VERSION=v24.22.3
UV_VERSION=0.13.7
NATS_VERSION=v2.15.2
case "$WHAT-$ARCH" in
go-amd64)   URL=https://go.dev/dl/go$GO_VERSION.linux-amd64.tar.gz;  SHA=9849f4e04ee35303714e34fbc3ac8ab44ea3e448a95aa182f91e3b9b79c710ec ;;
go-arm64)   URL=https://go.dev/dl/go$GO_VERSION.linux-arm64.tar.gz;  SHA=6c2f29b458b5add0835f18b776f69c8881a6d88428f1484a6da55755e620757e ;;
node-amd64) URL=https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.gz;   SHA=061ec3e3062115705b56b51fa9cc330ab50d34b6969387d4e4b1a50c6809acc2 ;;
node-arm64) URL=https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-arm64.tar.gz; SHA=261af2af250dfd7e9f25cf151d1b2713a0adf8f10a9ad116c4947f68627affe8 ;;
uv-amd64)   URL=https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz;  SHA=c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83 ;;
uv-arm64)   URL=https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-unknown-linux-gnu.tar.gz; SHA=71279f8d3c67241e807b9d8db872d1bf541579fb9f08b7d1eb1682196d1e57dc ;;
nats-amd64) URL=https://github.com/nats-io/nats-server/releases/download/$NATS_VERSION/nats-server-$NATS_VERSION-linux-amd64.tar.gz; SHA=67cb8e10bc6f0c4b47f75a728529a20953dbae2a4f9a4a52ae8517d65ae303ff
            BIN_SHA=33f3fe3fed80b2b229bd9fe4b735257ad8583cd2349452a0c74f3d768b593e66 ;;
nats-arm64) URL=https://github.com/nats-io/nats-server/releases/download/$NATS_VERSION/nats-server-$NATS_VERSION-linux-arm64.tar.gz; SHA=bc2c788dcbf2849af749564e06a0d48c19bced851f2d68a2e21c54d078949b28
            BIN_SHA=9f03b5f7b53b1d3dd3474dce5744b4b55149ceafd8bbeded0ae4c27695c4aeb4 ;;
*) echo "fetch-onemind.sh: unknown $WHAT for $ARCH" >&2; exit 1 ;;
esac
T=$(mktemp -d)
curl -fsSL --retry 5 --proto '=https' -o "$T/a.tgz" "$URL"
echo "$SHA  $T/a.tgz" | sha256sum -c -
mkdir -p "$DEST"
tar -xzf "$T/a.tgz" -C "$DEST" --strip-components=1 --no-same-owner
if [ "$WHAT" = nats ]; then
  echo "$BIN_SHA  $DEST/nats-server" | sha256sum -c -
fi
rm -rf "$T"
echo "$WHAT ($ARCH) from $URL: sha256 verified"
