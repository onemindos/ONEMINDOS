#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike step 1: T1 (environment), tools, k3s from the pinned binary.
# Runs as root INSIDE the disposable Lima VM only. Never run it on a host.
set -euo pipefail
LAB=${LAB:?"set LAB to <lab-dir>/machines-spike"}; OUT=$LAB/run; mkdir -p "$OUT" /opt/machlab/dl
exec > >(tee -a "$OUT/setup.log") 2>&1
echo "== T1 environment $(date -u +%FT%TZ)"
uname -a; nproc; grep -E 'MemTotal|MemAvailable' /proc/meminfo; cat /etc/debian_version; getconf PAGESIZE
if [ -c /dev/kvm ] && python3 -c "import os;os.close(os.open('/dev/kvm',os.O_RDWR))"; then
  echo "T1 kvm: /dev/kvm present and opens"; ls -l /dev/kvm; echo kvm > /opt/machlab/accel
else
  echo "T1 LIMIT: no usable /dev/kvm, software emulation for every M test"; echo tcg > /opt/machlab/accel
fi
swapoff -a || true
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q podman
apt-get install -y -q --no-install-recommends chromium fonts-dejavu-core qemu-utils btrfs-progs \
  xfsprogs e2fsprogs jq socat cloud-image-utils curl ca-certificates openssh-client gpg gpgv python3
dpkg-query -W podman chromium qemu-utils btrfs-progs jq socat cloud-image-utils openssh-client python3 | tee "$OUT/debian-tools.txt"

echo "== k3s (pin from os/versions.lock.yaml)"
K3S_SHA=a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b
U=https://github.com/k3s-io/k3s/releases/download/v1.37.2%2Bk3s1
cd /opt/machlab/dl
[ -f k3s-arm64 ] || curl -fsSL -o k3s-arm64 "$U/k3s-arm64"
curl -fsSL -o k3s-sha256sum-arm64.txt "$U/sha256sum-arm64.txt"
got=$(sha256sum k3s-arm64 | cut -d' ' -f1)
[ "$got" = "$K3S_SHA" ] || { echo "T0 FAIL k3s got=$got"; exit 1; }
grep -q "^$K3S_SHA  k3s-arm64$" k3s-sha256sum-arm64.txt || { echo "T0 FAIL k3s pin not in upstream file"; exit 1; }
echo "sha256 OK pin+upstream k3s-arm64 $got"
install -m755 k3s-arm64 /usr/local/bin/k3s
for l in kubectl crictl ctr; do ln -sf k3s /usr/local/bin/$l; done
cat > /etc/systemd/system/k3s.service <<'UNIT'
[Unit]
Description=k3s server (LAB-machines-spike)
Wants=network-online.target
After=network-online.target
[Service]
Type=notify
ExecStart=/usr/local/bin/k3s server --disable traefik,servicelb,metrics-server --write-kubeconfig-mode 0644
Delegate=yes
KillMode=process
Restart=always
LimitNOFILE=1048576
TasksMax=infinity
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload; systemctl enable --now k3s
for _ in $(seq 1 120); do kubectl get nodes 2>/dev/null | grep -q ' Ready' && break; sleep 5; done
kubectl get nodes -o wide | sed -E 's/([0-9]+\.){3}[0-9]+/<ip>/g'
k3s --version
echo "== setup done $(date -u +%FT%TZ)"
