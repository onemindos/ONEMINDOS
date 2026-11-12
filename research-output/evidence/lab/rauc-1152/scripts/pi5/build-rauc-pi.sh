#!/bin/bash
# LAB-rauc-1152 Pi 5 founder test: build RAUC v1.15.2 from the pinned upstream
# tag on the workbench (Raspberry Pi OS trixie, arm64) into $RAUC_DEST.
# SPDX-License-Identifier: Apache-2.0
#   sudo bash build-rauc-pi.sh
set -euo pipefail
TAG=v1.15.2; COMMIT=4fb7c798d6ae412344fb8f8d310d773046af3441
B=${B:-/root/raucbuild}; RAUC_DEST=${RAUC_DEST:-/root/rauc-1.15.2-dest}
export DEBIAN_FRONTEND=noninteractive
apt-get update -q >/dev/null
apt-get install -y -q git build-essential meson ninja-build pkgconf libglib2.0-dev libssl-dev libjson-glib-dev \
  libdbus-1-dev libfdisk-dev libcurl4-openssl-dev libnl-genl-3-dev squashfs-tools dosfstools rsync openssl curl >/dev/null
rm -rf "$B" "$RAUC_DEST"
git clone -q -c advice.detachedHead=false --depth 1 --branch $TAG https://github.com/rauc/rauc.git "$B/src"
[ "$(git -C "$B/src" rev-parse HEAD)" = $COMMIT ] || { echo "ERROR: $TAG is not $COMMIT"; exit 1; }
meson setup --prefix=/usr --buildtype=release -Dtests=false -Dhtmldocs=false -Dmanpages=false \
  -Dsystemdunitdir=/usr/lib/systemd/system -Dsystemdcatalogdir=/usr/lib/systemd/catalog \
  -Ddbuspolicydir=/usr/share/dbus-1/system.d -Ddbussystemservicedir=/usr/share/dbus-1/system-services \
  -Ddbusinterfacesdir=/usr/share/dbus-1/interfaces "$B/build" "$B/src" >/dev/null
ninja -C "$B/build" >/dev/null
DESTDIR=$RAUC_DEST meson install -C "$B/build" --no-rebuild >/dev/null
"$RAUC_DEST/usr/bin/rauc" --version
sha256sum "$RAUC_DEST/usr/bin/rauc"
