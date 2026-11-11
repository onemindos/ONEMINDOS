#!/bin/bash
# Runs on the macOS HOST (Apple silicon, Lima >= 2.3). Full spike: fetch, 4 disposable VMs, measure, back up,
# restore, verify, delete. Outputs land in $LAB/xfer. Takes about 20 minutes.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); LAB=${LAB:-$HOME/<lab-dir>/k3s-footprint-restore}; export LAB
"$HERE/host-fetch.sh"
mk() { limactl create -y --name="$1" --cpus=2 --memory=4 --disk=20 --mount-none --containerd=none template:debian-13 && limactl start "$1"; }
for v in kfr-sqlite kfr-etcd kfr-sqlite-restore kfr-etcd-restore; do mk $v > "$LAB/xfer/create-$v.log" 2>&1 & done; wait
"$HERE/host-source.sh" kfr-sqlite sqlite > "$LAB/xfer/run-sqlite.log" 2>&1 &
"$HERE/host-source.sh" kfr-etcd etcd > "$LAB/xfer/run-etcd.log" 2>&1 &
wait
"$HERE/host-restore.sh" kfr-sqlite-restore sqlite > "$LAB/xfer/restore-sqlite.log" 2>&1
# pass-token is REQUIRED for etcd on a new host (attempt 1 without it failed; see README).
"$HERE/host-restore.sh" kfr-etcd-restore etcd pass-token > "$LAB/xfer/restore-etcd.log" 2>&1
grep -H -E "IDENTICAL|workloads_ready_seconds|fatal" "$LAB"/xfer/restore-*.log
for v in kfr-sqlite kfr-etcd kfr-sqlite-restore kfr-etcd-restore; do limactl delete -f $v; done
