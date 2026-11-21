#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# BAK-02 (#163): the in-VM half of the whole-box restore drill, run as root on Debian 13 by drill.py.
#
#   in-vm.sh source  <repo> <onemindd>   the box being protected: install, data, backup to the USB disk
#   in-vm.sh restore <repo> <onemindd>   a CLEAN box: install, restore from the USB disk with the owner key, verify
#
# Prints DRILL-PHASE / DRILL-INFO / PASS / FAIL lines that test/restore-drill/drillcore.py judges.
# The owner key is read from /run/drill/owner.key (restore) or written there (source); it is never printed.
#
# Restore path today ("restic-owner-key"): the box does not yet have `onemind init --restore` (UMB-P08, #145),
# so the drill restores the way the emergency kit promises anyone can: plain restic with the owner key, onto a
# freshly installed box. When UMB-P08 lands, only restore_box() changes; the clock, data and checks stay.
# RUN, ANS and friends are read inside the single-quoted strings that check() evals.
# shellcheck disable=SC2034
set -uo pipefail

MODE="${1:?mode: source or restore}"
REPO="${2:?path of the repo copy}"
ONEMINDD="${3:?path of the onemindd binary}"
GW=http://127.0.0.1:8080
USB_UUID=5d1a2c3e-0b6f-4d8e-9a77-163000000001
USB_DEV=/dev/disk/by-id/virtio-drillusb
MNT=/run/onemind/backup/$USB_UUID
REPO_PATH=$MNT/onemind-restic
RESTIC=/usr/lib/onemind/restic
PAYLOAD_MB="${DRILL_PAYLOAD_MB:-256}"
BULK_ROWS=20000
EXPECTED=/root/drill-expected.env
FAILS=0

now() { date +%s.%N; }
phase() { printf 'DRILL-PHASE %s %s %s\n' "$1" "$2" "$(now)"; }
info() { printf 'DRILL-INFO %s=%s\n' "$1" "$2"; }
step() { printf '\n== %s\n' "$*"; }
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; FAILS=$((FAILS + 1)); fi; }
api() { curl -fsS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' "$@"; }
k() { k3s kubectl "$@"; }
wait_action() {
  local s
  for _ in $(seq 1 450); do
    s=$(api "$GW/v1/actions/$1" | jq -r .state)
    case $s in succeeded|failed|outcome_unknown|expired|cancelled) echo "$s"; return 0 ;; esac
    sleep 2
  done
  echo timeout
}

mount_usb() {
  for _ in $(seq 1 30); do [ -b "$USB_DEV" ] && break; sleep 1; done
  mkdir -p "$MNT"
  mount "$USB_DEV" "$MNT"
}

install_box() {
  mkdir -p /tmp/dist && echo '<!doctype html><title>OneMind</title>' > /tmp/dist/index.html
  (cd "$REPO" && deploy/install.sh --role hub --onemindd-bin "$ONEMINDD" --dashboard-dist /tmp/dist) > /tmp/install.log 2>&1 \
    || { tail -40 /tmp/install.log; return 1; }
  TOKEN=$(awk '/^OWNER TOKEN/{getline; getline; print $1; exit}' /tmp/install.log)
  [ -n "$TOKEN" ]
}

