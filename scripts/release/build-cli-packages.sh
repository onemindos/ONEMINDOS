#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Build the onemind CLI packages for laptops (#882): .tar.gz for linux amd64/arm64 and macOS arm64/amd64,
# a .deb per Linux arch and a Homebrew formula, with shell completions and man pages made from the Cobra tree.
# Artifacts only (nothing is uploaded or signed here). Run from the repo root after `sh sdk/scripts/gen-code.sh go`.
#   scripts/release/build-cli-packages.sh <version> [out-dir]
set -eu
version=${1:?usage: build-cli-packages.sh <version> [out-dir]}
out=${2:-dist/cli}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export CGO_ENABLED=0 GOFLAGS=-mod=readonly SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct 2>/dev/null || echo 0)}"
ld="-s -w -buildid= -X github.com/onemindos/onemindos/internal/version.Version=$version"
mkdir -p "$work/bin" "$work/comp" "$work/man"
for t in linux/amd64 linux/arm64 darwin/arm64 darwin/amd64; do
  GOOS=${t%/*} GOARCH=${t#*/} go build -trimpath -buildvcs=false -ldflags "$ld" -o "$work/bin/onemind-${t%/*}-${t#*/}" ./cmd/onemind
done
# Completions and man pages are text: make them with a copy that runs on this machine.
go build -trimpath -buildvcs=false -o "$work/host-onemind" ./cmd/onemind
go build -trimpath -buildvcs=false -o "$work/host-mangen" ./cmd/onemind-mangen
"$work/host-onemind" completion bash > "$work/comp/onemind.bash"
"$work/host-onemind" completion zsh > "$work/comp/_onemind"
"$work/host-onemind" completion fish > "$work/comp/onemind.fish"
"$work/host-mangen" "$work/man" "$version"
gzip -9n "$work"/man/*.1
python3 -I scripts/release/cli-packages.py --version "$version" --bin-dir "$work/bin" --completions "$work/comp" \
  --man "$work/man" --out "$out"
