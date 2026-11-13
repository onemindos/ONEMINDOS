# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
#
# Backups switched on for the developer install (BACKUP-WIRE-1, DB-SHARED-1). Sourced by
# deploy/install.sh; backup_setup runs on the hub once the gateway answers. Re-running is safe.
#
# What it sets up, in plain words:
#   - restic, pinned by version and sha256 (the agent refuses any other binary);
#   - the "onemind-local" storage class: app volumes that survive deleting their claim (Retain);
#   - the shared PostgreSQL's manifests, which the gateway applies when the first app needs one;
#   - the gateway's Ed25519 job key: the backup agent obeys only jobs signed with it;
#   - the backup agent inside onemindd (backup.Service(), one service, loopback :7480), with a
#     systemd drop-in giving onemindd the four capabilities a restore needs;
#   - ONEMIND_BACKUPS_ENABLED=1 for the gateway, which then runs the hourly backups with each
#     app's hooks. No destination is configured here: the owner adds one (a USB disk, another
#     OneMind box, an S3 bucket) and approves it, then prints the emergency kit.

backup_setup() {
  local k="$BIN/k3s kubectl" conf="$ETC/backup-agent.json" agent_state=/var/lib/onemind-backup
  local url sum binsum box k3sv
  log "backups: restic $RESTIC_VERSION, onemind-local storage class, backup agent"

  # sqlite3 makes the online copies of the gateway and k3s databases; bzip2 unpacks restic.
  if ! dpkg -s sqlite3 bzip2 >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends sqlite3 bzip2 >/dev/null
  fi
  url=$(pick RESTIC_URL); sum=$(pick RESTIC_SHA256); binsum=$(pick RESTIC_BIN_SHA256)
  if ! echo "$binsum  /usr/lib/onemind/restic" | sha256sum -c --status 2>/dev/null; then
    fetch "$url" "$sum" "$CACHE/restic-$RESTIC_VERSION.bz2"
    install -d -m0755 /usr/lib/onemind
    bunzip2 -c "$CACHE/restic-$RESTIC_VERSION.bz2" > /usr/lib/onemind/restic.new
    echo "$binsum  /usr/lib/onemind/restic.new" | sha256sum -c --status || die "restic binary sha256 mismatch"
    chmod 0755 /usr/lib/onemind/restic.new && mv /usr/lib/onemind/restic.new /usr/lib/onemind/restic
  fi

  # The agent may write only where its unit says (ReadWritePaths). systemd silently drops a path
  # that does not exist when the service starts, which would leave app volumes read-only for a
  # restore: create them now and at every boot (/run is emptied on reboot).
  printf '%s\n' '# OneMind backup agent (deploy/backup.sh): folders onemindd (backup drop-in) may write.' \
    'd /run/onemind/backup 0755 root root -' 'd /var/lib/rancher/k3s/storage 0700 root root -' \
    'd /var/lib/onemind-backup 0700 root root -' \
    > /etc/tmpfiles.d/onemind-backup.conf
  systemd-tmpfiles --create /etc/tmpfiles.d/onemind-backup.conf

  $k apply -f "$SCRIPT_DIR/platform/storage/storageclass-onemind-local.yaml" >/dev/null
  install -d -m0755 "$PREFIX/platform"
  copy_tree "$SCRIPT_DIR/platform/postgres" "$PREFIX/platform/postgres"
  chmod -R a+rX "$PREFIX/platform"

  # The job key lives with the gateway (only it signs); the agent gets the public half.
  install -d -m0700 -o onemind -g onemind "$STATE/custodian"
  if [ ! -f "$STATE/custodian/job.key" ]; then
    runuser -u onemind -- "$PREFIX/venv/bin/python" -I -c \
      'import sys, pathlib; from onemind_core.backups.jobs import load_or_create_job_key as k; k(pathlib.Path(sys.argv[1]))' \
      "$STATE/custodian/job.key"
  fi
  install -m0644 "$STATE/custodian/job.pub" "$ETC/job.pub"

  # The box id is the hub's node id: sha256 of /etc/machine-id, first 12 hex (contract §1),
  # the same id the gateway reports, so restic's box= tag names this box.
  box=$(printf '%s' "$(tr -d '[:space:]' < /etc/machine-id)" | sha256sum | cut -c1-12)
  k3sv=$(printf '%s' "$K3S_VERSION" | tr '+' '-')
  (umask 077; cat > "$conf.new" <<EOF
{
  "box_id": "$box",
  "node_id": "$box",
  "generation": 0,
  "state_dir": "$agent_state",
  "scratch_dir": "$agent_state/scratch",
  "device_key_file": "$agent_state/secrets/device.key",
  "restic": {"binary": "/usr/lib/onemind/restic", "cache_dir": "/var/cache/onemind-backup"},
  "sqlite3_binary": "/usr/bin/sqlite3",
  "listen": "127.0.0.1:7480",
  "job_pubkey_file": "$ETC/job.pub",
  "storage_roots": ["/var/lib/rancher/k3s/storage"],
  "schedule": {"minute": -1, "maintenance_hour": 3, "verify_weekday": 0, "verify_min_age": "1h", "gateway_hourly": true},
  "retention": {"hourly": 24, "daily": 7, "weekly": 4, "monthly": 12},
  "targets": [],
  "units": {
    "system": {"paths": ["$ETC"], "sqlite": [{"path": "$STATE/onemind.db", "name": "gateway.db"}],
               "audit_log": "$STATE/audit.jsonl"},
    "k3s": {"paths": ["/var/lib/rancher/k3s/server/token", "/var/lib/rancher/k3s/server/tls",
                      "/var/lib/rancher/k3s/server/cred"],
            "state_db": "/var/lib/rancher/k3s/server/db/state.db", "version": "$k3sv"}
  }
}
EOF
  )
  mv "$conf.new" "$conf"

  # onemindd reads this file: it starts the backup agent and fills the heartbeat's "backup" object.
  grep -q '^ONEMIND_BACKUP_CONF=' "$ETC/onemindd.env" || echo "ONEMIND_BACKUP_CONF=$conf" >> "$ETC/onemindd.env"
  # One service: the agent runs inside onemindd. Retire the separate unit of earlier dev installs.
  systemctl disable --now onemind-backup >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/onemind-backup.service
  install -d -m0755 /etc/systemd/system/onemindd.service.d
  install -m0644 "$SCRIPT_DIR/systemd/onemindd-backup.conf" /etc/systemd/system/onemindd.service.d/backup.conf
  systemctl daemon-reload
  "$BIN/onemindd" backup-init -config "$conf"
  systemctl restart onemindd

  if ! grep -q '^ONEMIND_BACKUPS_ENABLED=' "$ETC/gateway.env"; then
    cat >> "$ETC/gateway.env" <<EOF
# Backups (core/onemind_core/backups; deploy/backup.sh).
ONEMIND_BACKUPS_ENABLED=1
ONEMIND_BACKUPS_JOB_KEY_FILE=$STATE/custodian/job.key
ONEMIND_DATABASES_PLATFORM_DIR=$PREFIX/platform/postgres
EOF
    systemctl restart onemind-gateway
  fi
  local _
  for _ in $(seq 1 60); do
    curl -fsS http://127.0.0.1:7480/api/v1/backup/status >/dev/null 2>&1 \
      && curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 && return 0
    sleep 1
  done
  die "backups: the agent or the gateway did not come up (journalctl -u onemindd -u onemind-gateway)"
}
