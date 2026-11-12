#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike option B: build the QEMU image with podman and import it into k3s. Root, lab VM only.
set -euo pipefail; source "$(dirname "$0")/../common.sh"
exec > >(tee -a "$OUT/b-build.log") 2>&1
t0=$(ts)
podman build --pull=missing -t localhost/machlab-qemu:1 "$S/b"
podman run --rm localhost/machlab-qemu:1 sh -c 'cat /pkg-versions.txt; sha256sum /usr/share/AAVMF/AAVMF_CODE.fd'
podman save -o $W/machlab-qemu.tar localhost/machlab-qemu:1
k3s ctr -n k8s.io images import $W/machlab-qemu.tar
k3s ctr -n k8s.io images ls | awk '/machlab-qemu/{print $1, $3}'
podman image inspect docker.io/library/debian@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6 --format '{{.Digest}} {{.Architecture}}' || true
echo "build_s $(python3 -c "print(round($(ts)-$t0))")"
