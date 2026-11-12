#!/usr/bin/env bash
# Checks are strings evaluated by check(), so single quotes and "unused" variables are intended.
# shellcheck disable=SC2016,SC2034
# SPDX-License-Identifier: Apache-2.0
#
# The backup, break, restore, verify scenario on a real hub. Runs as root INSIDE a throwaway
# Debian 13 VM (lima-e2e.sh starts it); never run it on a machine you care about: it installs
# k3s and the whole developer install, and loop-mounts a fake USB disk.
#
#   in-vm.sh <repo checkout> <onemindd binary>
#
# Every check prints PASS or FAIL; the script exits 1 if any failed. Secrets (the owner token, the
# emergency kit's key) are used, never printed.
set -euo pipefail

REPO=$1
ONEMINDD=$2
GW=http://127.0.0.1:8080
FAILS=0
step() { printf '\n== %s\n' "$*"; }
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; FAILS=$((FAILS + 1)); fi; }
api() { curl -fsS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' "$@"; }
wait_action() {
  local s
  for _ in $(seq 1 450); do
    s=$(api "$GW/v1/actions/$1" | jq -r .state)
    case $s in succeeded|failed|outcome_unknown|expired|cancelled) echo "$s"; return 0 ;; esac
    sleep 2
  done
  echo timeout
}
k() { k3s kubectl "$@"; }

step "0. a USB backup disk: an ext4 image loop-mounted where the agent looks for disks"
DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq jq e2fsprogs >/dev/null
UUID=$(cat /proc/sys/kernel/random/uuid)
truncate -s 3G /var/tmp/usb.img
mkfs.ext4 -q -U "$UUID" /var/tmp/usb.img
mkdir -p "/run/onemind/backup/$UUID"
mount -o loop /var/tmp/usb.img "/run/onemind/backup/$UUID"
REPO_PATH=/run/onemind/backup/$UUID/onemind-restic

step "1. developer install (k3s, NATS, onemindd, gateway, backup agent)"
mkdir -p /tmp/dist && echo '<!doctype html><title>OneMind</title>' > /tmp/dist/index.html
(cd "$REPO" && deploy/install.sh --role hub --onemindd-bin "$ONEMINDD" --dashboard-dist /tmp/dist) > /tmp/install.log 2>&1 \
  || { tail -40 /tmp/install.log; exit 1; }
TOKEN=$(awk '/^OWNER TOKEN/{getline; getline; print $1; exit}' /tmp/install.log)
check "install finished and printed an owner token" '[ -n "$TOKEN" ]'
check "onemind-backup.service is active" 'systemctl is-active --quiet onemind-backup'
check "the backup agent listens on loopback only" '[ "$(ss -ltnH "sport = :7481" | awk "{print \$4}" | sort -u)" = 127.0.0.1:7481 ]'
check "an unsigned restore job is refused" '[ "$(curl -s -o /dev/null -w %{http_code} -X POST -d "{\"kind\":\"backup.restore\"}" http://127.0.0.1:7481/api/v1/backup/jobs)" = 403 ]'
check "status before setup: kit blocks onboarding" '[ "$(api $GW/v1/backups/status | jq -r ".setup.blocking[0]")" = emergency_kit ]'

step "2. add the USB disk as the destination (owner shortcut: request + approve)"
A=$(api -X POST "$GW/v1/backups/destinations" -d "{\"kind\":\"usb\",\"label\":\"Test USB disk\",\"config\":{\"usb_uuid\":\"$UUID\"},\"approve\":true}" | jq -r .id)
check "destination added" '[ "$(wait_action "$A")" = succeeded ]'

step "3. install the probe app: one volume, one shared-PostgreSQL database, backup hooks"
cp -r "$REPO/test/backup-wire/backup-probe" /opt/onemind/apps/backup-probe
printf '{"scanned_at":"%s","result":"pass","images":[],"licence":{"spdx":"Apache-2.0","class":"L1"},"smoke":"skipped"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > /opt/onemind/apps/backup-probe/scan.json
EXP=$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)
A=$(api -X POST "$GW/v1/actions" -d "{\"type\":\"app.install\",\"params\":{\"app_id\":\"backup-probe\"},\"idempotency_key\":\"e2e-install\",\"expires_at\":\"$EXP\"}" | jq -r .id)
INSTALL=$(api -X POST "$GW/v1/actions/$A/approve")
check "install succeeded (database, role and Secret first)" '[ "$(echo "$INSTALL" | jq -r .state)" = succeeded ]'
check "no password in the install result" '! echo "$INSTALL" | grep -qi "password\":\|PGPASSWORD=\|postgresql://"'
check "shared PostgreSQL is running" 'k -n onemind-db rollout status statefulset/postgres --timeout=300s >/dev/null'
check "its claim is on the Retain class" '[ "$(k -n onemind-db get pvc data-postgres-0 -o jsonpath={.spec.storageClassName})" = onemind-local ]'
k -n app-backup-probe rollout status deploy/backup-probe --timeout=300s >/dev/null
POD=$(k -n app-backup-probe get pod -l app.kubernetes.io/name=backup-probe -o jsonpath='{.items[0].metadata.name}')
kx() { k -n app-backup-probe exec "$POD" -c app -- "$@"; }
check "the app logs in to its own database with its own role" '[ "$(kx psql -tAc "select current_user")" = app_backup_probe ]'
check "the app role cannot open the maintenance database" '! kx psql -d postgres -tAc "select 1" >/dev/null 2>&1'

