#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# What a release-keyed installer image must prove before a stick is built from it (#234, D-010;
# os/boards/installer-x86_64/UPDATES.md). Run on the CI runner after `make release-image`, on a publishing run and in
# the dry-run rehearsal alike (.github/workflows/security-nightly.yml, job installer):
#   check-release-image.sh <image-dir> <release-dir> <board> <version>
# <image-dir>   the make release-image output. release-ca.cert.pem there is the keyring read back from the assembled
#               image's tree by os/assemble/release-image.sh (/etc/rauc/keyring.pem), not a copy of the input.
# <release-dir> the build job's release-<board> artifact: the signed bundle, its keyring.pem and packages.txt.
# Checks, each one fatal:
#   1. the image's keyring is byte for byte the keyring the bundle was verified against (build-release.sh);
#   2. no dev CA sits next to the image;
#   3. RAUC verifies this run's bundle with the image's keyring, as the installed box will (`rauc info --keyring` in
#      the tools container TOOLS, default onemind-tools:ci; both folders mounted read-only);
#   4. the image's package list is the one the build job scanned (Trivy, ClamAV) and signed: the image is rebuilt from
#      a second rootfs build, so a different package set fails here instead of shipping.
# Reads only public files (certificates, bundle, package lists); no key is read or used.
set -eu
[ $# -eq 4 ] || { echo "usage: $0 <image-dir> <release-dir> <board> <version>" >&2; exit 2; }
IMG=$1; REL=$2; BOARD=$3; VERSION=$4
B=onemind-$BOARD-$VERSION
fail() { echo "FAILED: $*" >&2; exit 1; }
[ -s "$IMG/release-ca.cert.pem" ] || fail "$IMG has no release-ca.cert.pem (not a make release-image output)"
[ -s "$REL/$B.keyring.pem" ] || fail "$REL has no $B.keyring.pem"
cmp -s "$IMG/release-ca.cert.pem" "$REL/$B.keyring.pem" ||
  fail "the image's keyring is not the keyring $B.raucb was verified against"
[ ! -e "$IMG/dev-ca.cert.pem" ] || fail "a dev CA sits next to the release-keyed image"
[ -s "$REL/$B.raucb" ] || fail "$REL has no $B.raucb"
docker run --rm -v "$(cd "$IMG" && pwd)":/img:ro -v "$(cd "$REL" && pwd)":/rel:ro "${TOOLS:-onemind-tools:ci}" \
  rauc info --keyring=/img/release-ca.cert.pem "/rel/$B.raucb" >/dev/null ||
  fail "RAUC refuses $B.raucb with the image's keyring: a box installed from this stick would refuse this release"
[ -s "$IMG/$B.packages.txt" ] || fail "$IMG has no $B.packages.txt"
[ -s "$REL/$B.packages.txt" ] || fail "$REL has no $B.packages.txt"
cmp -s "$IMG/$B.packages.txt" "$REL/$B.packages.txt" ||
  fail "the image's packages differ from the scanned and signed build's ($B.packages.txt)"
echo "ok: $B image trusts the bundle's CA, RAUC accepts the bundle with it, same packages as the signed build"