install_probe() {
  cp -r "$REPO/test/backup-wire/backup-probe" /opt/onemind/apps/backup-probe
  printf '{"scanned_at":"%s","result":"pass","images":[],"licence":{"spdx":"Apache-2.0","class":"L1"},"smoke":"skipped"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > /opt/onemind/apps/backup-probe/scan.json
  local exp a
  exp=$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)
  a=$(api -X POST "$GW/v1/actions" -d "{\"type\":\"app.install\",\"params\":{\"app_id\":\"backup-probe\"},\"idempotency_key\":\"drill-install-$MODE\",\"expires_at\":\"$exp\"}" | jq -r .id)
  [ "$(api -X POST "$GW/v1/actions/$a/approve" | jq -r .state)" = succeeded ] || return 1
  k -n app-backup-probe rollout status deploy/backup-probe --timeout=300s >/dev/null || return 1
  probe_pod
}
probe_pod() {
  POD=$(k -n app-backup-probe get pod -l app.kubernetes.io/name=backup-probe --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
}
kx() { k -n app-backup-probe exec "$POD" -c app -- "$@"; }
pgx() { k -n onemind-db exec -i postgres-0 -c postgres -- "$@"; }

# ------------------------------------------------------------------------------------------------ source
source_box() {
  phase seed start
  step "S0. a USB backup disk (second virtual disk, fixed UUID so the clean box finds it)"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq jq e2fsprogs >/dev/null
  mkfs.ext4 -q -U "$USB_UUID" "$USB_DEV" && mount_usb
  check "the USB disk is mounted where the agent looks for disks" 'mountpoint -q "$MNT"'

  step "S1. install the box"
  install_box; check "install finished and printed an owner token" '[ -n "${TOKEN:-}" ]'
  [ -n "${TOKEN:-}" ] || return 1
  A=$(api -X POST "$GW/v1/backups/destinations" -d "{\"kind\":\"usb\",\"label\":\"Drill USB disk\",\"config\":{\"usb_uuid\":\"$USB_UUID\"},\"approve\":true}" | jq -r .id)
  check "destination added" '[ "$(wait_action "$A")" = succeeded ]'

  step "S2. real data: a file, a ${PAYLOAD_MB} MiB payload, a database row and ${BULK_ROWS} bulk rows"
  install_probe; check "the probe app is running" '[ -n "${POD:-}" ]'
  [ -n "${POD:-}" ] || return 1
  kx sh -c "echo GOOD > /data/notes.txt && head -c $((PAYLOAD_MB * 1048576)) /dev/urandom > /data/payload.bin"
  PSHA=$(kx sha256sum /data/payload.bin | awk '{print $1}')
  kx psql -v ON_ERROR_STOP=1 -qc "create table notes(v text); insert into notes values ('GOOD'); create table bulk as select g from generate_series(1,$BULK_ROWS) g;"
  printf 'PAYLOAD_SHA=%s\nPAYLOAD_MB=%s\nBULK_ROWS=%s\n' "$PSHA" "$PAYLOAD_MB" "$BULK_ROWS" > "$EXPECTED"
  check "the payload hash was recorded" '[ ${#PSHA} = 64 ]'

  step "S3. back up the whole box (system, k3s, app) and write the emergency kit"
  A=$(api -X POST "$GW/v1/backups/runs" -d '{"approve":true}' | jq -r .id)
  check "backup run succeeded" '[ "$(wait_action "$A")" = succeeded ]'
  RUN=$(api "$GW/v1/backups/runs" | jq --arg a "$A" '[.[]|select(.action_id==$a)][0]')
  check "system, k3s and app units all succeeded" \
    '[ "$(echo "$RUN" | jq -r "[.units[]|select(.state==\"succeeded\")|.unit]|sort|join(\",\")")" = "app:backup-probe,k3s,system" ]'
  KIT=$(api -X POST "$GW/v1/backups/kit")
  mkdir -p /run/drill && (umask 077; echo "$KIT" | jq -r .one_time.owner_key > /run/drill/owner.key)
  ANS=$(echo "$KIT" | jq -c '.one_time.groups as $g | .kit.positions | map({key: tostring, value: $g[. - 1]}) | from_entries')
  check "the emergency kit confirms" '[ "$(api -X POST "$GW/v1/backups/kit/confirm" -d "{\"answers\":$ANS}" | jq -r .state)" = confirmed ]'
  unset KIT ANS
  check "the owner key alone opens the repository" 'RESTIC_PASSWORD_FILE=/run/drill/owner.key $RESTIC -r "$REPO_PATH" snapshots --tag onemind -q >/dev/null'
  sync; umount "$MNT"
  check "the USB disk was unmounted cleanly" '! mountpoint -q "$MNT"'
  phase seed end
}

# ------------------------------------------------------------------------------------------------ restore
# The one function UMB-P08 (`onemind init --restore`) replaces. Input: a freshly installed box, the USB disk
# mounted, the owner key in /run/drill/owner.key. Output: the probe app running with the old box's data.
restore_box() {
  local R=/var/tmp/drill-restore vol pv
  export RESTIC_PASSWORD_FILE=/run/drill/owner.key
  rm -rf "$R" && mkdir -p "$R/app" "$R/system"
  $RESTIC -r "$REPO_PATH" restore latest --tag unit=app:backup-probe --target "$R/app" >/dev/null || return 1
  $RESTIC -r "$REPO_PATH" restore latest --tag unit=system --target "$R/system" >/dev/null || return 1
  # The app on the new box has a new volume folder (a new claim id): its data goes into that folder.
  k -n app-backup-probe scale deploy/backup-probe --replicas=0 >/dev/null || return 1
  k -n app-backup-probe wait --for=delete pod -l app.kubernetes.io/name=backup-probe --timeout=120s >/dev/null || true
  vol=$(ls -d /var/lib/rancher/k3s/storage/pvc-*_app-backup-probe_data 2>/dev/null | head -1)
  pv=$(dirname "$(find "$R/app" -name notes.txt -not -path '*/cache/*' | head -1)")
  [ -n "$vol" ] && [ -n "$pv" ] && [ -d "$pv" ] || return 1
  cp -a "$pv"/. "$vol"/ || return 1
  # The database: recreate it empty (as the platform's own restore does), then load the dump.
  local dump name=app_backup_probe
  dump=$(find "$R/app" -name "$name.pgdump" | head -1)
  [ -n "$dump" ] || return 1
  pgx psql -v ON_ERROR_STOP=1 -X -q -U postgres -d postgres -c "DROP DATABASE IF EXISTS $name WITH (FORCE);" \
    -c "CREATE DATABASE $name OWNER $name;" -c "REVOKE ALL ON DATABASE $name FROM PUBLIC;" \
    -c "GRANT CONNECT, TEMPORARY ON DATABASE $name TO $name;" || return 1
  pgx sh -c "cat > /tmp/drill.pgdump && chmod 600 /tmp/drill.pgdump" < "$dump" || return 1
  pgx pg_restore -U postgres --no-owner "--role=$name" --exit-on-error --single-transaction -d "$name" /tmp/drill.pgdump || return 1
  pgx rm -f /tmp/drill.pgdump
  k -n app-backup-probe scale deploy/backup-probe --replicas=1 >/dev/null || return 1
  k -n app-backup-probe rollout status deploy/backup-probe --timeout=300s >/dev/null || return 1
  probe_pod
}

restore_on_clean_box() {
  # shellcheck disable=SC1090
  . "$EXPECTED"
  step "R0. the box is clean: nothing of the old box is on it"
  check "no OneMind or k3s on this machine yet" '! command -v k3s >/dev/null && [ ! -d /var/lib/onemind ]'
  check "the owner key arrived out of band" '[ -s /run/drill/owner.key ]'
  mount_usb
  check "the USB disk with the backups is mounted" 'mountpoint -q "$MNT"'

  phase install start
  step "R1. install a fresh box (the same one-command install a new owner runs)"
  install_box
  phase install end
  check "the fresh box installed and is healthy" '[ -n "${TOKEN:-}" ] && curl -fsS -m 5 "$GW/healthz" >/dev/null'
  [ -n "${TOKEN:-}" ] || return 1
  info restore_mode restic-owner-key

  phase restore start
  step "R2. restore the old box's data from the USB disk with the owner key"
  install_probe
  check "the app is installed on the new box" '[ -n "${POD:-}" ]'
  restore_box
  RC=$?
  phase restore end
  check "the restore from the repository succeeded" '[ "$RC" = 0 ]'
  [ "$RC" = 0 ] || return 1

  phase verify start
  step "R3. verify the data, byte for byte"
  check "the file is back" '[ "$(kx cat /data/notes.txt)" = GOOD ]'
  check "the payload hash matches the old box (${PAYLOAD_MB} MiB)" '[ "$(kx sha256sum /data/payload.bin | awk "{print \$1}")" = "$PAYLOAD_SHA" ]'
  check "the database row is back" '[ "$(kx psql -tAc "select string_agg(v, chr(44)) from notes")" = GOOD ]'
  check "all ${BULK_ROWS} bulk rows are back" '[ "$(kx psql -tAc "select count(*) from bulk")" = "$BULK_ROWS" ]'
  check "the app runs as its own database role" '[ "$(kx psql -tAc "select current_user")" = app_backup_probe ]'
  check "the old box's system snapshot restored with its audit log and k3s state" \
    '[ -n "$(find /var/tmp/drill-restore/system -name "*audit*" | head -1)" ] && [ -n "$(find /var/tmp/drill-restore/system -path "*k3s*" | head -1)" ]'
  check "the gateway is healthy after the restore" 'curl -fsS -m 5 "$GW/healthz" >/dev/null'
  phase verify end
}

case "$MODE" in
  source) source_box ;;
  restore) restore_on_clean_box ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
RC=$?
[ "$RC" = 0 ] || { echo "FAIL  the $MODE half stopped early (exit $RC)"; FAILS=$((FAILS + 1)); }
printf '\n%s\n' "$( [ "$FAILS" = 0 ] && echo "ALL CHECKS PASSED" || echo "$FAILS CHECK(S) FAILED")"
[ "$FAILS" = 0 ]
