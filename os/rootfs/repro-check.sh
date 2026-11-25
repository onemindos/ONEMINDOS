#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Reproducible-build check (Step 2 PR 8): build the rootfs twice from nothing (--no-cache, a pause between so the
# clock differs), assemble each into rootfs.ext4 the way the image does, and compare hashes.
#   make repro-check BOARD=x86_64-efi         (run from the repo root; needs Docker, no KVM)
# Exit 0 only when the rootfs tar AND rootfs.ext4 are byte-identical across both builds. On a difference it prints
# the first differing tar entries so the cause is visible in the CI log. Throwaway material only: the keyring made
# here is a dummy certificate with its private key thrown away at creation.
set -eu
: "${BOARD:=x86_64-efi}" "${LEG:=debian}" "${OUT:=out}" "${TOOLS:=onemind-tools:ci}"
SRC=$(pwd)
EPOCH=$(python3 -I os/rootfs/source-date-epoch.py "$(sed -n 's/^SNAPSHOT=//p' "os/rootfs/$LEG.args")")
[ -n "$EPOCH" ] || { echo "repro-check: leg $LEG has no pinned snapshot, so no SOURCE_DATE_EPOCH" >&2; exit 2; }
ARGS=$(sed -n 's/^\([A-Z_]*=.*\)/--build-arg \1/p' "os/rootfs/$LEG.args")
R="$OUT/repro-$BOARD"; rm -rf "$R"; mkdir -p "$R"
# One dummy keyring for both runs (the image embeds it; a fresh one each time would be the difference we test for).
docker run --rm -v "$SRC/$R":/r "$TOOLS" openssl req -x509 -newkey rsa:2048 -nodes -days 1 -keyout /dev/null \
  -out /r/ca.pem -subj "/O=OneMind DEV (throwaway)/CN=repro" 2>/dev/null
for n in 1 2; do
  echo "== build $n of 2 (no cache, SOURCE_DATE_EPOCH=$EPOCH)"
  # shellcheck disable=SC2086
  docker buildx build --no-cache -f os/rootfs/Containerfile --target rootfs --build-arg BOARD="$BOARD" \
    --build-arg SOURCE_DATE_EPOCH="$EPOCH" $ARGS \
    --output "type=tar,dest=$R/rootfs-$n.tar,rewrite-timestamp=true" .
  echo "== assemble rootfs.ext4 from build $n"
  docker run --rm -v "$SRC":/src:ro -v "$SRC/$R":/r -e SOURCE_DATE_EPOCH="$EPOCH" -e BOARD="$BOARD" -e N="$n" "$TOOLS" sh -eu -c '
    W=$(mktemp -d); trap "rm -rf $W" EXIT
    python3 -I /src/os/assemble/assemble.py tree --board "$BOARD" --rootfs "/r/rootfs-$N.tar" --work "$W" --version repro --keyring /r/ca.pem
    python3 -I /src/os/assemble/assemble.py ext4 --work "$W" --out "/r/rootfs-$N.ext4"'
  [ "$n" = 2 ] || sleep 5
done
t1=$(sha256sum "$R/rootfs-1.tar" | cut -d' ' -f1); t2=$(sha256sum "$R/rootfs-2.tar" | cut -d' ' -f1)
e1=$(sha256sum "$R/rootfs-1.ext4" | cut -d' ' -f1); e2=$(sha256sum "$R/rootfs-2.ext4" | cut -d' ' -f1)
echo "rootfs tar   1: $t1"; echo "rootfs tar   2: $t2"
echo "rootfs.ext4  1: $e1"; echo "rootfs.ext4  2: $e2"
rc=0
if [ "$t1" != "$t2" ]; then
  rc=1; echo "FAIL: the rootfs tar differs between two builds; first differences:" >&2
  tar -tvf "$R/rootfs-1.tar" > "$R/list-1.txt"; tar -tvf "$R/rootfs-2.tar" > "$R/list-2.txt"
  diff "$R/list-1.txt" "$R/list-2.txt" | head -40 >&2 || true
fi
[ "$e1" = "$e2" ] || { rc=1; echo "FAIL: rootfs.ext4 differs between two builds" >&2; }
[ "$rc" != 0 ] || echo "PASS: two builds, identical rootfs tar and rootfs.ext4 ($e1)"
exit "$rc"
