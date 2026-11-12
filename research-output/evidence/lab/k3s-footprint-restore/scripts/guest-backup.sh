#!/bin/bash
# Runs INSIDE the VM as root. Usage: guest-backup.sh sqlite|etcd
# Backs up the datastore (SQLite online .backup copy, or k3s etcd snapshot), the server token and
# the local-path volume directory into a fresh restic repository at /srv/restic.
set -euo pipefail
MODE=$1; export RESTIC_REPOSITORY=/srv/restic RESTIC_PASSWORD_FILE=/root/restic-pass
[ -f /root/restic-pass ] || head -c 32 /dev/urandom | base64 > /root/restic-pass
chmod 600 /root/restic-pass
echo "--- F4 probe: k3s etcd-snapshot save on datastore=$MODE"; k3s etcd-snapshot save --name probe 2>&1 | tail -3 || true
# Ask PostgreSQL to flush to disk; the volume copy is then crash-consistent (PG replays WAL on start).
k3s kubectl -n kfr exec pg-0 -- psql -U postgres -qc CHECKPOINT
rm -rf /var/backups/kfr; mkdir -p /var/backups/kfr
if [ "$MODE" = sqlite ]; then
  sqlite3 /var/lib/rancher/k3s/server/db/state.db ".backup /var/backups/kfr/state.db"
  sqlite3 /var/backups/kfr/state.db "PRAGMA integrity_check;"
else
  k3s etcd-snapshot save --name kfr 2>&1 | tail -2
  cp -a /var/lib/rancher/k3s/server/db/snapshots/kfr-* /var/backups/kfr/
fi
cp -a /var/lib/rancher/k3s/server/token /var/backups/kfr/token
restic init 2>&1 | head -1
T0=$(date +%s)
restic backup --host omos-box /var/backups/kfr /var/lib/rancher/k3s/storage 2>&1 | tail -4
echo "backup_seconds=$(( $(date +%s) - T0 ))"
restic check 2>&1 | tail -1
echo "repo_size_mib=$(du -sm /srv/restic | cut -f1)"
S=$(k3s kubectl -n kfr get secret kfr-secret -o jsonpath='{.data.marker}' | base64 -d)
if grep -rqa -- "$S" /srv/restic; then echo "R3_plaintext_in_repo=FOUND"; else echo "R3_plaintext_in_repo=none"; fi
tar -C /srv -cf /tmp/kfr-restic.tar restic
