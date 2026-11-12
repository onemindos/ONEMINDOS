#!/bin/bash
# Runs INSIDE a FRESH VM as root, after guest-install.sh <mode> nostart.
# Usage: guest-restore.sh sqlite|etcd [pass-token]   (expects /tmp/kfr/kfr-restic.tar and /tmp/kfr/restic-pass)
set -euo pipefail
MODE=$1; PASS=${2:-}; install -m 600 /tmp/kfr/restic-pass /root/restic-pass
mkdir -p /srv && tar -C /srv -xf /tmp/kfr/kfr-restic.tar
export RESTIC_REPOSITORY=/srv/restic RESTIC_PASSWORD_FILE=/root/restic-pass
restic restore latest --target / 2>&1 | tail -1
mkdir -p /var/lib/rancher/k3s/server/db
install -m 600 /var/backups/kfr/token /var/lib/rancher/k3s/server/token
T0=$(date +%s)
if [ "$MODE" = sqlite ]; then
  cp /var/backups/kfr/state.db /var/lib/rancher/k3s/server/db/state.db
else
  SNAP=$(ls /var/backups/kfr/kfr-* | head -1)
  TOKFLAG=""
  if [ "$PASS" = pass-token ]; then
    # Attempt 2: pass the ORIGINAL token explicitly (docs: "you must pass the server token that was
    # originally used when taking the snapshot"); keep it for the service too.
    install -m 600 /var/backups/kfr/token /etc/rancher/k3s/restore-token
    echo 'token-file: /etc/rancher/k3s/restore-token' >> /etc/rancher/k3s/config.yaml
    TOKFLAG="--token-file=/etc/rancher/k3s/restore-token"
  fi
  k3s server --cluster-reset --cluster-reset-restore-path="$SNAP" $TOKFLAG > /root/cluster-reset.log 2>&1 || true
  cmp -s /var/lib/rancher/k3s/server/token /var/backups/kfr/token && echo "token_file_after_reset=original" || echo "token_file_after_reset=REPLACED"
  tail -3 /root/cluster-reset.log
fi
systemctl start k3s
until k3s kubectl get node omos-box --no-headers 2>/dev/null | grep -qw Ready; do sleep 2; done
echo "node_ready_seconds=$(( $(date +%s) - T0 ))"
T0ISO=$(date -u -d @$T0 +%FT%TZ)
# Datastore status is stale after restore, so count only pods whose container started AFTER the restore.
for i in $(seq 1 150); do
  r=$(k3s kubectl -n kfr get pods -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready} {.status.containerStatuses[0].state.running.startedAt}{"\n"}{end}' 2>/dev/null \
      | awk -v t="$T0ISO" '$1=="true" && $2>=t {n++} END{print n+0}')
  [ "$r" -ge 32 ] && break; sleep 2
done
echo "workloads_ready_seconds=$(( $(date +%s) - T0 )) fresh_ready_pods=$r/32"
