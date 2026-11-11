#!/bin/bash
# Runs on the macOS HOST. Usage: host-source.sh <vm-name> sqlite|etcd
# Phase 1 on a source VM: baseline -> install k3s -> idle footprint -> load footprint -> verify -> backup -> export repo.
set -uo pipefail
VM=$1; MODE=$2
LAB=${LAB:?"set LAB to <lab-dir>/k3s-footprint-restore"}; HERE=$(cd "$(dirname "$0")" && pwd)
sh_() { limactl shell "$VM" sudo bash -c "$*"; }
limactl shell "$VM" mkdir -p /tmp/kfr
for f in "$LAB"/dl/k3s-arm64 "$LAB"/dl/install.sh "$LAB"/dl/restic_0.19.1_linux_arm64 "$HERE"/*.sh "$HERE"/workload.yaml; do
  limactl copy "$f" "$VM":/tmp/kfr/; done
sh_ "chmod +x /tmp/kfr/*.sh; DEBIAN_FRONTEND=noninteractive apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y sqlite3 >/dev/null; cat /etc/debian_version; uname -r"
sleep 60; sh_ /tmp/kfr/guest-measure.sh "baseline-no-k3s" 120
sh_ /tmp/kfr/guest-install.sh "$MODE" start 2>&1 | tail -2
sh_ 'until [ "$(k3s kubectl get pods -A --no-headers 2>/dev/null | grep -cE "Running|Completed")" -ge 7 ]; do sleep 5; done; k3s kubectl get pods -A --no-headers'
echo "settling 300s"; sleep 300
sh_ /tmp/kfr/guest-measure.sh "idle-k3s-$MODE" 120
sh_ /tmp/kfr/guest-workload.sh
sleep 60
sh_ "/tmp/kfr/guest-churn.sh 130 & /tmp/kfr/guest-measure.sh loaded-k3s-$MODE 120; wait"
sh_ "dmesg | grep -ci 'out of memory' | sed 's/^/oom_events=/'"
sh_ /tmp/kfr/guest-verify.sh | tee "$LAB/xfer/expected-$MODE.txt"
sh_ /tmp/kfr/guest-backup.sh "$MODE"
mkdir -p "$LAB/xfer/$MODE"
limactl copy "$VM":/tmp/kfr-restic.tar "$LAB/xfer/$MODE/" 
sh_ "cat /root/restic-pass" > "$LAB/xfer/$MODE/restic-pass"; chmod 600 "$LAB/xfer/$MODE/restic-pass"
sh_ "k3s crictl images -o json" | python3 -c 'import json,sys;[print("image",i["repoTags"][0] if i["repoTags"] else "-",i["repoDigests"][0].split("@")[1][:19] if i["repoDigests"] else "-",i["size"]) for i in json.load(sys.stdin)["images"]]'
echo "phase1 done $VM"
