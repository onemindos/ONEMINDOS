#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build everything deploy/install.sh needs for one CPU architecture, on the Mac,
# from this checkout, into out/bundle-<arch>/ (git-ignored):
#
#   onemindd-linux-<arch>               node agent (cmd/onemindd), static binary
#   onemind-gateway-linux-<arch>.tar    gateway image (core/Dockerfile), for k3s to import
#   dashboard/                          built dashboard (dashboard/, served by the gateway)
#   SHA256SUMS                          checked by install.sh --bundle before anything is used
#
#   ./deploy/bundle.sh --arch amd64     # Beelink, DigitalOcean droplet
#   ./deploy/bundle.sh --arch arm64     # Raspberry Pi 5, Jetson
#   ./deploy/bundle.sh --arch arm64 --node-only    # only onemindd (nodes need nothing else)
#
# Then copy it next to a clone of the repo on the machine, for example:
#   rsync -a out/bundle-amd64/ <user>@<machine>:onemind-bundle/
# Needs: Docker (buildx). Go is used for onemindd when present, else a Go container.
set -euo pipefail

ARCH=""
NODE_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --arch) ARCH="${2:-}"; shift 2 ;;
    --node-only) NODE_ONLY=1; shift ;;
    -h|--help) sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
case "$ARCH" in amd64|arm64) ;; *) echo "usage: $0 --arch amd64|arm64 [--node-only]" >&2; exit 2 ;; esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/out/bundle-$ARCH"
GO_IMAGE="golang:1.26.11-alpine@sha256:ae52b5bc6ed045a9ed26ab03dc19327a802a9cc9aa8b27ed57f5c6b60579b0bb"
NODE_IMAGE="node:22.23.5-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a"
LDFLAGS="-s -w -buildid= -X github.com/onemindos/onemindos/internal/version.Version=0.1.0+$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo dev)"

mkdir -p "$OUT"
cd "$REPO"

echo "==> onemindd linux/$ARCH"
if command -v go >/dev/null 2>&1; then
  CGO_ENABLED=0 GOOS=linux GOARCH="$ARCH" go build -trimpath -ldflags "$LDFLAGS" -o "$OUT/onemindd-linux-$ARCH" ./cmd/onemindd
else
  docker run --rm -v "$REPO:/src:ro" -v "$OUT:/out" -w /src -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH="$ARCH" \
    -e GOFLAGS=-buildvcs=false "$GO_IMAGE" go build -trimpath -ldflags "$LDFLAGS" -o "/out/onemindd-linux-$ARCH" ./cmd/onemindd
fi

if [ "$NODE_ONLY" -eq 0 ]; then
  echo "==> gateway image linux/$ARCH (core/Dockerfile, repo root as context)"
  docker buildx build --platform "linux/$ARCH" -f core/Dockerfile -t onemind/gateway:dev \
    -o "type=docker,dest=$OUT/onemind-gateway-linux-$ARCH.tar" .

  echo "==> dashboard (npm ci && npm run build in a pinned Node container)"
  rm -rf "$OUT/dashboard"
  mkdir -p "$OUT/dashboard"
  docker run --rm -v "$REPO/dashboard:/src:ro" -v "$OUT/dashboard:/out" --tmpfs /work:exec,size=1g -w /work "$NODE_IMAGE" \
    sh -euc 'cd /src && tar --exclude=./node_modules --exclude=./dist -cf - . | tar -C /work -xf - && cd /work && npm ci --no-audit --no-fund >/dev/null && npm run build >/dev/null && cp -a dist/. /out/'
  [ -f "$OUT/dashboard/index.html" ] || { echo "dashboard build produced no index.html" >&2; exit 1; }
fi

echo "==> SHA256SUMS"
(
  cd "$OUT"
  files="onemindd-linux-$ARCH"
  [ "$NODE_ONLY" -eq 1 ] || files="$files onemind-gateway-linux-$ARCH.tar"
  # shellcheck disable=SC2086
  if command -v sha256sum >/dev/null 2>&1; then sha256sum $files; else shasum -a 256 $files; fi > SHA256SUMS
  cat SHA256SUMS
)
echo
echo "Bundle ready: out/bundle-$ARCH/  (copy it to the machine and run install.sh with --bundle <dir>)"
