#!/usr/bin/env bash
# W5 restore drill. Runs INSIDE a disposable Lima VM as root. Usage: drill.sh <phase>
# phases: a1 (w5a: SQLite box + backup) | b1 (w5b: restore SQLite) | b2 (w5b: convert to etcd + snapshot)
#         a2 (w5a: wipe, restore etcd snapshot)
set -uo pipefail
S=<lab-dir>/w5-restore/shared
K3S_VERSION="v1.37.2+k3s1"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
export RESTIC_REPOSITORY=$S/restic-repo RESTIC_PASSWORD_FILE=$S/restic-pass
ts(){ date +%s.%N; }
log(){ echo "[$(date -u +%FT%TZ)] $*"; }
k(){ /usr/local/bin/k3s kubectl "$@"; }

deps(){
  log "deps"; export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null && apt-get install -y -qq sqlite3 restic curl bc >/dev/null
  restic version; sqlite3 --version; uname -a; cat /etc/debian_version
}
write_config(){ # $1 = extra yaml lines
  mkdir -p /etc/rancher/k3s
  cat > /etc/rancher/k3s/config.yaml <<EOF
node-name: box1
secrets-encryption: true
write-kubeconfig-mode: "0644"
disable:
  - traefik
  - metrics-server
$1
EOF
  log "config:"; cat /etc/rancher/k3s/config.yaml
}
install_k3s(){
  [ -f $S/install.sh ] || curl -sfL https://get.k3s.io -o $S/install.sh
  log "install.sh sha256: $(sha256sum $S/install.sh)"
  INSTALL_K3S_VERSION=$K3S_VERSION INSTALL_K3S_SKIP_START=true INSTALL_K3S_EXEC="server" sh $S/install.sh
  /usr/local/bin/k3s --version
}
wait_ready(){
  local t0=$(ts)
  for i in $(seq 1 180); do
    if k get --raw /readyz >/dev/null 2>&1 && k get node box1 2>/dev/null | grep -q " Ready"; then
      log "apiserver+node Ready after $(echo "$(ts)-$t0" | bc 2>/dev/null || echo ?)s"; return 0; fi
    sleep 2; done
  log "NOT READY after 360s"; return 1
}
wait_pod(){
  for i in $(seq 1 120); do
    k -n demo get pod writer 2>/dev/null | grep -q Running && { log "pod Running"; return 0; }; sleep 2; done
  log "pod NOT running"; k -n demo describe pod writer | tail -20; return 1
}
verify(){
  log "VERIFY"
  k get nodes -o wide
  k -n demo get cm,secret,pvc,pod
  log "cm value: $(k -n demo get cm demo-cm -o jsonpath='{.data.hello}')"
  log "secret value: $(k -n demo get secret demo-secret -o jsonpath='{.data.pw}' | base64 -d)"
  wait_pod && log "marker in pod: $(k -n demo exec writer -- cat /data/marker.txt)"
  log "expected marker: $(cat $S/marker.expected)"
}
idle_writes(){ # $1 label, $2 seconds
  local dev=$(lsblk -no PKNAME $(findmnt -no SOURCE /) | head -1); [ -z "$dev" ] && dev=vda
  local a=$(awk -v d=$dev '$3==d{print $10}' /proc/diskstats); sleep $2
  local b=$(awk -v d=$dev '$3==d{print $10}' /proc/diskstats)
  log "IDLE-WRITES $1 dev=$dev seconds=$2 sectors=$((b-a)) MiB=$(( (b-a)*512/1048576 ))"
  log "datastore dir size: $(du -sh /var/lib/rancher/k3s/server/db | cut -f1)"
}

case "${1:-}" in
a1)
  deps; write_config ""; install_k3s; systemctl start k3s; wait_ready
  k create ns demo
  for i in $(seq 1 60); do k -n demo get sa default >/dev/null 2>&1 && break; sleep 2; done
  k -n demo create configmap demo-cm --from-literal=hello=world-$(date +%s)
  k -n demo create secret generic demo-secret --from-literal=pw=s3cret-$RANDOM
  head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' > $S/marker.expected
  cat <<EOF | k apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: data, namespace: demo}
spec: {accessModes: [ReadWriteOnce], storageClassName: local-path, resources: {requests: {storage: 100Mi}}}
---
apiVersion: v1
kind: Pod
metadata: {name: writer, namespace: demo}
spec:
  containers:
  - name: w
    image: docker.io/library/busybox:1.37.0
    command: ["sh","-c","[ -f /data/marker.txt ] || echo $(cat $S/marker.expected) > /data/marker.txt; sleep 1000000"]
    volumeMounts: [{name: d, mountPath: /data}]
  volumes: [{name: d, persistentVolumeClaim: {claimName: data}}]
