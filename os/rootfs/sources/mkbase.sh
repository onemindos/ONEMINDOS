#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Make the Debian base tree from the pinned snapshot with mmdebstrap (Step 2 PR 9), instead of starting from a
# Docker Hub image. The tree comes straight from snapshot.debian.org, checked against Debian's archive keyring, so the
# image no longer carries the Hub image's container leftovers (policy-rc.d, docker-* apt and dpkg files).
#   mkbase.sh <SNAPSHOT> <outdir>      run as root in a Debian container (os/rootfs/Containerfile, stage bootstrap)
# The Hub image only hosts this tool; none of its files end up in the tree.
# Chrootless mode is the one that works inside `docker build` (no mount, no user namespace). Package files are
# unpacked under fakeroot, written to a tar, and the tar is unpacked again as real root so every file keeps its
# real owner. SOURCE_DATE_EPOCH, when set, makes the tar reproducible (mmdebstrap(1) "ENVIRONMENT").
set -eu
SNAP=$1; OUTDIR=$2
HERE=$(cd "$(dirname "$0")" && pwd)
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
# The host's own apt reads the same snapshot, so mmdebstrap and its dependencies are pinned too.
sh "$HERE/configure-apt.sh" debian "$SNAP" no
apt-get update
apt-get install -y mmdebstrap fakeroot
KR=/usr/share/keyrings/debian-archive-keyring.gpg
TAR=$(mktemp -d)/base.tar
# The same three suites configure-apt.sh gives the finished image, so the base is already at the snapshot's patch level.
fakeroot mmdebstrap --mode=chrootless --variant=minbase --skip=output/dev --format=tar \
  --aptopt='Acquire::Check-Valid-Until "false"' \
  trixie "$TAR" \
  "deb [signed-by=$KR] http://snapshot.debian.org/archive/debian/$SNAP trixie main" \
  "deb [signed-by=$KR] http://snapshot.debian.org/archive/debian/$SNAP trixie-updates main" \
  "deb [signed-by=$KR] http://snapshot.debian.org/archive/debian-security/$SNAP trixie-security main"
mkdir -p "$OUTDIR"
tar --numeric-owner -xpf "$TAR" -C "$OUTDIR"
rm -rf "$(dirname "$TAR")"
echo "mkbase: Debian trixie base from snapshot $SNAP: $(grep -c '^Package:' "$OUTDIR/var/lib/dpkg/status") packages"
