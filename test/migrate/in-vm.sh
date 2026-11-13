#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Migration kit e2e, inside a throwaway VM (run by test/migrate/lima-e2e.sh, never on a host).
# One k3s plays both "the cluster you are moving off" (namespace legacy-demo, reached only through
# a namespaced ServiceAccount kubeconfig) and "the OneMind box" (namespace app-legacy-demo, where
# the gateway applies with the node's admin kubeconfig, as on a real box).
set -euo pipefail

: "${KIT:?}" "${K3S_URL:?}" "${K3S_SHA256:?}" "${UV_URL:?}" "${UV_SHA256:?}"
NS=legacy-demo
APP=legacy-demo
HUB=http://127.0.0.1:8080
OWNER=dev-owner-token-change-me   # core/examples/tokens.example.yaml (dev token, not a secret)
DATA=/var/lib/omos-migrate-e2e
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
export ONEMIND_HUB=$HUB ONEMIND_TOKEN=$OWNER
PASS=0
FAIL=0
step() { printf '\n== %s\n' "$*"; }
ok() { PASS=$((PASS + 1)); printf 'PASS  %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL  %s\n' "$*"; }
check() { local what=$1; shift; if "$@"; then ok "$what"; else bad "$what"; fi; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {}, {'d': d}))" "$1"; }

fetch() { # url sha256 dest
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c --quiet -
}

step "k3s (pinned, checksum-verified)"
if ! command -v k3s >/dev/null; then
  fetch "$K3S_URL" "$K3S_SHA256" /usr/local/bin/k3s
  chmod 0755 /usr/local/bin/k3s
  ln -sf k3s /usr/local/bin/kubectl
  systemd-run --unit=k3s-e2e --property=KillMode=process /usr/local/bin/k3s server \
    --write-kubeconfig-mode 0600 --disable traefik --disable metrics-server >/dev/null
fi
for _ in $(seq 1 90); do kubectl get nodes 2>/dev/null | grep -q ' Ready' && break; sleep 2; done
kubectl wait --for=condition=Ready node --all --timeout=180s >/dev/null
for _ in $(seq 1 90); do kubectl -n kube-system get deploy/local-path-provisioner >/dev/null 2>&1 && break; sleep 2; done
kubectl -n kube-system rollout status deploy/local-path-provisioner --timeout=180s >/dev/null
ok "k3s $(k3s --version | head -1 | awk '{print $3}') ready"

# The box's platform layer (docs/architecture/DEPLOYMENTS.md §2.2) ships this class with the OS
# image; a plain k3s does not have it.
kubectl apply -f - >/dev/null <<'YAML'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: onemind-local
provisioner: rancher.io/local-path
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
YAML
ok "platform StorageClass onemind-local present"

step "gateway (uv-managed Python 3.12, kubernetes executor)"
if ! command -v uv >/dev/null; then
  fetch "$UV_URL" "$UV_SHA256" /tmp/uv.tgz
  tar -xzf /tmp/uv.tgz -C /tmp && install -m 0755 /tmp/uv-*/uv /usr/local/bin/uv
