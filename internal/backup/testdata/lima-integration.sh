#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Run the backup agent's integration test against the real, pinned restic and
# rest-server binaries inside a Debian 13 Lima VM (the shipping base, D-007).
#
#   internal/backup/testdata/lima-integration.sh            # create or reuse the VM, run, keep it
#   internal/backup/testdata/lima-integration.sh --delete   # delete the VM afterwards
#
# What it does:
#   1. starts (or reuses) a plain Debian 13 VM with no host mounts;
#   2. cross-compiles the test binary for the VM's architecture on the host,
#      so the VM needs no Go toolchain;
#   3. downloads restic and rest-server from their GitHub releases inside the
#      VM, checks each archive against the sha256 pinned in pins.go, and
#      installs sqlite3 from Debian;
#   4. runs the test with ONEMIND_VERIFY_PINS=1, so it also refuses any
#      binary whose own sha256 differs from the pin.
set -euo pipefail

VM="${ONEMIND_LIMA_VM:-onemind-backup-it}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PKGDIR="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$PKGDIR/../.." && pwd)"
DELETE=0
[[ "${1:-}" == "--delete" ]] && DELETE=1

if ! limactl list -q 2>/dev/null | grep -qx "$VM"; then
  limactl start --name="$VM" --tty=false --plain --cpus=2 --memory=2 --disk=10 template:debian-13
elif [[ "$(limactl list "$VM" --format '{{.Status}}')" != "Running" ]]; then
  limactl start --tty=false "$VM"
fi

case "$(limactl shell "$VM" uname -m)" in
  aarch64) ARCH=arm64 ;;
  x86_64)  ARCH=amd64 ;;
  *) echo "unsupported VM architecture" >&2; exit 1 ;;
esac

# pin <name> <field>: read a field of the pin for $ARCH from pins.go.
pin() {
  awk -v n="\"$1\"" -v a="\"$ARCH\"" -v f="$2" '
    $0 ~ "\\{" n ", \"[0-9.]+\", " a "," { hit = 1; line = 0; next }
    hit { line++; gsub(/[",\t ]/, ""); if (line == f) { print; exit } }
  ' "$PKGDIR/pins.go"
}
RESTIC_URL="$(pin restic 1)";       RESTIC_SHA="$(pin restic 2)"
REST_URL="$(pin rest-server 1)";    REST_SHA="$(pin rest-server 2)"
for v in "$RESTIC_URL" "$RESTIC_SHA" "$REST_URL" "$REST_SHA"; do
  [[ -n "$v" ]] || { echo "could not read pins from pins.go" >&2; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
(cd "$REPO" && CGO_ENABLED=0 GOOS=linux GOARCH="$ARCH" go test -c -tags integration -o "$WORK/backup.test" ./internal/backup/)
limactl copy "$WORK/backup.test" "$VM:/tmp/backup.test"

limactl shell "$VM" sudo env DEBIAN_FRONTEND=noninteractive apt-get -qq update
limactl shell "$VM" sudo env DEBIAN_FRONTEND=noninteractive apt-get -qq install -y sqlite3 curl bzip2 ca-certificates >/dev/null
limactl shell "$VM" bash -euo pipefail -c "
  d=\$(mktemp -d); cd \"\$d\"
  curl -fsSL -o restic.bz2 '$RESTIC_URL'
  echo '$RESTIC_SHA  restic.bz2' | sha256sum -c -
  bunzip2 restic.bz2 && chmod 0755 restic
  curl -fsSL -o rest-server.tgz '$REST_URL'
  echo '$REST_SHA  rest-server.tgz' | sha256sum -c -
  tar -xzf rest-server.tgz --strip-components=1 --wildcards '*/rest-server' && chmod 0755 rest-server
  ./restic version
  ./rest-server --version
  cd /tmp && ONEMIND_RESTIC=\"\$d/restic\" ONEMIND_REST_SERVER=\"\$d/rest-server\" \
    ONEMIND_SQLITE3=/usr/bin/sqlite3 ONEMIND_VERIFY_PINS=1 \
    ./backup.test -test.run Integration -test.v -test.count=1
"

if [[ "$DELETE" == 1 ]]; then
  limactl delete --force "$VM"
fi
