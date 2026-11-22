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
  local try
  for try in 1 2; do
    (cd "$REPO" && deploy/install.sh --role hub --onemindd-bin "$ONEMINDD" --dashboard-dist /tmp/dist) > /tmp/install.log 2>&1 && break
    # install.sh waits 60 s for the gateway's first start (a cold start can take longer in a nested VM). That is the only
    # failure retried, once: the installer is re-runnable, and it prints the owner token only on a first run, so the
    # tokens file of the half-finished run goes first (the installer says to do exactly that when a token is lost).
    if [ "$try" = 1 ] && grep -q 'gateway did not answer /healthz' /tmp/install.log; then
      info install_retried 1
      rm -f /etc/onemind/tokens.yaml
      continue
    fi
    tail -40 /tmp/install.log
    return 1
  done
  TOKEN=$(awk '/^OWNER TOKEN/{getline; getline; print $1; exit}' /tmp/install.log)
  [ -n "$TOKEN" ]
}

# KNOWN PRODUCT GAP, worked around here so the drill can reach the restore (reported in the PR for #163): the hardened
# gateway (H-03, deploy/k8s/gateway-rbac.yaml) may only touch app-* namespaces, but an app with `spec.database` makes it
# create and read the shared PostgreSQL in onemind-db, so such an install fails with "statefulsets.apps postgres is
# forbidden". As the cluster admin this creates what the gateway cannot (namespace, admin Secret, the PostgreSQL manifests)
# a namespaced Role so the gateway can watch and exec into it, and one line in the fence policy that lets that exec through. Second to fourth gaps: databases.py creates the app's namespace without a Pod
# Security label, which the fence rejects, so the probe's namespace is created here first. DRILL-INFO db_rbac_workaround=1 marks every run that
# needed it; delete this function when the platform grants the gateway that itself.
provision_shared_db() {
  k create namespace onemind-db >/dev/null 2>&1 || true
  k label namespace onemind-db app.kubernetes.io/part-of=onemind onemind.io/platform=postgres pod-security.kubernetes.io/enforce=baseline --overwrite >/dev/null
  k -n onemind-db get secret postgres-admin >/dev/null 2>&1 \
    || k -n onemind-db create secret generic postgres-admin --from-literal=POSTGRES_PASSWORD="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" >/dev/null
  k apply -k /opt/onemind/platform/postgres >/dev/null || return 1
  k apply -f - >/dev/null <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: onemind-gateway-db, namespace: onemind-db}
rules:
  - {apiGroups: ["apps"], resources: [statefulsets], verbs: [get, list, watch]}
  - {apiGroups: [""], resources: [pods, pods/log], verbs: [get, list, watch]}
  - {apiGroups: [""], resources: [pods/exec], verbs: [create]}
  - {apiGroups: [""], resources: [persistentvolumeclaims], verbs: [get, list, watch]}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: onemind-gateway-db, namespace: onemind-db}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: Role, name: onemind-gateway-db}
subjects: [{kind: ServiceAccount, name: onemind-gateway, namespace: onemind-system}]
YAML
  # The fence (a ValidatingAdmissionPolicy) also denies the gateway's `kubectl exec` into onemind-db: let it through.
  k get validatingadmissionpolicy onemind-gateway-fence -o json \
    | jq '.spec.validations[0].expression = "request.namespace == \"onemind-db\" || " + .spec.validations[0].expression' | k replace -f - >/dev/null || return 1
  # The same fence rejects the app namespace databases.py creates for the app's Secret (no Pod Security label): create it
  # properly first; the app install then applies its own labels on top.
  k create namespace app-backup-probe >/dev/null 2>&1 || true
  k label namespace app-backup-probe onemind.io/app=backup-probe pod-security.kubernetes.io/enforce=baseline --overwrite >/dev/null
  # Third: the database step writes the app's Secret before the executor binds the gateway into the namespace, so the
  # Secret write is forbidden. The executor's own binding (same name and role) is created here first.
  k create rolebinding onemind-gateway --clusterrole=onemind-app-deployer --serviceaccount=onemind-system:onemind-gateway \
    -n app-backup-probe >/dev/null 2>&1 || true
  # Fourth: an app's pre-backup hook runs in its pod through `kubectl exec`, which the deployer role does not allow either.
  k -n app-backup-probe create role onemind-gateway-exec --verb=create --resource=pods/exec >/dev/null 2>&1 || true
  k -n app-backup-probe create rolebinding onemind-gateway-exec --role=onemind-gateway-exec \
    --serviceaccount=onemind-system:onemind-gateway >/dev/null 2>&1 || true
  sleep 5   # the API server takes a moment to pick the policy change up
  k -n onemind-db rollout status statefulset/postgres --timeout=300s >/dev/null || return 1
  info db_rbac_workaround 1
}

