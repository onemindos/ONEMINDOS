#!/bin/bash
# LAB-rauc-1152: build RAUC from the pinned upstream tag, for arm64 (this VM,
# used to create bundles) and amd64 (installed into the test image), then run
# T12 (CVE-2026-34155 regression at bundle creation).
# Run as root INSIDE the disposable Debian 13 Lima VM. Never on the host.
#   sudo OUT=/var/lab/r1152-out bash build-rauc.sh
set -euo pipefail
TAG=v1.15.2
COMMIT=4fb7c798d6ae412344fb8f8d310d773046af3441
B=${B:-/var/lab/raucbuild}; OUT=${OUT:?set OUT}
log(){ echo "[build-rauc $(date -u +%T)] $*"; }
MESON_OPTS="--prefix=/usr --buildtype=release -Dtests=false -Dhtmldocs=false -Dmanpages=false \
 -Dsystemdunitdir=/usr/lib/systemd/system -Dsystemdcatalogdir=/usr/lib/systemd/catalog \
 -Ddbuspolicydir=/usr/share/dbus-1/system.d -Ddbussystemservicedir=/usr/share/dbus-1/system-services \
 -Ddbusinterfacesdir=/usr/share/dbus-1/interfaces"
DEPS="build-essential meson ninja-build pkgconf libglib2.0-dev libssl-dev libjson-glib-dev libdbus-1-dev libfdisk-dev libcurl4-openssl-dev libnl-genl-3-dev"
rm -rf "$B"; mkdir -p "$B" "$OUT"

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

log "amd64 build chroot (qemu-user)"
mmdebstrap --mode=root --arch=amd64 --variant=buildd --include="${DEPS// /,}" \
  trixie "$B/chroot-amd64" "deb http://deb.debian.org/debian trixie main" 2>&1 | tail -2
cp -a "$B/src" "$B/chroot-amd64/src"
chroot "$B/chroot-amd64" sh -c "meson setup $MESON_OPTS /build /src >/dev/null && ninja -C /build >/dev/null && /build/rauc --version && DESTDIR=/dest meson install -C /build --no-rebuild >/dev/null"
( cd "$B/chroot-amd64/dest" && find . -type f | sort ) | tee "$OUT/rauc-amd64-files.txt"
tar -C "$B/chroot-amd64/dest" -cf "$OUT/rauc-amd64-dest.tar" .
chroot "$B/chroot-amd64" sh -c 'ldd /dest/usr/bin/rauc | awk "/=>/{print \$3}" | xargs -r realpath | sed "s|^/lib/|/usr/lib/|" | xargs -r dpkg -S 2>/dev/null | cut -d: -f1 | sort -u' | tee "$OUT/rauc-amd64-runtime-pkgs.txt"
chroot "$B/chroot-amd64" dpkg-query -W -f='${Package} ${Version}\n' $DEPS libglib2.0-0t64 libssl3t64 2>/dev/null > "$OUT/rauc-amd64-builddeps.txt" || true
( cd "$OUT" && sha256sum rauc-arm64 rauc-amd64-dest.tar ) | tee "$OUT/rauc-build.sha256"

# ---------------------------------------------------------------- T12
log "T12: CVE-2026-34155 regression at bundle creation (2.1 GiB payload)"
T=$B/t12; mkdir -p "$T/keys" "$T/content"; cd "$T/keys"
openssl req -x509 -newkey rsa:3072 -nodes -days 3 -sha256 -keyout k.pem -out c.pem -subj "/O=OneMind LAB/CN=t12" 2>/dev/null
head -c 2150M /dev/urandom > "$T/content/rootfs.ext4"     # incompressible, > 2 GiB after squashfs
mf(){ printf '[update]\ncompatible=t12\nversion=1\n\n[bundle]\nformat=%s\n\n[image.rootfs]\nfilename=rootfs.ext4\n' "$1" > "$T/content/manifest.raucm"; }
t12(){ # $1 label $2 rauc-binary $3 format
  mf "$3"; rm -f "$T/out.raucb"
  if "$2" bundle --cert="$T/keys/c.pem" --key="$T/keys/k.pem" "$T/content" "$T/out.raucb" > "$T/$1.log" 2>&1; then
    echo "T12 $1: CREATED $(stat -c %s "$T/out.raucb") bytes"
  else echo "T12 $1: REFUSED: $(grep -E -o 'exceeds[^"]*|Error[^"]*' "$T/$1.log" | head -1)"; fi
  rm -f "$T/out.raucb"
}
echo "control binary: $(/usr/bin/rauc --version) ($(dpkg-query -W -f='${Version}' rauc))"
t12 debian-1.13-plain /usr/bin/rauc plain
t12 upstream-1.15.2-plain "$B/arm64/rauc" plain
t12 upstream-1.15.2-verity "$B/arm64/rauc" verity
rm -rf "$T/content"
log done