step "4. good data: a file in the volume and a row in the database"
kx sh -c 'echo GOOD > /data/notes.txt && mkdir -p /data/cache && echo junk > /data/cache/tmp'
kx psql -v ON_ERROR_STOP=1 -qc "create table notes(v text); insert into notes values ('GOOD');"

step "5. back up now (owner shortcut)"
A=$(api -X POST "$GW/v1/backups/runs" -d '{"approve":true}' | jq -r .id)
check "backup run succeeded" '[ "$(wait_action "$A")" = succeeded ]'
RUN=$(api "$GW/v1/backups/runs" | jq --arg a "$A" '[.[]|select(.action_id==$a)][0]')
check "the run has system, k3s and app units, all succeeded" \
  '[ "$(echo "$RUN" | jq -r "[.units[]|select(.state==\"succeeded\")|.unit]|sort|join(\",\")")" = "app:backup-probe,k3s,system" ]'
check "the pre hook ran inside the app container" 'kx test -s /data/last-pre-hook'
export RESTIC_PASSWORD_FILE=/var/lib/onemind-backup/secrets/device.key
check "plain restic lists the app snapshot by its tags" \
  '[ "$(/usr/lib/onemind/restic -r "$REPO_PATH" snapshots --tag onemind,unit=app:backup-probe --json | jq length)" -ge 1 ]'
LS=$(/usr/lib/onemind/restic -r "$REPO_PATH" ls latest --tag unit=app:backup-probe)
check "the snapshot holds the volume and the database dump" 'echo "$LS" | grep -q "/notes.txt$" && echo "$LS" | grep -q "app_backup_probe.pgdump$"'
check "excluded paths are not in it" '! echo "$LS" | grep -q "/cache/tmp$"'
check "the heartbeat carries the backup object" '[ "$(curl -fsS http://127.0.0.1:7480/api/v1/node | jq -r .backup.last_result)" = succeeded ]'
unset RESTIC_PASSWORD_FILE

step "6. emergency kit: shown once, typed back, opens the backup alone"
KIT=$(api -X POST "$GW/v1/backups/kit")
OWNER_KEY=$(echo "$KIT" | jq -r .one_time.owner_key)
ANS=$(echo "$KIT" | jq -c '.one_time.groups as $g | .kit.positions | map({key: tostring, value: $g[. - 1]}) | from_entries')
check "a wrong type-back is refused" '[ "$(api -o /dev/null -w %{http_code} -X POST "$GW/v1/backups/kit/confirm" -d "{\"answers\":{\"1\":\"AAAA\",\"2\":\"BBBB\"}}" || true)" != 200 ]'
check "the right groups confirm the kit" '[ "$(api -X POST "$GW/v1/backups/kit/confirm" -d "{\"answers\":$ANS}" | jq -r .state)" = confirmed ]'
check "onboarding is no longer blocked" '[ "$(api $GW/v1/backups/status | jq -r ".setup.blocking|length")" = 0 ]'
check "the owner key alone opens the repository (no device key)" \
  'RESTIC_PASSWORD="$OWNER_KEY" /usr/lib/onemind/restic -r "$REPO_PATH" snapshots --tag onemind -q >/dev/null'
check "the key is not on the box (gateway DB, audit log)" \
  '! grep -rqs "$OWNER_KEY" /var/lib/onemind /etc/onemind'
unset OWNER_KEY KIT ANS

step "7. break the data"
kx sh -c 'echo BROKEN > /data/notes.txt; rm -f /data/last-pre-hook'
kx psql -v ON_ERROR_STOP=1 -qc "update notes set v='BROKEN'; insert into notes values ('EXTRA');"