install_probe() {
  cp -r "$REPO/test/backup-wire/backup-probe" /opt/onemind/apps/backup-probe
  printf '{"scanned_at":"%s","result":"pass","images":[],"licence":{"spdx":"Apache-2.0","class":"L1"},"smoke":"skipped"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > /opt/onemind/apps/backup-probe/scan.json
  local exp a
  exp=$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)
  a=$(api -X POST "$GW/v1/actions" -d "{\"type\":\"app.install\",\"params\":{\"app_id\":\"backup-probe\"},\"idempotency_key\":\"drill-install-$MODE\",\"expires_at\":\"$exp\"}" | jq -r .id)
  if [ "$(api -X POST "$GW/v1/actions/$a/approve" | jq -r .state)" != succeeded ]; then
    echo "app.install did not succeed: $(api "$GW/v1/actions/$a" | jq -c '{state, result}' | cut -c1-700)"
    return 1
  fi
  GW_ACTION=$a
  # Fifth product gap, worked around here: the gateway's default-deny policy for app-<id> leaves an app no path to the
  # shared PostgreSQL in onemind-db (its egress allows DNS, the namespace and the internet minus private ranges), so a
  # database app installs, runs, and can never connect. The shared PostgreSQL already admits app namespaces on 5432;
  # this adds the app side. Policies only add, so it is safe next to the gateway's own. Marked in the results.
  k -n app-backup-probe apply -f - >/dev/null <<'YAML' || return 1
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: drill-allow-shared-postgres}
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
    - to: [{namespaceSelector: {matchLabels: {onemind.io/platform: postgres}}}]
      ports: [{protocol: TCP, port: 5432}]
