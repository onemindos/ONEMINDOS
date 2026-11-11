#!/bin/bash
# Runs on the macOS HOST. Downloads the pinned binaries and verifies them against the upstream checksum files.
set -euo pipefail
LAB=${LAB:-$HOME/<lab-dir>/k3s-footprint-restore}; mkdir -p "$LAB/dl" "$LAB/xfer"; cd "$LAB/dl"
V='v1.37.2%2Bk3s1'
curl -sSfLO "https://github.com/k3s-io/k3s/releases/download/$V/k3s-arm64"
curl -sSfLO "https://github.com/k3s-io/k3s/releases/download/$V/sha256sum-arm64.txt"
grep ' k3s-arm64$' sha256sum-arm64.txt | shasum -a 256 -c -
curl -sSfL -o install.sh "https://raw.githubusercontent.com/k3s-io/k3s/$V/install.sh"
echo "ed01f89fd977bf20ac1516bbebf8370bf3ddbaa55dac8aba610956a4c78cc00b  install.sh" | shasum -a 256 -c -
curl -sSfLO https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_linux_arm64.bz2
curl -sSfLO https://github.com/restic/restic/releases/download/v0.19.1/SHA256SUMS
grep linux_arm64.bz2 SHA256SUMS | shasum -a 256 -c -
bunzip2 -kf restic_0.19.1_linux_arm64.bz2
