#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Pinned downloads for the OneMind layer (version + sha256 in os/versions.lock.yaml, onemind_layer).
#   fetch-onemind.sh go|node|uv|nats|tailscale|headscale|restic <amd64|arm64> <dest-dir>
# go/node/uv are build toolchains (builder stages only); nats-server, tailscale/tailscaled and headscale ship in the image.
# restic is one bzip2-compressed binary (needs bunzip2): it lands in <dest-dir>/restic, checked against the sha256
# the backup agent enforces at every start (internal/backup/pins.go).
# headscale is one binary, not a tarball: it lands in <dest-dir>/headscale.
set -eu
WHAT=$1; ARCH=$2; DEST=$3
GO_VERSION=1.26.11
NODE_VERSION=v24.22.3
UV_VERSION=0.13.7
NATS_VERSION=v2.15.2
TAILSCALE_VERSION=1.104.6
HEADSCALE_VERSION=0.29.7
RESTIC_VERSION=0.19.1
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
tailscale-amd64) URL=https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_amd64.tgz; SHA=82a85429f733e52fd1a95dedb2c8dd8cd46d6603504e566a56b1779c9a7a4809
            BIN_SHA=a781895a86932424dce380c8b445c77b8568dd2248a7fed20ba77ce3cb221185
            BIN2_SHA=01106e93593dfe01ba6d8615ba5de40222ce3e54797525cc66ef7795f682c216 ;;
tailscale-arm64) URL=https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_arm64.tgz; SHA=d0e4f297da3c428d02162c6235b9948e4ddc245c64502b7b05647da9b96a0971
            BIN_SHA=2e547c5e8acb4e9dc7c3ae576c302346044bd2f30958515cca5b7a91fb5cd636
            BIN2_SHA=904044a58d6b22426fa2ff2307f774dc69c0edda0c5053bc3de53fb11a0b8e40 ;;
headscale-amd64) URL=https://github.com/juanfont/headscale/releases/download/v$HEADSCALE_VERSION/headscale_${HEADSCALE_VERSION}_linux_amd64; SHA=e827fc9b12d958bc95b081c4401dd63f8e0471d025b45b508535a920532150a8 ;;
headscale-arm64) URL=https://github.com/juanfont/headscale/releases/download/v$HEADSCALE_VERSION/headscale_${HEADSCALE_VERSION}_linux_arm64; SHA=4357b38ac63c1e425f190819fd2ee078f13e01a6d7559b15811154e2475df5e4 ;;
restic-amd64) URL=https://github.com/restic/restic/releases/download/v$RESTIC_VERSION/restic_${RESTIC_VERSION}_linux_amd64.bz2; SHA=f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c
            BIN_SHA=20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639 ;;
restic-arm64) URL=https://github.com/restic/restic/releases/download/v$RESTIC_VERSION/restic_${RESTIC_VERSION}_linux_arm64.bz2; SHA=a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465
            BIN_SHA=2fb45ac6f9071b6f20eb883953a188f9e7c7cb6bbe43c67a2e47ada4e85ee7f0 ;;
*) echo "fetch-onemind.sh: unknown $WHAT for $ARCH" >&2; exit 1 ;;
esac
T=$(mktemp -d)
curl -fsSL --retry 5 --proto '=https' -o "$T/a.dl" "$URL"
echo "$SHA  $T/a.dl" | sha256sum -c -
mkdir -p "$DEST"
if [ "$WHAT" = headscale ]; then
  install -m 0755 "$T/a.dl" "$DEST/headscale"
elif [ "$WHAT" = restic ]; then
  bunzip2 -c "$T/a.dl" > "$T/restic"
  echo "$BIN_SHA  $T/restic" | sha256sum -c -
  install -m 0755 "$T/restic" "$DEST/restic"
else
  tar -xzf "$T/a.dl" -C "$DEST" --strip-components=1 --no-same-owner
fi
if [ "$WHAT" = nats ]; then
  echo "$BIN_SHA  $DEST/nats-server" | sha256sum -c -
fi
if [ "$WHAT" = tailscale ]; then
  echo "$BIN_SHA  $DEST/tailscale" | sha256sum -c -
  echo "$BIN2_SHA  $DEST/tailscaled" | sha256sum -c -
fi
rm -rf "$T"
echo "$WHAT ($ARCH) from $URL: sha256 verified"
