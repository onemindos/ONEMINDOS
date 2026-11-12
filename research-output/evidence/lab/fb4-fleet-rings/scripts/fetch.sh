#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# T0 for both spikes: Debian packages, pinned downloads checked against the pin AND the upstream
# checksum file, FDO builds from pinned module versions (sum.golang.org verified).
set -euo pipefail; S=$(cd "$(dirname "$0")" && pwd); . $S/lib.sh
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq curl jq sqlite3 openssl ca-certificates unzip gcc libc6-dev swtpm swtpm-tools tpm2-tools docker.io iptables >/dev/null
echo "== debian packages"; dpkg-query -W -f='${Package} ${Version}\n' sqlite3 openssl swtpm tpm2-tools docker.io iptables
mkdir -p $B/dl; cd $B/dl
get(){ [ -f "$2" ] || curl -fsSL -o "$2" "$1"; }
chk(){ local got; got=$(sha256sum "$1"|cut -d' ' -f1); [ "$got" = "$2" ] || { echo "T0 FAIL hash $1 got=$got want=$2"; exit 1; }; echo "sha256 OK pin $1 $got"; }
up(){ grep -q "$2" "$1" && echo "sha256 OK upstream-file $1 contains $2" || { echo "T0 FAIL $2 not in $1"; exit 1; }; }
GO_V=1.27.4; GO_SHA=3392582988a273a87ab5043ee1b2c9c17a2c3c00580bf9326c47a2e0aaaeac92
K3D_V=5.9.0; K3D_SHA=03cde5cf23e6e8e67de5a039ecf26e5b85aca82fba3e5d13dadf904cd218a250
HELM_V=3.22.1; HELM_SHA=4c29e286b279d170fa048ddfc3e4e83dcd069ca9c52102766ba672d7149e694d
FL_V=0.16.3; FL_CRD=fd3e5641d72c121da51eb428121b4fd4d0feed7dcf410b44bca4cd5dc3ef141b; FL_CH=1a4b7304314cf11c0c6f45cc2fc752e9aa828b70824cd3fe96bfb2dbd2b69bbc; FL_CLI=a0c2e18c7d84f119275ef6f5c4a67ad51fa83f4b0e932db326850045652311f4
get https://go.dev/dl/go$GO_V.linux-arm64.tar.gz go.tgz; chk go.tgz $GO_SHA
rm -rf /opt/go && tar xzf go.tgz -C /opt
get https://github.com/k3d-io/k3d/releases/download/v$K3D_V/k3d-linux-arm64 k3d; get https://github.com/k3d-io/k3d/releases/download/v$K3D_V/checksums.txt k3d-checksums.txt
chk k3d $K3D_SHA; up k3d-checksums.txt "$K3D_SHA"
get https://get.helm.sh/helm-v$HELM_V-linux-arm64.tar.gz helm.tgz; get https://get.helm.sh/helm-v$HELM_V-linux-arm64.tar.gz.sha256sum helm.sha256sum
chk helm.tgz $HELM_SHA; up helm.sha256sum "$HELM_SHA"
FR=https://github.com/rancher/fleet/releases/download/v$FL_V
get $FR/fleet_${FL_V}_checksums.txt fleet-checksums.txt
for f in fleet-crd-$FL_V.tgz fleet-$FL_V.tgz fleet-agent-$FL_V.tgz fleet-linux-arm64; do get $FR/$f $f; h=$(sha256sum $f|cut -d' ' -f1); up fleet-checksums.txt "$h"; done
chk fleet-crd-$FL_V.tgz $FL_CRD; chk fleet-$FL_V.tgz $FL_CH; chk fleet-linux-arm64 $FL_CLI
install -m755 k3d $B/bin/k3d; tar xzf helm.tgz && install -m755 linux-arm64/helm $B/bin/helm; install -m755 fleet-linux-arm64 $B/bin/fleet
export GOPATH=$B/gopath GOCACHE=$B/gocache GOTOOLCHAIN=local GOFLAGS=-mod=readonly CGO_ENABLED=1
GOBIN=$B/bin go install github.com/fido-device-onboard/go-fdo-server@v1.0.2
GOBIN=$B/bin go install github.com/fido-device-onboard/go-fdo-client@v1.0.0
echo "== versions"; go version; k3d version | head -2; helm version --short; fleet --version 2>&1 | head -1 || true
go version -m $B/bin/go-fdo-server | grep -E "^\s+(path|mod)\s|go-fdo\s" | head -4
go version -m $B/bin/go-fdo-client | grep -E "^\s+(path|mod)\s|go-fdo\s" | head -4
sha256sum $B/bin/*
