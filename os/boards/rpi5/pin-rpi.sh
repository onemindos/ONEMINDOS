#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Board rpi5, maintainer tool: print the pins for fetch-rpi.sh and os/versions.lock.yaml from
# archive.raspberrypi.com, verifying the whole chain first:
#   keyring deb (pinned sha256) -> key fingerprint (pinned) -> InRelease signature (gpgv)
#   -> Packages.gz sha256 (from InRelease) -> each deb's pool path and sha256 (from Packages).
# Run on Linux (needs curl, gpg, gpgv, dpkg-deb); never on the image. It changes no file: copy its
# output into fetch-rpi.sh, os/versions.lock.yaml (rpi5) and re-run `make test`.
#   pin-rpi.sh [kernel-version]      # default: the version in the current index, e.g. 6.18.60
set -eu
BASE=https://archive.raspberrypi.com/debian
KEYRING_DEB=pool/main/r/raspberrypi-archive-keyring/raspberrypi-archive-keyring_2025.1+rpt1_all.deb
KEYRING_SHA=2e727149d7acb8cc7f604e66d0049161039c8aa1eaf1175e54f9e69d963d60e4
FPR=CF8A1AF502A2AA2D763BAE7E82B129927FA3303E
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
curl -fsSL --proto '=https' -o "$T/k.deb" "$BASE/$KEYRING_DEB"
echo "$KEYRING_SHA  $T/k.deb" | sha256sum -c - >/dev/null
dpkg-deb -x "$T/k.deb" "$T/k"
KR=$T/k/usr/share/keyrings/raspberrypi-archive-keyring.gpg
gpg --show-keys --with-colons "$KR" 2>/dev/null | grep -q "^fpr:::::::::$FPR:" || { echo "key fingerprint is not $FPR" >&2; exit 1; }
curl -fsSL --proto '=https' -o "$T/InRelease" "$BASE/dists/trixie/InRelease"
gpgv --keyring "$KR" "$T/InRelease" 2>"$T/gpgv" || { cat "$T/gpgv" >&2; exit 1; }
grep -q "$FPR" "$T/gpgv" || { echo "InRelease not signed by $FPR" >&2; exit 1; }
want=$(awk '/^SHA256:/{f=1;next} /^[A-Z]/{f=0} f && $3=="main/binary-arm64/Packages.gz"{print $1}' "$T/InRelease")
curl -fsSL --proto '=https' -o "$T/Packages.gz" "$BASE/dists/trixie/main/binary-arm64/Packages.gz"
echo "$want  $T/Packages.gz" | sha256sum -c - >/dev/null
gunzip "$T/Packages.gz"
V=${1:-$(awk '$0=="Package: linux-image-rpi-2712"{f=1} f&&/^Version:/{sub(/^1:/,"",$2); print $2; exit}' "$T/Packages")}
K=${V%%-*}
echo "# InRelease $(sed -n 's/^Date: //p' "$T/InRelease"), signed by $FPR; kernel $V"
for p in "linux-base-$K+rpt-rpi-2712" "linux-image-$K+rpt-rpi-2712" "linux-base-$K+rpt-rpi-v8" "linux-image-$K+rpt-rpi-v8"; do
  awk -v p="$p" '$0=="Package: "p{f=1} f&&/^Filename:/{fn=$2} f&&/^SHA256:/{print fn, $2; exit}' "$T/Packages" | grep . \
    || { echo "$p not in the current index (older pins: read the pool, then sha256 the file)" >&2; exit 1; }
done
