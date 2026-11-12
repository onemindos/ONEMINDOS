#!/bin/bash
# Runs in the Bakery container (native arch). Downloads k3s + air-gap images for the
# target arch, verifies them against the release's sha256sum file, and copies them in.
set -euo pipefail
V="${RECIPE_PARAM_VERSION}"
VU="${V//+/%2B}"
case "${RUGIX_ARCH}" in
  amd64) BIN=k3s; SUM=sha256sum-amd64.txt; IMG=k3s-airgap-images-amd64.tar.zst ;;
  arm64) BIN=k3s-arm64; SUM=sha256sum-arm64.txt; IMG=k3s-airgap-images-arm64.tar.zst ;;
  *) echo "unsupported arch ${RUGIX_ARCH}"; exit 1 ;;
esac
DL="/project/.downloads/k3s-${V}"
mkdir -p "$DL"
for f in "$BIN" "$SUM" "$IMG"; do
  [ -s "$DL/$f" ] || curl -fsSL --retry 3 -o "$DL/$f" "https://github.com/k3s-io/k3s/releases/download/${VU}/$f"
done
( cd "$DL" && grep -E " (${BIN}|${IMG})\$" "$SUM" | sha256sum -c - )
install -D -m 755 "$DL/$BIN" "${RUGIX_ROOT_DIR}/usr/local/bin/k3s"
install -D -m 644 "$DL/$IMG" "${RUGIX_ROOT_DIR}/usr/lib/onemind/k3s-airgap-images.tar.zst"