EOF
  wait_pod; verify
  k get pv -o jsonpath='{range .items[*]}{.metadata.name}{" nodeAffinity="}{.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values}{" path="}{.spec.local.path}{.spec.hostPath.path}{"\n"}{end}'
  log "H1: k3s etcd-snapshot save on SQLite"; /usr/local/bin/k3s etcd-snapshot save; log "H1 exit=$?"
  ls -la /var/lib/rancher/k3s/server/db/
  idle_writes sqlite 600
  log "BACKUP (online, k3s running)"; t0=$(ts)
  mkdir -p $S/bk-sqlite
  sqlite3 /var/lib/rancher/k3s/server/db/state.db ".backup '$S/bk-sqlite/state.db'"
  log "sqlite3 integrity: $(sqlite3 $S/bk-sqlite/state.db 'PRAGMA integrity_check;')"
  cp /var/lib/rancher/k3s/server/token $S/bk-sqlite/token
  cp /etc/rancher/node/password $S/bk-sqlite/node-password
  [ -f $S/restic-pass ] || head -c 32 /dev/urandom | base64 > $S/restic-pass
  restic snapshots >/dev/null 2>&1 || restic init
  restic backup --tag sqlite-box /var/lib/rancher/k3s/storage
  log "backup took $(echo "$(ts)-$t0" | bc)s"; ls -la $S/bk-sqlite; du -sh $S/restic-pass $S/restic-repo
  ;;
b1)
  deps; write_config ""; install_k3s
  t0=$(ts)
  mkdir -p /var/lib/rancher/k3s/server/db /etc/rancher/node
  cp $S/bk-sqlite/state.db /var/lib/rancher/k3s/server/db/state.db
  cp $S/bk-sqlite/token /var/lib/rancher/k3s/server/token
  cp $S/bk-sqlite/node-password /etc/rancher/node/password
  restic restore latest --tag sqlite-box --target /
  systemctl start k3s; wait_ready; verify
  log "restore-to-ready took $(echo "$(ts)-$t0" | bc)s"
  ;;
b2)
  write_config "cluster-init: true"; t0=$(ts)
  systemctl restart k3s; wait_ready
  journalctl -u k3s --no-pager | grep -i -E "Migrating content from sqlite|Starting etcd for new cluster" | head -3
  journalctl -u k3s --no-pager | grep -c "Migrating etcd key" | sed 's/^/keys migrated: /'
  ls -la /var/lib/rancher/k3s/server/db/
  verify; log "conversion took $(echo "$(ts)-$t0" | bc)s"
  idle_writes etcd 600
  /usr/local/bin/k3s etcd-snapshot save --name drill; log "etcd-snapshot exit=$?"
  mkdir -p $S/bk-etcd; cp /var/lib/rancher/k3s/server/db/snapshots/drill-* $S/bk-etcd/
  cp /var/lib/rancher/k3s/server/token $S/bk-etcd/token
  log "snapshot file starts with: $(head -c 64 $S/bk-etcd/drill-* | strings | head -2 | tr '\n' ' ')"
  restic backup --tag etcd-box /var/lib/rancher/k3s/storage; ls -la $S/bk-etcd
  ;;
a2)
  log "WIPE w5a"; /usr/local/bin/k3s-uninstall.sh >/dev/null 2>&1; ls /var/lib/rancher 2>&1
  write_config "cluster-init: true"; install_k3s; t0=$(ts)
  snap=$(ls $S/bk-etcd/drill-* | head -1)
  timeout 300 /usr/local/bin/k3s server --cluster-reset --cluster-reset-restore-path="$snap" --token="$(cat $S/bk-etcd/token)" > /tmp/reset.log 2>&1
  log "reset exit=$?"; grep -i -E "restart without --cluster-reset|restor|error" /tmp/reset.log | tail -5
  echo "token: $(cat $S/bk-etcd/token)" > /dev/null
  cp $S/bk-etcd/token /var/lib/rancher/k3s/server/token
  restic restore latest --tag etcd-box --target /
  systemctl start k3s; wait_ready; verify
  log "etcd restore-to-ready took $(echo "$(ts)-$t0" | bc)s"
  ;;
*) echo "usage: $0 a1|b1|b2|a2"; exit 2;;
esac
