#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Build OneMind's own RAUC from the pinned upstream tag (brief 30 B4.1, REC-DEC-05/-31).
# Port of research-output/evidence/lab/rauc-1152/scripts/build-rauc.sh.
#   build-rauc.sh <destdir>      # installs into <destdir> (DESTDIR), prints the version
# Runs inside a Debian 13 (or Ubuntu 26.04) build container that already has the
# build dependencies (see os/rootfs/Containerfile stage "rauc-build"). Never on the Mac.
# Behaviour sources: meson DESTDIR install (https://mesonbuild.com/Installing.html),
# RAUC meson_options.txt at 4fb7c798 (https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/meson_options.txt).
set -eu
DEST=${1:?usage: build-rauc.sh <destdir>}
REPO=https://github.com/rauc/rauc.git
TAG=v1.15.2
COMMIT=4fb7c798d6ae412344fb8f8d310d773046af3441
SRC=${RAUC_SRC_DIR:-/tmp/rauc-src}
BUILD=${RAUC_BUILD_DIR:-/tmp/rauc-build}
log() { echo "[build-rauc] $*"; }

# 1. The tag must still point at the pinned commit (a moved tag is a supply-chain alarm).
remote=$(git ls-remote "$REPO" "refs/tags/$TAG*" | awk -v r="refs/tags/$TAG^{}" '$2 == r {print $1}')
[ "$remote" = "$COMMIT" ] || { echo "ERROR: $TAG resolves to '$remote', expected $COMMIT" >&2; exit 1; }

# 2. Fetch the tag (RAUC's version string comes from `git describe`) and check it is the commit.
rm -rf "$SRC" "$BUILD"; mkdir -p "$SRC"
git -C "$SRC" init -q
git -C "$SRC" fetch -q --depth 1 "$REPO" "refs/tags/$TAG:refs/tags/$TAG"
git -C "$SRC" -c advice.detachedHead=false checkout -q "$TAG"
head=$(git -C "$SRC" rev-parse HEAD)
[ "$head" = "$COMMIT" ] || { echo "ERROR: HEAD $head != $COMMIT" >&2; exit 1; }
log "rauc $TAG HEAD=$head"
log "git archive sha256 $(git -C "$SRC" archive --format=tar "$COMMIT" | sha256sum | cut -d' ' -f1)"

# 3. Configure, build, install (options = os/versions.lock.yaml rauc.meson_options).
meson setup --prefix=/usr --buildtype=release -Dtests=false -Dhtmldocs=false -Dmanpages=false \
  -Dsystemdunitdir=/usr/lib/systemd/system -Dsystemdcatalogdir=/usr/lib/systemd/catalog \
  -Ddbuspolicydir=/usr/share/dbus-1/system.d -Ddbussystemservicedir=/usr/share/dbus-1/system-services \
  -Ddbusinterfacesdir=/usr/share/dbus-1/interfaces "$BUILD" "$SRC" >/dev/null
ninja -C "$BUILD" >/dev/null
DESTDIR="$DEST" meson install -C "$BUILD" --no-rebuild >/dev/null

# 4. Prove what we built.
ver=$("$DEST/usr/bin/rauc" --version)
echo "$ver" | grep -qxE 'rauc v?1\.15\.2' || { echo "ERROR: unexpected version '$ver'" >&2; exit 1; }
log "built: $ver ($(uname -m)); binary sha256 $(sha256sum "$DEST/usr/bin/rauc" | cut -d' ' -f1)"
( cd "$DEST" && find . -type f | sort ) > "$DEST/../rauc-files.txt" 2>/dev/null || true
