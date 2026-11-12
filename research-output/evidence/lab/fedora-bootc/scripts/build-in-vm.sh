#!/bin/bash
# Runs INSIDE the disposable Lima build VM (Fedora 44 aarch64). Builds the four image
# variants, starts a local registry and writes a qcow2 disk from v1 with bootc-image-builder.
# Usage: build-in-vm.sh <workdir-with-Containerfile> <ssh-pubkey-file> <outdir>
set -euo pipefail
WD=$1; PUB=$2; OUT=$3
REG_LOCAL=localhost:5000
REG_GUEST=198.18.0.2:5000           # how the test VM sees the same registry
REGISTRY_IMG=docker.io/library/registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373
BIB_IMG=quay.io/centos-bootc/bootc-image-builder@sha256:dab86ee6b46dcade411b37f4e70b07d93b6a06da0dbfec6fe89247a220e0d9f8

sudo podman container exists lab-registry || \
  sudo podman run -d --name lab-registry -p 5000:5000 "$REGISTRY_IMG"

cd "$WD"
for v in v1 v2 v3-bad alt; do
  sudo podman build --pull=missing --build-arg VARIANT=$v -t onemind/lab:$v .
  sudo podman push --tls-verify=false onemind/lab:$v $REG_LOCAL/onemind/lab:$v
done
# Rebase target lives under a different repository name.
sudo podman push --tls-verify=false onemind/lab:alt $REG_LOCAL/onemind/lab-alt:latest
# The channel the device tracks starts at v1.
sudo podman push --tls-verify=false onemind/lab:v1 $REG_LOCAL/onemind/lab:stable
# Tag v1 locally with the name the device will use for upgrades, then build the disk.
sudo podman tag onemind/lab:v1 $REG_GUEST/onemind/lab:stable

mkdir -p "$OUT"
cat > "$OUT/config.toml" <<EOF
[[customizations.user]]
name = "lab"
key = "$(cat "$PUB")"
groups = ["wheel"]
EOF
sudo podman run --rm --privileged --pull=missing \
  --security-opt label=type:unconfined_t \
  -v "$OUT":/output -v "$OUT/config.toml":/config.toml:ro \
  -v /var/lib/containers/storage:/var/lib/containers/storage \
  "$BIB_IMG" --type qcow2 --rootfs xfs \
  $REG_GUEST/onemind/lab:stable
sudo chown -R "$(id -u):$(id -g)" "$OUT"
sha256sum "$OUT"/qcow2/disk.qcow2
for t in v1 v2 v3-bad alt; do echo "$t $(sudo skopeo inspect --tls-verify=false docker://$REG_LOCAL/onemind/lab:$t | jq -r .Digest)"; done