YAML
  info db_netpol_workaround 1
  k -n app-backup-probe rollout status deploy/backup-probe --timeout=300s >/dev/null || return 1
  probe_pod
}
probe_pod() {
  POD=$(k -n app-backup-probe get pod -l app.kubernetes.io/name=backup-probe --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
}
kx() { k -n app-backup-probe exec "$POD" -c app -- "$@"; }
gw_action_state() { sqlite3 /var/lib/onemind/onemind.db "select state from actions where id='$GW_ACTION'"; }
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

  provision_shared_db; PRC=$?
  check "the shared PostgreSQL is provisioned for the gateway" '[ "$PRC" = 0 ]'
  step "S2. real data: a file, a ${PAYLOAD_MB} MiB payload, a database row and ${BULK_ROWS} bulk rows"
  install_probe; check "the probe app is running" '[ -n "${POD:-}" ]'
  [ -n "${POD:-}" ] || return 1
  kx sh -c "echo GOOD > /data/notes.txt && head -c $((PAYLOAD_MB * 1048576)) /dev/urandom > /data/payload.bin"
  PSHA=$(kx sha256sum /data/payload.bin | awk '{print $1}')
  if ! { kx psql -v ON_ERROR_STOP=1 -qc "create table notes(v text); insert into notes values ('GOOD'); create table bulk as select g from generate_series(1,$BULK_ROWS) g;" ; }; then
    echo "DIAG probe cannot reach the shared PostgreSQL"
    k -n onemind-db get pods,svc,endpoints,networkpolicy -o wide 2>&1 | tail -20
    k get ns --show-labels 2>&1 | tail -12
    kx env 2>&1 | /usr/bin/grep -i '^PG' | sed 's/PASSWORD=.*/PASSWORD=<hidden>/'
    pgx sh -c 'pg_isready -h "$(hostname -i)"; pg_isready -h 127.0.0.1; psql -U postgres -Atc "show listen_addresses; select rolname from pg_roles where rolname like '"'"'app%'"'"'"' 2>&1 | tail -6
    kx sh -c 'timeout 3 bash -c "echo > /dev/tcp/10.42.0.7/5432" && echo direct-pod-ip-ok || echo direct-pod-ip-failed; timeout 3 bash -c "echo > /dev/tcp/$PGHOST/5432" && echo svc-ok || echo svc-failed' 2>&1 | tail -3
    k -n onemind-db get networkpolicy -o yaml 2>&1 | /usr/bin/grep -c . ; k -n app-backup-probe get networkpolicy 2>&1 | tail -5
    kx sh -c 'getent hosts postgres.onemind-db.svc.cluster.local; (command -v nc && nc -zvw3 postgres.onemind-db.svc.cluster.local 5432)' 2>&1 | tail -5
    return 1
  fi
  # Two canaries for the system snapshot: a ConfigMap only the old box's k3s datastore knows, and the install action in
  # the old box's gateway database (and so in its audit log). The clean box must get both back.
  K3S_CANARY=$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')
  k -n default create configmap drill-canary --from-literal=v="$K3S_CANARY" >/dev/null
  printf 'PAYLOAD_SHA=%s\nPAYLOAD_MB=%s\nBULK_ROWS=%s\nK3S_CANARY=%s\nGW_ACTION=%s\n' "$PSHA" "$PAYLOAD_MB" "$BULK_ROWS" "$K3S_CANARY" "$GW_ACTION" > "$EXPECTED"
  check "the payload hash and the system canaries were recorded" '[ ${#PSHA} = 64 ] && [ -n "$K3S_CANARY" ] && [ -n "${GW_ACTION:-}" ]'

  step "S3. back up the whole box (system, k3s, app) and write the emergency kit"
  A=$(api -X POST "$GW/v1/backups/runs" -d '{"approve":true}' | jq -r .id)
  check "backup run succeeded" '[ "$(wait_action "$A")" = succeeded ]'
  RUN=$(api "$GW/v1/backups/runs" | jq --arg a "$A" '[.[]|select(.action_id==$a)][0]')
  echo "backup run units: $(echo "$RUN" | jq -c '{state, units: [.units[]? | {unit, state, error}]}' | cut -c1-1500)"
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
# The two functions UMB-P08 (`onemind init --restore`) replaces. Input: a freshly installed box, the USB disk
# mounted, the owner key in /run/drill/owner.key. Output: the old box's own state back, the probe app running with
# the old box's data. Plain restic with the owner key, the way the emergency kit says anyone can.
R=/var/tmp/drill-restore
STAGE=
SRV=/var/lib/rancher/k3s/server

# One snapshot of a unit, restored into a scratch folder.
fetch_unit() {   # fetch_unit <unit> <dir>
  rm -rf "$2" && mkdir -p "$2" && $RESTIC -r "$REPO_PATH" restore latest --tag "unit=$1" --target "$2" >/dev/null
}

# The system and k3s snapshots go back onto the machine: the gateway's database and audit log, /etc/onemind, and
# k3s's own datastore, token, CA and credentials. Nothing is only "checked for presence".
restore_system() {
  local gdb audit sdb f u
  STAGE="fetch the system and k3s snapshots"
  fetch_unit system "$R/system" && fetch_unit k3s "$R/k3s" || return 1
  gdb=$(find "$R/system" -name gateway.db | head -1)
  audit=$(find "$R/system" -name audit.jsonl | head -1)
  sdb=$(find "$R/k3s" -name state.db | head -1)
  [ -n "$gdb" ] && [ -n "$audit" ] && [ -n "$sdb" ] && [ -d "$R/system/etc/onemind" ] && [ -d "$R/k3s$SRV/tls" ] || return 1
  STAGE="stop the services"
  # Stop everything that holds these files (the new box's own, just-installed state is replaced by the old box's).
  systemctl stop onemind-gateway-token.timer 2>/dev/null
  STOPPED=$(systemctl list-units 'onemind*' --type=service --state=active --no-legend --plain | awk '{print $1}')
  for u in $STOPPED; do systemctl stop "$u" || return 1; done
  systemctl stop k3s || return 1
  STAGE="put the files back"
  # /etc/onemind: the old box's tokens, TLS and settings (the whole identity of the box).
  cp -a "$R/system/etc/onemind/." /etc/onemind/ || return 1
  # The gateway's SQLite database and audit log: written through the existing files so owner and mode stay.
  cat "$gdb" > /var/lib/onemind/onemind.db && rm -f /var/lib/onemind/onemind.db-wal /var/lib/onemind/onemind.db-shm || return 1
  cat "$audit" > /var/lib/onemind/audit.jsonl || return 1
  # k3s: token, CA/TLS, credentials (these include the key that encrypts Secrets) and the datastore itself.
  for f in token tls cred; do
    rm -rf "${SRV:?}/$f" && cp -a "$R/k3s$SRV/$f" "$SRV/$f" || return 1
  done
  mkdir -p "$SRV/db" && cat "$sdb" > "$SRV/db/state.db" && rm -f "$SRV/db/state.db-wal" "$SRV/db/state.db-shm" || return 1
  STAGE="start k3s from the restored datastore"
  systemctl start k3s || return 1
  for _ in $(seq 1 120); do k get nodes 2>/dev/null | /usr/bin/grep -q ' Ready' && break; sleep 2; done
  k get nodes 2>/dev/null | /usr/bin/grep -q ' Ready' || return 1
  # The shared PostgreSQL's own data folder is not in any backup (the apps' dumps are). The restored cluster state
  # starts it empty with the old admin Secret; each app's role comes back with the password its Secret already holds.
  # The restored cluster state names the old box's local-path volume folders, which do not exist here. The kubelet
  # would create them root-only 0755, and PostgreSQL (not root) then cannot write; the provisioner's own mode is 0777.
  STAGE="make the restored volume folders writable"
  for f in $(k get pv -o jsonpath='{range .items[*]}{.spec.hostPath.path}{"\n"}{.spec.local.path}{"\n"}{end}' 2>/dev/null | sort -u); do
    [ -n "$f" ] && mkdir -p "$f" && chmod 0777 "$f" || true
  done
  k -n onemind-db delete pod postgres-0 --wait=false >/dev/null 2>&1   # skip the crash-loop back-off
  STAGE="wait for the shared PostgreSQL to start empty"
  for _ in $(seq 1 180); do pgx pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2; done
  pgx pg_isready -U postgres >/dev/null 2>&1 || return 1
  STAGE="recreate the app's database role"
  local pw
  pw=$(k -n app-backup-probe get secret probe-db -o jsonpath='{.data.PGPASSWORD}' | base64 -d) && [ -n "$pw" ] || return 1
  pgx psql -v ON_ERROR_STOP=1 -X -q -U postgres -d postgres \
    -c "CREATE ROLE app_backup_probe LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '$pw';" || return 1
  STAGE="start the OneMind services"
  systemctl daemon-reload
  for u in $STOPPED $STOPPED; do systemctl start "$u" 2>/dev/null; done   # twice: a unit that needs another one retries
  systemctl start onemind-gateway-token.timer 2>/dev/null
  for _ in $(seq 1 120); do curl -fsS -m 3 "$GW/healthz" >/dev/null 2>&1 && return 0; sleep 2; done
  return 1
}

# The app's own data (its volume and its database dump) from its snapshot, into the app the restored cluster state
# already knows (its Deployment and claims came back with the datastore).
restore_box() {
  local vol pv dump name=app_backup_probe
  fetch_unit app:backup-probe "$R/app" || return 1
  k -n app-backup-probe rollout status deploy/backup-probe --timeout=300s >/dev/null || return 1
  k -n app-backup-probe scale deploy/backup-probe --replicas=0 >/dev/null || return 1
  k -n app-backup-probe wait --for=delete pod -l app.kubernetes.io/name=backup-probe --timeout=120s >/dev/null || true
  vol=$(ls -d /var/lib/rancher/k3s/storage/pvc-*_app-backup-probe_data 2>/dev/null | head -1)
  pv=$(dirname "$(find "$R/app" -name notes.txt -not -path '*/cache/*' | head -1)")
  [ -n "$vol" ] && [ -n "$pv" ] && [ -d "$pv" ] || return 1
  cp -a "$pv"/. "$vol"/ || return 1
  # The database: recreate it empty (as the platform's own restore does), then load the dump.
  dump=$(find "$R/app" -name "$name.pgdump" | head -1)
  [ -n "$dump" ] || return 1
  pgx psql -v ON_ERROR_STOP=1 -X -q -U postgres -d postgres -c "DROP DATABASE IF EXISTS $name WITH (FORCE);" \
    -c "CREATE DATABASE $name OWNER $name;" -c "REVOKE ALL ON DATABASE $name FROM PUBLIC;" \
    -c "GRANT CONNECT, TEMPORARY ON DATABASE $name TO $name;" || return 1
  pgx sh -c "cat > /tmp/drill.pgdump && chmod 600 /tmp/drill.pgdump" < "$dump" || return 1
  pgx pg_restore -U postgres --no-owner "--role=$name" --exit-on-error --single-transaction -d "$name" /tmp/drill.pgdump || return 1
  pgx rm -f /tmp/drill.pgdump
  k -n app-backup-probe scale deploy/backup-probe --replicas=1 >/dev/null || return 1
  # Fifth product gap, worked around here: the gateway's default-deny policy for app-<id> leaves an app no path to the
  # shared PostgreSQL in onemind-db (its egress allows DNS, the namespace and the internet minus private ranges), so a
  # database app installs, runs, and can never connect. The shared PostgreSQL already admits app namespaces on 5432;
  # this adds the app side. Policies only add, so it is safe next to the gateway's own. Marked in the results.
  k -n app-backup-probe apply -f - >/dev/null <<'YAML' || return 1
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: drill-allow-shared-postgres}
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
    - to: [{namespaceSelector: {matchLabels: {onemind.io/platform: postgres}}}]
      ports: [{protocol: TCP, port: 5432}]
YAML
  info db_netpol_workaround 1
  k -n app-backup-probe rollout status deploy/backup-probe --timeout=300s >/dev/null || return 1
  probe_pod
}

