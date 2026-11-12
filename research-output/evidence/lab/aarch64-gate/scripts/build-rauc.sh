#!/bin/bash
# LAB-aarch64-gate: build RAUC from the pinned upstream tag natively for arm64.
# The same binary creates the bundles (in the build VM) and is installed into
# the arm64 test image (meson install --destdir). Derived from
# ../../rauc-1152/scripts/build-rauc.sh (the amd64 chroot and T12 are dropped).
# Run as root INSIDE the disposable Debian 13 arm64 Lima VM. Never on the host.
#   sudo OUT=/var/lab/a64-out bash build-rauc.sh
set -euo pipefail
TAG=v1.15.2
COMMIT=4fb7c798d6ae412344fb8f8d310d773046af3441
B=${B:-/var/lab/raucbuild}; OUT=${OUT:?set OUT}
log(){ echo "[build-rauc $(date -u +%T)] $*"; }
MESON_OPTS="--prefix=/usr --buildtype=release -Dtests=false -Dhtmldocs=false -Dmanpages=false \
 -Dsystemdunitdir=/usr/lib/systemd/system -Dsystemdcatalogdir=/usr/lib/systemd/catalog \
 -Ddbuspolicydir=/usr/share/dbus-1/system.d -Ddbussystemservicedir=/usr/share/dbus-1/system-services \
 -Ddbusinterfacesdir=/usr/share/dbus-1/interfaces"
rm -rf "$B"; mkdir -p "$B" "$OUT"
[ "$(uname -m)" = aarch64 ] || { echo "ERROR: run on arm64"; exit 1; }

log "clone $TAG (shallow) and check the commit"
git clone -q --depth 1 --branch "$TAG" https://github.com/rauc/rauc.git "$B/src"
HEAD=$(git -C "$B/src" rev-parse HEAD)
[ "$HEAD" = "$COMMIT" ] || { echo "ERROR: $TAG is $HEAD, expected $COMMIT"; exit 1; }
echo "rauc $TAG HEAD=$HEAD tagobj=$(git -C "$B/src" rev-parse "refs/tags/$TAG" 2>/dev/null || echo n/a)"
git -C "$B/src" archive --format=tar "$COMMIT" | sha256sum | sed 's/-$/rauc-src.tar (git archive)/' | tee "$OUT/rauc-src.sha256"

log "arm64 native build"
meson setup $MESON_OPTS "$B/arm64" "$B/src" >/dev/null
ninja -C "$B/arm64" >/dev/null
"$B/arm64/rauc" --version
install -m 755 "$B/arm64/rauc" "$OUT/rauc-arm64"
DESTDIR="$B/dest" meson install -C "$B/arm64" --no-rebuild >/dev/null
( cd "$B/dest" && find . -type f | sort ) | tee "$OUT/rauc-arm64-files.txt"
tar -C "$B/dest" -cf "$OUT/rauc-arm64-dest.tar" .
ldd "$B/arm64/rauc" | awk '/=>/{print $3}' | xargs -r realpath | sed 's|^/lib/|/usr/lib/|' \
  | xargs -r dpkg -S 2>/dev/null | cut -d: -f1 | sort -u | tee "$OUT/rauc-arm64-runtime-pkgs.txt"
dpkg-query -W -f='${Package} ${Version}\n' gcc meson ninja-build libglib2.0-dev libssl-dev libcurl4-openssl-dev \
  libjson-glib-dev libdbus-1-dev libfdisk-dev libnl-genl-3-dev > "$OUT/rauc-arm64-builddeps.txt"
( cd "$OUT" && sha256sum rauc-arm64 rauc-arm64-dest.tar ) | tee "$OUT/rauc-build.sha256"
echo "rauc-1152 arm64 binary sha256 for comparison (H3): 7f076b8b8ab7882dd4522952d511354c9d23690280945965ec14ad0009639d1f"
log done
