#!/bin/sh
# Runs INSIDE the disposable VM as root. Usage: guest-install.sh sqlite|etcd start|nostart
# Expects verified files in /tmp/kfr: k3s-arm64, install.sh, restic_0.19.1_linux_arm64
set -eu
MODE=$1; START=$2; STAGE=/tmp/kfr
install -m 0755 $STAGE/k3s-arm64 /usr/local/bin/k3s
install -m 0755 $STAGE/restic_0.19.1_linux_arm64 /usr/local/bin/restic
mkdir -p /etc/rancher/k3s
# Same node name on source and restore box: local-path volumes are pinned to a node name.
printf 'node-name: omos-box\nwrite-kubeconfig-mode: "0600"\n' > /etc/rancher/k3s/config.yaml
if [ "$MODE" = etcd ]; then echo 'cluster-init: true' >> /etc/rancher/k3s/config.yaml; fi
SKIP=false; if [ "$START" = nostart ]; then SKIP=true; fi
INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_SKIP_START=$SKIP sh $STAGE/install.sh
k3s --version
