#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Build the OneMind layer for Jetson (arm64): the same agent, CLI, NATS, gateway venv, dashboard,
# catalog, first boot and k3s as the Debian image, taken from the shared Containerfile's stages
# (os/rootfs/Containerfile onemind-*), plus the Jetson gate files in os/boards/jetson-orin/rootfs.
# Runs wherever Docker runs: the Lima VM on the Mac (arm64 native) or CI. Never on the Mac host.
#
#   os/boards/jetson-orin/make-layer.sh <out-dir> [version]
#     -> <out-dir>/onemind-layer-jetson-orin-<version>.tar.gz (+ .sha256)
#
# The layer holds only OneMind (Apache-2.0) files and pinned upstream binaries (k3s, NATS, Python,
# the gateway's wheels): no NVIDIA or Ubuntu file, so it can be published like any image layer.
set -euo pipefail
OUT=${1:?usage: make-layer.sh <out-dir> [version]}; VERSION=${2:-0.1.0-dev}
case "$VERSION" in *[!A-Za-z0-9.+_-]*|"") echo "make-layer: bad version '$VERSION'" >&2; exit 1 ;; esac
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
L="$OUT/jetson-layer"; rm -rf "$L"; mkdir -p "$L"
ARGS=(); while IFS= read -r a; do ARGS+=(--build-arg "$a"); done < <(sed -n 's/^\([A-Z]*=.*\)/\1/p' os/rootfs/debian.args)

img() { echo "onemind-jetson-$1:$VERSION"; }
build() {
  docker buildx build -f os/rootfs/Containerfile --platform linux/arm64 --target "$1" "${ARGS[@]}" \
    --build-arg "ONEMIND_VERSION=$VERSION" --load -t "$(img "$1")" .
}
copy_out() { # <stage> <path in image> <dest dir>
  local id; id=$(docker create --platform linux/arm64 "$(img "$1")" /bin/true)
  mkdir -p "$3"; docker cp "$id:$2" "$3"; docker rm "$id" >/dev/null
}
for s in onemind-buildbase onemind-go onemind-fetch onemind-gateway onemind-dashboard; do build "$s"; done

copy_out onemind-go /out/onemindd "$L/usr/bin"
copy_out onemind-go /out/onemind "$L/usr/bin"
copy_out onemind-fetch /opt/nats/nats-server "$L/usr/bin"
copy_out onemind-gateway /usr/lib/onemind/gateway "$L/usr/lib/onemind"
mkdir -p "$L/usr/lib/onemind/dashboard"
id=$(docker create --platform linux/arm64 "$(img onemind-dashboard)" /bin/true)
docker cp "$id:/src/dashboard/dist/." "$L/usr/lib/onemind/dashboard/"; docker rm "$id" >/dev/null
# k3s + air-gap images, sha256-checked by the shared fetch script (os/versions.lock.yaml `k3s:`).
# No bind mount: `docker cp` writes as the calling user under both rootful (CI) and rootless (Lima) Docker.
id=$(docker create "$(img onemind-buildbase)" sh /fetch-k3s.sh arm64 /stage)
docker cp os/rootfs/fetch-k3s.sh "$id:/fetch-k3s.sh"
docker start -a "$id"
docker cp "$id:/stage/." "$L/"; docker rm "$id" >/dev/null

# Repo files. From the base layer only what is not RAUC/GRUB/Debian-specific: L4T keeps its own
# fstab, hostname, network stack and watchdog setup; the RAUC gate and handler are replaced by
# the Jetson gate; onemind-update.service stays inert (no /etc/onemind/update.conf on Jetson).
install -D -m 755 os/gate/onemind-k3s-check            "$L/usr/lib/onemind/onemind-k3s-check"
install -D -m 755 os/gate/onemind-local-api-respond    "$L/usr/lib/onemind/onemind-local-api-respond"
install -D -m 644 os/gate/onemind-local-api.service    "$L/usr/lib/systemd/system/onemind-local-api.service"
B=os/rootfs/layers/base
for f in etc/default/k3s etc/default/onemind-health-gate usr/lib/systemd/system/k3s.service \
         usr/lib/systemd/system/onemind-data-layout.service usr/lib/onemind/manifests/onemind-core.yaml \
         usr/lib/onemind/tuf/README.md; do
  install -D -m 644 "$B/$f" "$L/$f"
done
mkdir -p "$L/usr/lib/onemind/sdk" "$L/usr/lib/onemind/apps"
cp -R sdk/schema "$L/usr/lib/onemind/sdk/"
cp -R apps/. "$L/usr/lib/onemind/apps/"; rm -f "$L/usr/lib/onemind/apps/README.md"
cp -R os/rootfs/layers/onemind/. "$L/"
cp -R os/boards/jetson-orin/rootfs/. "$L/"
install -D -m 644 os/assemble/onemind.conf.in "$L/usr/lib/onemind/jetson/onemind.conf.template"
ln -s ../lib/onemind/jetson/onemind-jetson "$L/usr/sbin/onemind-jetson"
find "$L" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$L" -name .keep -delete
printf 'ONEMIND_VERSION=%s\n' "$VERSION" > "$L/etc/onemind/release"
printf 'board=jetson-orin arch=arm64 version=%s base=nvidia-l4t\n' "$VERSION" > "$L/usr/lib/onemind/build-info.txt"
(cd "$L" && find . -type f ! -path ./usr/lib/onemind/jetson/layer-manifest.txt -print0 | sort -z \
  | xargs -0 sha256sum) > "$L/usr/lib/onemind/jetson/layer-manifest.txt"

# System-file modes, whatever the build host's umask was: dirs 0755, nothing group/other-writable.
find "$L" -type d -exec chmod 0755 {} +
chmod -R go-w "$L"
T="$OUT/onemind-layer-jetson-orin-$VERSION.tar.gz"
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime=@0 -C "$L" -czf "$T" .
(cd "$OUT" && sha256sum "$(basename "$T")" > "$(basename "$T").sha256")
rm -rf "$L"
cat "$T.sha256"