fi
cd "$KIT/core"
uv sync -q --python 3.12 --frozen
NODE_IP=$(kubectl get node -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
# A clean slate on every run (the VM may be reused with KEEP_VM=1).
pkill -f 'python -m onemind_core' 2>/dev/null || true
for _ in $(seq 1 30); do curl -fs "$HUB/healthz" >/dev/null 2>&1 || break; sleep 1; done
kubectl delete namespace legacy-demo app-$APP --ignore-not-found --wait=true >/dev/null
rm -rf "$DATA" && mkdir -p "$DATA"
if ! curl -fs "$HUB/healthz" >/dev/null 2>&1; then
  env ONEMIND_EXECUTOR=kubernetes ONEMIND_KUBECTL=/usr/local/bin/kubectl \
    ONEMIND_TOKENS_FILE="$KIT/core/examples/tokens.example.yaml" ONEMIND_APPS_DIR="$KIT/core/tests/fixtures/apps" \
    ONEMIND_DATA_DIR="$DATA" ONEMIND_NATS_URL= ONEMIND_HOST=0.0.0.0 ONEMIND_PORT=8080 \
    ONEMIND_MIGRATE_REPO_URL="http://$NODE_IP:8080" ONEMIND_MIGRATE_POLL_S=1 \
    nohup uv run --frozen python -m onemind_core >"$DATA/gateway.log" 2>&1 &
  for _ in $(seq 1 60); do curl -fs "$HUB/healthz" >/dev/null 2>&1 && break; sleep 1; done
fi
check "gateway answers /healthz" curl -fs "$HUB/healthz" -o /dev/null
cd "$KIT"

step "seed the old namespace"
kubectl apply -f "$KIT/test/migrate/fixtures/legacy-demo.yaml" >/dev/null
kubectl -n $NS create secret generic notes-env --from-literal=API_KEY="$(head -c 18 /dev/urandom | base64)" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
for w in deploy/notes deploy/web statefulset/db; do kubectl -n $NS rollout status $w --timeout=300s >/dev/null; done
sleep 3
ok "legacy-demo running (notes, web, db)"

step "namespaced kubeconfig from 'onemind migrate role' (read + copy + scale)"
"$KIT/onemind" migrate role --namespace $NS --copy --cutover | kubectl apply -f - >/dev/null
work=$(mktemp -d)
cd "$work"
# The recipe printed at the top of 'onemind migrate role', run as an owner would.
"$KIT/onemind" migrate role --namespace $NS | sed -n 's/^#   //p' | grep '^SERVER=\|^kubectl' > recipe.sh
bash -e recipe.sh
KC=$work/migrate.kubeconfig
check "the migration identity cannot read Secrets" \
  test "$(kubectl auth can-i get secrets -n $NS --as=system:serviceaccount:$NS:onemind-migrate)" = no
check "the migration identity cannot touch another namespace" \
  test "$(kubectl auth can-i list pods -n kube-system --as=system:serviceaccount:$NS:onemind-migrate)" = no
SA_TOKEN=$(KUBECONFIG=$KC kubectl config view --raw -o jsonpath='{.users[0].user.token}')

approve() { curl -fsS -X POST -H "Authorization: Bearer $OWNER" "$HUB/v1/actions/$1/approve" -o /dev/null; }
wait_action() { # id -> final state
  local s
  for _ in $(seq 1 600); do
    s=$(curl -fsS -H "Authorization: Bearer $OWNER" "$HUB/v1/actions/$1" | json 'd["state"]')
    case $s in succeeded|failed|outcome_unknown|cancelled|expired) echo "$s"; return;; esac
    sleep 2
  done
  echo timeout
}
result() { curl -fsS -H "Authorization: Bearer $OWNER" "$HUB/v1/actions/$1" | json '(d["result"] or {}).get("message")'; }
plan_json() { curl -fsS -H "Authorization: Bearer $OWNER" "$HUB/v1/migrate/plans/$PLAN"; }
copies() { # "pvc phase state files=N differ=M", one line per copy
  plan_json | json '"\n".join("%s %s %s files=%s differ=%s" % (c["pvc"], c["phase"], c["state"], c["files"], c["failed_files"]) for c in d["copies"])'
}
files_sha() { # namespace pod path -> sorted "sha  path" lines
  kubectl -n "$1" exec "$2" -- sh -c "cd $3 && find . -type f -exec sha256sum {} + | sort -k2"
}

step "plan (read-only, dry-run report)"
"$KIT/onemind" migrate plan --kubeconfig "$KC" --namespace $NS --app $APP --name "Legacy demo" | tee plan.txt
PLAN=$(grep -o 'mig_[0-9A-Z]*' plan.txt | head -1)
check "plan has no blocking findings" grep -q '^Result  *0 blocking' plan.txt
check "image pinned to the running digest" grep -q 'FIXED.*Image/docker.io/library/busybox:1.37.0.*pinned' plan.txt
check "secret values left behind (MOVE)" grep -q 'MOVE.*Secret/notes-env' plan.txt
check "Ingress dropped for a OneMind name" grep -q 'DROP.*Ingress/notes' plan.txt
check "CronJob skipped" grep -q 'SKIP.*CronJob/nightly' plan.txt
check "nothing was created in the old namespace" \
  test "$(kubectl -n $NS get pods -l onemind.io/migrate-helper -o name | wc -l)" -eq 0

step "import (approved), staged with 0 replicas"
# Stand-in for the on-box scan of private bundles (CORE-DEPLOY-2, not built yet): this harness
# writes the scan record the gate reads. A real box must get it from a real scan (F-7).
printf '{"scanned_at":"%s","result":"pass","scanner":"e2e stand-in for CORE-DEPLOY-2"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$DATA/migrate/bundles/$PLAN/scan.json"
A=$("$KIT/onemind" migrate import "$PLAN" --json | json 'd["id"]')
approve "$A"
check "import succeeded" test "$(wait_action "$A")" = succeeded
check "app-$APP has the volumes" kubectl -n app-$APP get pvc notes-data data-db-0 -o name
check "nothing runs yet" test "$(kubectl -n app-$APP get deploy notes -o jsonpath='{.spec.replicas}')" = 0

