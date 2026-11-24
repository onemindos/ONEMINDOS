#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Mirror the platform's map-pack volume in the isolated k3d app smoke cluster.
set -euo pipefail
[[ "$1" == offline-maps || "$1" == apps/offline-maps ]] || exit 0
docker exec "k3d-$2-server-0" mkdir -p -m 0755 /data/onemind/maps/packs
kubectl apply -f os/rootfs/layers/onemind/usr/lib/onemind/manifests/offline-maps-packs-pv.yaml
