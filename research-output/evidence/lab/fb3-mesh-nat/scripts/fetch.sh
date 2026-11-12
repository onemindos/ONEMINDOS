#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-fb3-mesh-nat T0: fetch pinned binaries inside the disposable VM, verify sha256
# against the pin AND the upstream checksum file, build derper from the pinned tag.
set -euo pipefail
B=/opt/fb3; mkdir -p $B/dl $B/bin; cd $B/dl
HS_V=0.29.7;  HS_SHA=4357b38ac63c1e425f190819fd2ee078f13e01a6d7559b15811154e2475df5e4
TS_V=1.104.6; TS_SHA=d0e4f297da3c428d02162c6235b9948e4ddc245c64502b7b05647da9b96a0971
NS_V=2.15.2;  NS_SHA=bc2c788dcbf2849af749564e06a0d48c19bced851f2d68a2e21c54d078949b28
NC_V=0.5.1;   NC_SHA=91c661f1173ee9bfe07514eef55a29d25ac7757a0868c179e825eba976073adc
GO_V=1.27.4;  GO_SHA=3392582988a273a87ab5043ee1b2c9c17a2c3c00580bf9326c47a2e0aaaeac92
get(){ [ -f "$2" ] || curl -fsSL -o "$2" "$1"; }
chk(){ local got; got=$(sha256sum "$1"|cut -d' ' -f1); [ "$got" = "$2" ] || { echo "T0 FAIL hash $1 got=$got want=$2"; exit 1; }; echo "sha256 OK pin $1 $got"; }
up(){ grep -q "$2" "$1" && echo "sha256 OK upstream-file $1 contains pin" || { echo "T0 FAIL $2 not in $1"; exit 1; }; }
get https://github.com/juanfont/headscale/releases/download/v$HS_V/headscale_${HS_V}_linux_arm64 headscale_${HS_V}_linux_arm64
get https://github.com/juanfont/headscale/releases/download/v$HS_V/checksums.txt headscale-checksums.txt
chk headscale_${HS_V}_linux_arm64 $HS_SHA; up headscale-checksums.txt "$HS_SHA  headscale_${HS_V}_linux_arm64"
get https://pkgs.tailscale.com/stable/tailscale_${TS_V}_arm64.tgz tailscale_${TS_V}_arm64.tgz
get https://pkgs.tailscale.com/stable/tailscale_${TS_V}_arm64.tgz.sha256 tailscale.sha256
chk tailscale_${TS_V}_arm64.tgz $TS_SHA; up tailscale.sha256 "$TS_SHA"
get https://github.com/nats-io/nats-server/releases/download/v$NS_V/nats-server-v$NS_V-linux-arm64.tar.gz nats-server-v$NS_V-linux-arm64.tar.gz
get https://github.com/nats-io/nats-server/releases/download/v$NS_V/SHA256SUMS nats-server-SHA256SUMS
chk nats-server-v$NS_V-linux-arm64.tar.gz $NS_SHA; up nats-server-SHA256SUMS "$NS_SHA"
get https://github.com/nats-io/natscli/releases/download/v$NC_V/nats-$NC_V-linux-arm64.zip nats-$NC_V-linux-arm64.zip
get https://github.com/nats-io/natscli/releases/download/v$NC_V/SHA256SUMS natscli-SHA256SUMS
chk nats-$NC_V-linux-arm64.zip $NC_SHA; up natscli-SHA256SUMS "$NC_SHA"
get https://go.dev/dl/go$GO_V.linux-arm64.tar.gz go$GO_V.linux-arm64.tar.gz
chk go$GO_V.linux-arm64.tar.gz $GO_SHA
install -m755 headscale_${HS_V}_linux_arm64 $B/bin/headscale
tar xzf tailscale_${TS_V}_arm64.tgz && install -m755 tailscale_${TS_V}_arm64/tailscale tailscale_${TS_V}_arm64/tailscaled $B/bin/
tar xzf nats-server-v$NS_V-linux-arm64.tar.gz && install -m755 nats-server-v$NS_V-linux-arm64/nats-server $B/bin/
unzip -oq nats-$NC_V-linux-arm64.zip && install -m755 nats-$NC_V-linux-arm64/nats $B/bin/
rm -rf /opt/go && tar xzf go$GO_V.linux-arm64.tar.gz -C /opt
# derper from the same tag as the client; GOFLAGS=-mod=readonly + GONOSUMDB unset => go.sum and sum.golang.org verify every module
export GOPATH=/opt/fb3/gopath GOCACHE=/opt/fb3/gocache GOTOOLCHAIN=local CGO_ENABLED=0
GOBIN=$B/bin /opt/go/bin/go install tailscale.com/cmd/derper@v$TS_V
echo "== versions"
/opt/go/bin/go version
$B/bin/headscale version 2>&1 | head -3
$B/bin/tailscale version | head -1; $B/bin/tailscaled --version | head -1
$B/bin/derper --version 2>&1 | head -1 || true
/opt/go/bin/go version -m $B/bin/derper | grep -E "^\s+(path|mod)\s" | head -3
$B/bin/nats-server --version; $B/bin/nats --version
sha256sum $B/bin/*