step "copy (approved): helper pod + restic + sha256 check, then side by side"
A=$("$KIT/onemind" migrate copy "$PLAN" --kubeconfig "$KC" --json | json 'd["id"]')
approve "$A"
S=$(wait_action "$A"); echo "copy: $S — $(result "$A")"
check "copy succeeded" test "$S" = succeeded
COPIES=$(copies); echo "$COPIES"
check "notes volume verified" grep -q '^notes-data warm verified' <<<"$COPIES"
check "helper pods removed from the old cluster" test "$(kubectl -n $NS get pods -l onemind.io/migrate-helper -o name | wc -l)" -eq 0
kubectl -n app-$APP rollout status deploy/notes --timeout=180s >/dev/null
OLD=$(kubectl -n $NS get pod -l app=notes -o jsonpath='{.items[0].metadata.name}')
NEW=$(kubectl -n app-$APP get pod -l app=notes -o jsonpath='{.items[0].metadata.name}')
files_sha $NS "$OLD" /data > old.sha; files_sha app-$APP "$NEW" /data > new.sha
check "notes files identical old vs new ($(wc -l < old.sha) files)" cmp -s old.sha new.sha
check "ownership and mode kept" test "$(kubectl -n app-$APP exec "$NEW" -- stat -c '%a %u' /data/docs/f1.bin /data/docs/f2.bin | tr '\n' ' ')" = "640 0 644 1000 "
check "old app still running (side by side)" test "$(kubectl -n $NS get deploy notes -o jsonpath='{.status.readyReplicas}')" = 1

step "cutover --stop-old (approved): final copy with the old writers stopped"
A=$("$KIT/onemind" migrate cutover "$PLAN" --kubeconfig "$KC" --stop-old --json | json 'd["id"]')
approve "$A"
S=$(wait_action "$A"); echo "cutover: $S — $(result "$A")"
check "cutover succeeded" test "$S" = succeeded
check "old workloads at 0" test "$(kubectl -n $NS get deploy notes -o jsonpath='{.spec.replicas}')$(kubectl -n $NS get sts db -o jsonpath='{.spec.replicas}')" = 00
COPIES=$(copies | grep ' final '); echo "$COPIES"
check "both final copies verified" test "$(grep -c ' final verified' <<<"$COPIES")" -eq 2
kubectl -n app-$APP rollout status sts/db --timeout=180s >/dev/null
# The old db volume, read through a short-lived pod now that its writer is stopped.
kubectl -n $NS run reader --image=docker.io/library/busybox:1.37.0@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec \
  --restart=Never --overrides='{"spec":{"containers":[{"name":"reader","image":"docker.io/library/busybox:1.37.0@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec","command":["sleep","300"],"volumeMounts":[{"name":"d","mountPath":"/d","readOnly":true}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"data-db-0","readOnly":true}}]}}' >/dev/null
kubectl -n $NS wait --for=condition=Ready pod/reader --timeout=120s >/dev/null
OLD_LINES=$(kubectl -n $NS exec reader -- wc -l /d/log.txt | awk '{print $1}')
OLD_SHA=$(kubectl -n $NS exec reader -- sha256sum /d/log.txt | awk '{print $1}')
NEW_HEAD=$(kubectl -n app-$APP exec db-0 -- sh -c "head -n $OLD_LINES /var/lib/db/log.txt | sha256sum" | awk '{print $1}')
check "db log carried over exactly ($OLD_LINES lines, then the new app appends)" test "$OLD_SHA" = "$NEW_HEAD"
kubectl -n $NS delete pod reader --wait=false >/dev/null

step "revert (approved): new app stops, old app back"
A=$("$KIT/onemind" migrate revert "$PLAN" --kubeconfig "$KC" --json | json 'd["id"]')
approve "$A"
check "revert succeeded" test "$(wait_action "$A")" = succeeded
check "old replicas restored" test "$(kubectl -n $NS get deploy notes -o jsonpath='{.spec.replicas}')$(kubectl -n $NS get sts db -o jsonpath='{.spec.replicas}')" = 11
check "new app stopped" test "$(kubectl -n app-$APP get deploy notes -o jsonpath='{.spec.replicas}')" = 0

step "records"
check "the ServiceAccount token never reached the audit log" sh -c "! grep -qF '$SA_TOKEN' '$DATA/audit.jsonl'"
check "no restore Secrets left on the box" test "$(kubectl -n app-$APP get secrets -l onemind.io/migrate -o name | wc -l)" -eq 0
check "audit chain intact" sh -c "cd '$KIT/core' && uv run --frozen onemind-audit-verify '$DATA/audit.jsonl' >/dev/null"
grep -o '"event": *"[a-z_.]*"' "$DATA/audit.jsonl" | sed 's/.*"\([a-z_.]*\)"$/\1/' | sort | uniq -c | sort -rn | head -20

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
