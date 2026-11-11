#!/bin/bash
# Runs on the macOS HOST. Usage: host-restore.sh <fresh-vm-name> sqlite|etcd [pass-token]
# Phase 2: install the same k3s (not started) on a FRESH VM, restore from the exported restic repo, verify.
set -uo pipefail
VM=$1; MODE=$2
LAB=${LAB:?"set LAB to <lab-dir>/k3s-footprint-restore"}; HERE=$(cd "$(dirname "$0")" && pwd)
sh_() { limactl shell "$VM" sudo bash -c "$*"; }
limactl shell "$VM" mkdir -p /tmp/kfr
for f in "$LAB"/dl/k3s-arm64 "$LAB"/dl/install.sh "$LAB"/dl/restic_0.19.1_linux_arm64 "$HERE"/*.sh "$LAB/xfer/$MODE/kfr-restic.tar" "$LAB/xfer/$MODE/restic-pass"; do
  limactl copy "$f" "$VM":/tmp/kfr/; done
sh_ "chmod +x /tmp/kfr/*.sh; hostname; ls /var/lib/rancher 2>&1 | head -1"
sh_ /tmp/kfr/guest-install.sh "$MODE" nostart 2>&1 | tail -2
sh_ /tmp/kfr/guest-restore.sh "$MODE" "${3:-}"
sh_ /tmp/kfr/guest-verify.sh | tee "$LAB/xfer/actual-$MODE.txt"
echo "--- diff expected vs actual (empty = identical)"; diff "$LAB/xfer/expected-$MODE.txt" "$LAB/xfer/actual-$MODE.txt" && echo "IDENTICAL"
sh_ "k3s kubectl get pods -A --no-headers | awk '{print \$4}' | sort | uniq -c; k3s kubectl -n kfr exec pg-0 -- sh -c 'grep -h \"database system\" /proc/1/fd/1 2>/dev/null' ; k3s kubectl -n kfr logs pg-0 | grep -iE 'recover|redo|ready to accept' | tail -4"
echo "phase2 done $VM"