restore_on_clean_box() {
  # shellcheck disable=SC1090
  . "$EXPECTED"
  export RESTIC_PASSWORD_FILE=/run/drill/owner.key
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
  step "R2. restore the old box from the USB disk with the owner key: system and k3s, then the app's data"
  restore_system
  RC=$?
  [ "$RC" = 0 ] || { echo "restore_system stopped at: $STAGE"; k get pods -A 2>&1 | tail -15; k -n onemind-db logs postgres-0 --previous --tail=25 2>&1 | tail -25; systemctl --no-pager --failed 2>&1 | head -8; }
  check "the system and k3s snapshots were restored onto the new box" '[ "$RC" = 0 ]'
  if [ "$RC" = 0 ]; then restore_box; RC=$?; fi
  phase restore end
  check "the app's data was restored from the repository" '[ "$RC" = 0 ]'
  [ "$RC" = 0 ] || return 1

  phase verify start
  step "R3. verify the data and the system state, byte for byte"
  check "the file is back" '[ "$(kx cat /data/notes.txt)" = GOOD ]'
  check "the payload hash matches the old box (${PAYLOAD_MB} MiB)" '[ "$(kx sha256sum /data/payload.bin | awk "{print \$1}")" = "$PAYLOAD_SHA" ]'
  check "the database row is back" '[ "$(kx psql -tAc "select string_agg(v, chr(44)) from notes")" = GOOD ]'
  check "all ${BULK_ROWS} bulk rows are back" '[ "$(kx psql -tAc "select count(*) from bulk")" = "$BULK_ROWS" ]'
  check "the app runs as its own database role" '[ "$(kx psql -tAc "select current_user")" = app_backup_probe ]'
  check "k3s runs from the old box's datastore (its ConfigMap canary is back)" '[ "$(k -n default get configmap drill-canary -o jsonpath="{.data.v}")" = "$K3S_CANARY" ]'
  check "k3s serves the old box's app namespace and the node is Ready" 'k get ns app-backup-probe >/dev/null && k get nodes | /usr/bin/grep -q " Ready"'
  check "the gateway database is the old box's (its install action is there, succeeded)" \
    '[ "$(gw_action_state)" = succeeded ]'
  check "the gateway database passes its integrity check" '[ "$(sqlite3 /var/lib/onemind/onemind.db "pragma integrity_check")" = ok ]'
  check "the old box's audit log is back and records that action" '/usr/bin/grep -q "$GW_ACTION" /var/lib/onemind/audit.jsonl'
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
