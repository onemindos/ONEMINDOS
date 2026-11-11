#!/bin/bash
# LAB-rauc-1152 T12 control (added after pre-registration, see README deviations):
# Debian's 1.13-3+deb13u1 turned out to carry the CVE-2026-34155 fix, so it is
# not a vulnerable control. This builds the last unfixed upstream release,
# v1.15.1 (commit fac72b8347eed46f300d3a8a06e847ce1aa9d677), natively in the
# VM and checks that it CREATES the >2 GiB plain bundle the fixed builds refuse.
# Creation only; the bundle is deleted at once and never installed.
# Run as root INSIDE the disposable Lima VM.
set -euo pipefail
B=${B:-/var/lab/raucbuild}; C=$B/v1151
TAG=v1.15.1; COMMIT=fac72b8347eed46f300d3a8a06e847ce1aa9d677
rm -rf "$C"; git clone -q -c advice.detachedHead=false --depth 1 --branch $TAG https://github.com/rauc/rauc.git "$C/src"
[ "$(git -C "$C/src" rev-parse HEAD)" = $COMMIT ] || { echo "ERROR: wrong commit"; exit 1; }
meson setup --buildtype=release -Dtests=false "$C/build" "$C/src" >/dev/null && ninja -C "$C/build" >/dev/null
echo "control: $("$C/build/rauc" --version) HEAD=$COMMIT"
T=$B/t12; mkdir -p "$T/content"
head -c 2150M /dev/urandom > "$T/content/rootfs.ext4"
printf '[update]\ncompatible=t12\nversion=1\n\n[bundle]\nformat=plain\n\n[image.rootfs]\nfilename=rootfs.ext4\n' > "$T/content/manifest.raucm"
rm -f "$T/out.raucb"
if "$C/build/rauc" bundle --cert="$T/keys/c.pem" --key="$T/keys/k.pem" "$T/content" "$T/out.raucb" > "$T/v1151-plain.log" 2>&1; then
  echo "T12 upstream-1.15.1-plain (unfixed control): CREATED $(stat -c %s "$T/out.raucb") bytes"
  # Same bundle, verified by the fixed 1.15.2 build: expect a refusal.
  if "$B/arm64/rauc" info --keyring="$T/keys/c.pem" "$T/out.raucb" > "$T/v1152-info.log" 2>&1; then
    echo "T12 1.15.2 'rauc info' on that bundle: ACCEPTED"
  else echo "T12 1.15.2 'rauc info' on that bundle: REFUSED: $(grep -E -o 'exceeds[^"]*' "$T/v1152-info.log" | head -1)"; fi
  if /usr/bin/rauc info --keyring="$T/keys/c.pem" "$T/out.raucb" > "$T/deb-info.log" 2>&1; then
    echo "T12 Debian 1.13-3+deb13u1 'rauc info' on that bundle: ACCEPTED"
  else echo "T12 Debian 1.13-3+deb13u1 'rauc info' on that bundle: REFUSED: $(grep -E -o 'exceeds[^"]*' "$T/deb-info.log" | head -1)"; fi
else echo "T12 upstream-1.15.1-plain: REFUSED/FAILED: $(tail -1 "$T/v1151-plain.log")"; fi
rm -rf "$T/content" "$T/out.raucb"
