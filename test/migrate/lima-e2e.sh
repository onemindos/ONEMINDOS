#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Migration kit end-to-end test in a throwaway Lima VM (Debian 13). Installs nothing on this
# machine: it builds the onemind CLI with the local Go toolchain, copies the kit into the VM,
# runs test/migrate/in-vm.sh there as root, and deletes the VM.
#
#   test/migrate/lima-e2e.sh                 create omos-migrate-e2e, run, delete
#   VM=name KEEP_VM=1 test/migrate/lima-e2e.sh   reuse or keep a VM (for debugging)
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
VM=${VM:-omos-migrate-e2e}
KEEP_VM=${KEEP_VM:-0}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/omos-migrate-e2e.XXXXXX")
UV_VERSION=0.13.7   # same uv as the developer machines; checksums from the release's .sha256 files

created=0
cleanup() {
  rm -rf "$WORK"
  if [ "$created" = 1 ] && [ "$KEEP_VM" != 1 ]; then
    limactl delete --force "$VM" >/dev/null 2>&1 || true
    echo "deleted VM $VM"
  fi
}
trap cleanup EXIT

if ! limactl list -q 2>/dev/null | grep -qx "$VM"; then
  limactl create --name "$VM" --cpus 4 --memory 6 --disk 20 --mount-none --tty=false template:debian-13
  created=1
fi
[ "$KEEP_VM" = 1 ] || created=1   # a reused VM is deleted too unless KEEP_VM=1
limactl start "$VM" >/dev/null 2>&1 || true

arch=$(limactl shell "$VM" uname -m)
case $arch in
  aarch64) goarch=arm64; k3s_file=k3s-arm64; uv_triple=aarch64-unknown-linux-gnu
           uv_sha=71279f8d3c67241e807b9d8db872d1bf541579fb9f08b7d1eb1682196d1e57dc ;;
  x86_64)  goarch=amd64; k3s_file=k3s; uv_triple=x86_64-unknown-linux-gnu
           uv_sha=c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83 ;;
  *) echo "unsupported VM arch $arch" >&2; exit 2 ;;
esac

# k3s exactly as pinned for the OS image (os/versions.lock.yaml).
lock="$REPO/os/versions.lock.yaml"
k3s_url=$(awk '/^k3s:/{f=1} f&&/^  url:/{print $2; exit}' "$lock")
k3s_sha=$(awk -v key="    $k3s_file:" '/^k3s:/{f=1} f&&index($0,key)==1{print $2; exit}' "$lock")
[ -n "$k3s_url" ] && [ -n "$k3s_sha" ] || { echo "k3s pin not found in $lock" >&2; exit 2; }

echo "building onemind for linux/$goarch"
(cd "$REPO" && CGO_ENABLED=0 GOOS=linux GOARCH=$goarch go build -o "$WORK/kit/onemind" ./cmd/onemind)
mkdir -p "$WORK/kit/test"
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -C "$REPO" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=data -cf - core test/migrate \
  | tar -C "$WORK/kit" -xf -
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -C "$WORK" -czf "$WORK/kit.tgz" kit

limactl shell "$VM" sudo rm -rf /tmp/omos-migrate-kit /tmp/kit.tgz
limactl copy "$WORK/kit.tgz" "$VM:/tmp/kit.tgz"
limactl shell "$VM" bash -c 'mkdir -p /tmp/omos-migrate-kit && tar --warning=no-unknown-keyword -xzf /tmp/kit.tgz -C /tmp/omos-migrate-kit --strip-components=1'

limactl shell "$VM" sudo env KIT=/tmp/omos-migrate-kit \
  K3S_URL="${k3s_url}${k3s_file}" K3S_SHA256="$k3s_sha" \
  UV_URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$uv_triple.tar.gz" UV_SHA256="$uv_sha" \
  bash /tmp/omos-migrate-kit/test/migrate/in-vm.sh
