#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Download the scanners the security pipeline uses, pinned by version + sha256 (os/versions.lock.yaml,
# tools.trivy / tools.syft; brief 30 §2 rule 2). ClamAV runs as a digest-pinned container instead
# (tools.clamav), because its signatures must be fresh on every run (freshclam).
#   os/update/fetch-tools.sh <bindir>      (linux amd64 or arm64)
set -eu
BIN=$1; mkdir -p "$BIN"
case "$(uname -m)" in
  x86_64|amd64) A=amd64 ;;
  aarch64|arm64) A=arm64 ;;
  *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;;
esac
TRIVY_VERSION=0.76.2
SYFT_VERSION=1.55.0
if [ $A = amd64 ]; then
  TRIVY_TGZ=trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz
  TRIVY_SHA=bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf
  SYFT_SHA=bb65249542db5fedeeb4d3f9b018b75e7264dbfbbb10486f044581a92f90490d
else
  TRIVY_TGZ=trivy_${TRIVY_VERSION}_Linux-ARM64.tar.gz
  TRIVY_SHA=ab9d51f86e6a5fb936f605faff6b593ac51bc378fff4d3e8b9d58358b9c367c3
  SYFT_SHA=929bd163db2d7cd2255d3bcb8967208079813d7b46b0c952f7b794d8e2c7d304
fi
SYFT_TGZ=syft_${SYFT_VERSION}_linux_$A.tar.gz
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
get() {  # url file sha256
  curl -fsSL --retry 5 -o "$T/$2" "$1"
  echo "$3  $T/$2" | sha256sum -c - >/dev/null || { echo "sha256 mismatch: $2" >&2; exit 1; }
}
get "https://github.com/aquasecurity/trivy/releases/download/v$TRIVY_VERSION/$TRIVY_TGZ" "$TRIVY_TGZ" "$TRIVY_SHA"
get "https://github.com/anchore/syft/releases/download/v$SYFT_VERSION/$SYFT_TGZ" "$SYFT_TGZ" "$SYFT_SHA"
tar -xzf "$T/$TRIVY_TGZ" -C "$BIN" trivy
tar -xzf "$T/$SYFT_TGZ" -C "$BIN" syft
"$BIN/trivy" --version | head -n1
"$BIN/syft" version | sed -n 's/^Version: *//p'