step "8. restore the app: requested, approved, pre-restore snapshot, health gate"
SNAP=$(api "$GW/v1/backups/snapshots?app_id=backup-probe" | jq -r '[.[]|select(.reason=="manual")][0].id')
REQ=$(api -X POST "$GW/v1/restores" -d "{\"snapshot_id\":\"$SNAP\",\"scope\":{\"app_id\":\"backup-probe\"}}")
A=$(echo "$REQ" | jq -r .id)
check "the restore waits for approval" '[ "$(echo "$REQ" | jq -r .state)" = awaiting_approval ]'
check "its plan says the current data is saved first" 'echo "$REQ" | jq -r ".restore.plan.steps[0]" | grep -q "pre-restore snapshot"'
api -X POST "$GW/v1/actions/$A/approve" >/dev/null
check "restore succeeded" '[ "$(wait_action "$A")" = succeeded ]'
k -n app-backup-probe rollout status deploy/backup-probe --timeout=180s >/dev/null || true
POD=$(k -n app-backup-probe get pod -l app.kubernetes.io/name=backup-probe --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
check "the file is back" '[ "$(kx cat /data/notes.txt)" = GOOD ]'
check "the database is back (one row, GOOD)" '[ "$(kx psql -tAc "select string_agg(v, chr(44)) from notes")" = GOOD ]'
RST=$(api "$GW/v1/restores" | jq '.[0]')
check "the health gate passed on fresh pods" '[ "$(echo "$RST" | jq -r .health_gate.verdict)" = pass ]'
PRE=$(echo "$RST" | jq -r .pre_restore_snapshot_id)
check "a pre-restore snapshot was taken" '[ -n "$PRE" ] && [ "$PRE" != null ]'

step "9. Rewind: the broken version is still browsable in the pre-restore snapshot"
DIR=$(api "$GW/v1/backups/snapshots/$PRE" | jq -r '.paths[]|select(test("_app-backup-probe_data$"))')
FILE=$(api -G "$GW/v1/backups/snapshots/$PRE/tree" --data-urlencode "path=$DIR" | jq -r '.[]|select(.name=="notes.txt").path')
check "download of notes.txt from the pre-restore snapshot says BROKEN" \
  '[ "$(api -G "$GW/v1/backups/snapshots/$PRE/file" --data-urlencode "path=$FILE")" = BROKEN ]'

step "10. verified-restore badge"
check "before a scratch restore the app badge is not green" '[ "$(api $GW/v1/backups/status | jq -r .badges.apps[\"backup-probe\"].state)" = unverified ]'
A=$(api -X POST "$GW/v1/backups/verify" -d '{"approve":true}' | jq -r .id)
check "scratch-restore verification passed" '[ "$(wait_action "$A")" = succeeded ]'
ST=$(api "$GW/v1/backups/status")
check "the app badge is green" '[ "$(echo "$ST" | jq -r .badges.apps[\"backup-probe\"].state)" = verified ]'
check "the box badge is green and health ok" '[ "$(echo "$ST" | jq -r .badges.box.state)/$(echo "$ST" | jq -r .health)" = verified/ok ]'

step "11. undo: restoring the pre-restore snapshot brings the broken data back"
A=$(api -X POST "$GW/v1/restores" -d "{\"snapshot_id\":\"$PRE\",\"scope\":{\"app_id\":\"backup-probe\"},\"approve\":true}" | jq -r .id)
check "undo restore succeeded" '[ "$(wait_action "$A")" = succeeded ]'
k -n app-backup-probe rollout status deploy/backup-probe --timeout=180s >/dev/null || true
POD=$(k -n app-backup-probe get pod -l app.kubernetes.io/name=backup-probe --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
check "the file is BROKEN again" '[ "$(kx cat /data/notes.txt)" = BROKEN ]'
check "the database is the broken one again" '[ "$(kx psql -tAc "select string_agg(v, chr(44) order by v) from notes")" = BROKEN,EXTRA ]'

step "12. the audit chain holds the whole story"
AUD=$(jq -r .event /var/lib/onemind/audit.jsonl | sort | uniq -c)
check "restore requested, approved and finished are audited" \
  'echo "$AUD" | grep -q " action.requested$" && echo "$AUD" | grep -q " action.approved$" && echo "$AUD" | grep -q " restore.state_changed$"'
check "snapshot reads are audited" 'echo "$AUD" | grep -q " backup.download$"'
check "the audit chain verifies" '/opt/onemind/venv/bin/onemind-audit-verify /var/lib/onemind/audit.jsonl >/dev/null'

printf '\n%s\n' "$( [ "$FAILS" = 0 ] && echo "ALL CHECKS PASSED" || echo "$FAILS CHECK(S) FAILED")"
[ "$FAILS" = 0 ]
