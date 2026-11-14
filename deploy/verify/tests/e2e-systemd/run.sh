#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# End-to-end test of deploy/install.sh on two "stock Debian 13 machines": privileged containers with
# systemd as PID 1 (Dockerfile.debian13). Ported from PR #27 and adapted to main (systemd gateway,
# offline bundle, agent token, node-check). Every OneMind part is the real one, built by
# deploy/bundle.sh from this checkout; the machines get only the bundle, never the checkout.
#
#   1. deploy/bundle.sh for the Docker host's architecture (or E2E_BUNDLE=DIR to reuse one)
#   2. hub: BUNDLE/src/deploy/install.sh --role hub --with-agent-token (k3s, NATS, onemindd, gateway)
#   3. owner and agent tokens printed once; no raw token anywhere on the hub's disk
#   4. hub again: exit 0, tokens kept, no new token printed (idempotent)
#   5. node: --join with a one-time code from `onemind fabric ticket`; the owner approves on the hub
#   6. 2 k3s nodes Ready; 2 onemindd heartbeats on NATS; the gateway lists 2 online machines
#   7. node-check.sh passes on the hub and on the node
#   8. verify.sh on the hub (owner + agent token files, audit file, kubernetes executor); then the
#      owner installs the app (E2E_APP, default ntfy) through an approved action and k3s runs it
#   9. --dry-run on the installed hub changes no file; --uninstall --purge on the node removes it all
#
#   deploy/verify/tests/e2e-systemd/run.sh            # KEEP=1 leaves the containers running
#   E2E_APP=uptime-kuma E2E_BUNDLE=out/onemind-bundle-arm64 deploy/verify/tests/e2e-systemd/run.sh
#
# Needs Docker that can run privileged containers (Linux, Docker Desktop, a Lima VM), python3, ~4 GB RAM.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../../.." && pwd)
PFX=onemind-e2e
NET=$PFX-net HUB=$PFX-hub NODE=$PFX-node
APP=${E2E_APP:-ntfy}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/onemind-e2e.XXXXXX")
RESULTS="" FAILED=0

case "$(docker info --format '{{.Architecture}}')" in
  aarch64|arm64) ARCH=arm64 ;;
  x86_64|amd64) ARCH=amd64 ;;
  *) echo "unsupported Docker architecture" >&2; exit 2 ;;
esac

# shellcheck disable=SC2317,SC2329  # invoked via trap (SC2317 in shellcheck <0.10, SC2329 after)
cleanup() {
  if [ "${KEEP:-0}" != 1 ]; then
    docker rm -f "$HUB" "$NODE" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

res() { # PASS|FAIL name
  RESULTS="$RESULTS$1  $2
"
  [ "$1" = PASS ] || FAILED=1
  printf '%s  %s\n' "$1" "$2"
}
check() { # check NAME CMD...: PASS when CMD exits 0
  local name=$1; shift
  if "$@"; then res PASS "$name"; else res FAIL "$name"; fi
}
on() { local m=$1; shift; docker exec "$m" "$@"; }

if [ -n "${E2E_BUNDLE:-}" ]; then
  BUNDLE=$(cd "$E2E_BUNDLE" && pwd)
  echo "== using the bundle $BUNDLE"
else
  echo "== deploy/bundle.sh --arch $ARCH (onemindd, gateway runtime, dashboard, k3s + airgap images, NATS)"
  BUNDLE=$WORK/bundle
  "$REPO/deploy/bundle.sh" --arch "$ARCH" --go docker --out "$BUNDLE" > "$WORK/bundle.log" 2>&1 \
    || { tail -40 "$WORK/bundle.log"; exit 1; }
fi

echo "== the Debian 13 machine image"
docker build -q -t onemind/e2e-debian13:test -f "$HERE/Dockerfile.debian13" "$HERE" >/dev/null
docker rm -f "$HUB" "$NODE" >/dev/null 2>&1 || true
docker network rm "$NET" >/dev/null 2>&1 || true
docker network create "$NET" >/dev/null

boot() { # boot NAME: start the machine and copy the bundle (and nothing else) onto it
  # Each machine gets its own machine-id, so hub and node get different node ids (a VM cloned from
  # a snapshot keeps its twin's id: deploy/README.md). /lib/modules: k3s loads br_netfilter & co.
  python3 -I -c 'import uuid; print(uuid.uuid4().hex)' > "$WORK/$1.machine-id"
  docker run -d --name "$1" --hostname "$1" --network "$NET" --privileged --cgroupns=private \
    -v "$WORK/$1.machine-id:/etc/machine-id:ro" -v /lib/modules:/lib/modules:ro \
    --tmpfs /run --tmpfs /run/lock onemind/e2e-debian13:test >/dev/null
  on "$1" mkdir -p /root/bundle
  COPYFILE_DISABLE=1 tar -C "$BUNDLE" -cf - . | docker exec -i "$1" tar -C /root/bundle -xf -
  local st=""
  for _ in $(seq 1 60); do
    st=$(on "$1" systemctl is-system-running 2>/dev/null || true)
    case "$st" in running|degraded) return 0 ;; esac
    sleep 1
  done
  echo "systemd did not come up in $1 ($st)" >&2
  return 1
}
INSTALL=/root/bundle/src/deploy/install.sh
VERIFY_DIR=/root/bundle/src/deploy/verify

echo "== hub"
boot "$HUB"
if on "$HUB" "$INSTALL" --role hub --with-agent-token > "$WORK/hub.log" 2>&1; then res PASS "hub install from the bundle exits 0"
else
  res FAIL "hub install from the bundle exits 0"; tail -40 "$WORK/hub.log"
  # What the failing units said (the install only prints which one did not start).
  for u in onemind-headscale tailscaled onemind-nats k3s; do
    echo "--- journalctl -u $u"; on "$HUB" journalctl -u "$u" --no-pager -n 25 2>&1 || true
  done
fi
check "banner: unsupported developer install, no OS rollback" grep -q 'unsupported developer install, no OS rollback' "$WORK/hub.log"
check "bundle checked against SHA256SUMS, k3s images from the bundle" \
  sh -c "grep -q 'bundle: ok' '$WORK/hub.log' && grep -q 'from the bundle: k3s-airgap-images' '$WORK/hub.log'"
OWNER=$(sed -n '/^OWNER TOKEN/{n;n;p;}' "$WORK/hub.log" | tr -d ' ')
AGENT=$(sed -n '/^AGENT TOKEN/{n;n;p;}' "$WORK/hub.log" | tr -d ' ')
if printf '%s' "$OWNER" | grep -Eqx '[0-9a-f]{64}' && printf '%s' "$AGENT" | grep -Eqx '[0-9a-f]{64}'; then
  res PASS "owner and agent tokens printed once"
else
  res FAIL "owner and agent tokens printed once"
fi
# Only hashes may be on disk. k3s's own data (images, etcd) is left out of the search.
check "no raw API token on the hub's disk (only sha256 in tokens.yaml)" \
  sh -c "! docker exec $HUB grep -rlsF -e '$OWNER' -e '$AGENT' /etc /opt /root /tmp /var --exclude-dir=rancher --exclude-dir=containerd --exclude-dir=kubelet"
on "$HUB" sh -c "umask 077; printf '%s' '$OWNER' > /root/owner.token; printf '%s' '$AGENT' > /root/agent.token"

echo "== hub again (idempotency)"
if on "$HUB" "$INSTALL" --role hub --with-agent-token > "$WORK/hub2.log" 2>&1; then res PASS "second hub install exits 0"
else res FAIL "second hub install exits 0"; tail -30 "$WORK/hub2.log"; fi
check "second run keeps both tokens and prints none" \
  sh -c "grep -q 'owner token kept' '$WORK/hub2.log' && grep -q 'agent principal exists, kept' '$WORK/hub2.log' && ! grep -q 'TOKEN (shown once' '$WORK/hub2.log'"

echo "== node (owner-approved join over the mesh)"
boot "$NODE"
# The hub mints a one-time join code; the node installer shows a match code and waits; the owner
# approves on the hub (the same flow test/net/two_vm.py checks on real VMs).
TICKET=$(on "$HUB" sh -c "ONEMIND_TOKEN=\$(cat /root/owner.token) onemind fabric ticket --json")
PAYLOAD=$(printf '%s' "$TICKET" | python3 -I -c 'import json,sys; t=sys.stdin.read(); print(json.loads(t[t.index("{"):])["qr_payload"])')
HUB_IP=$(docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$HUB")
docker exec -d "$NODE" sh -c "$INSTALL --role node --join '$PAYLOAD' --hub-addr $HUB_IP > /tmp/node-install.log 2>&1; echo exit=\$? >> /tmp/node-install.log"
APPROVED=0
for _ in $(seq 1 120); do
  if on "$NODE" grep -q 'Waiting for the owner' /tmp/node-install.log 2>/dev/null; then
    ACTION=$(on "$HUB" python3 -I -c '
import json, urllib.request
tok = open("/root/owner.token").read().strip()
rq = urllib.request.Request("http://127.0.0.1:8080/v1/fabric", headers={"Authorization": "Bearer " + tok})
j = json.load(urllib.request.urlopen(rq, timeout=10))
print((j.get("joining") or [{}])[0].get("action_id", ""))' 2>/dev/null || true)
    if [ -n "$ACTION" ]; then
      on "$HUB" sh -c "ONEMIND_TOKEN=\$(cat /root/owner.token) onemind fabric approve $ACTION" >/dev/null 2>&1 && APPROVED=1
      break
    fi
  fi
  sleep 3
done
NODE_EXIT=""
for _ in $(seq 1 300); do
  NODE_EXIT=$(on "$NODE" sed -n 's/^exit=//p' /tmp/node-install.log 2>/dev/null || true)
  [ -n "$NODE_EXIT" ] && break
  sleep 3
done
if [ "$APPROVED" = 1 ] && [ "$NODE_EXIT" = 0 ]; then res PASS "node install from the bundle (join code, owner approval) exits 0"
else res FAIL "node install from the bundle (join code, owner approval) exits 0 (approved=$APPROVED exit=$NODE_EXIT)"; on "$NODE" tail -40 /tmp/node-install.log || true; fi

echo "== checks"
READY=0
for _ in $(seq 1 60); do
  READY=$(on "$HUB" k3s kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready"' | wc -l | tr -d ' ')
  [ "$READY" -ge 2 ] && break
  sleep 3
done
check "2 k3s nodes Ready (got $READY)" [ "$READY" -ge 2 ]
check "2 onemindd heartbeats on the hub's NATS" \
  on "$HUB" python3 -I "$VERIFY_DIR/natscheck.py" watch --env-file /etc/onemind/onemindd.env --count 2 --timeout 40
ONLINE=0
for _ in $(seq 1 15); do
  ONLINE=$(on "$HUB" python3 -I -c '
import json, urllib.request
tok = open("/root/owner.token").read().strip()
rq = urllib.request.Request("http://127.0.0.1:8080/v1/nodes", headers={"Authorization": "Bearer " + tok})
print(sum(1 for n in json.load(urllib.request.urlopen(rq, timeout=10)) if n.get("status") == "online"))' 2>/dev/null || echo 0)
  [ "$ONLINE" -ge 2 ] && break
  sleep 2
done
check "the gateway lists 2 online machines (got $ONLINE)" [ "$ONLINE" -ge 2 ]
if on "$HUB" "$VERIFY_DIR/node-check.sh" > "$WORK/nc-hub.log" 2>&1; then res PASS "node-check.sh on the hub"
else res FAIL "node-check.sh on the hub"; cat "$WORK/nc-hub.log"; fi
if on "$NODE" "$VERIFY_DIR/node-check.sh" > "$WORK/nc-node.log" 2>&1; then res PASS "node-check.sh on the node"
else res FAIL "node-check.sh on the node"; cat "$WORK/nc-node.log"; fi

if on "$HUB" "$VERIFY_DIR/verify.sh" http://127.0.0.1:8080 --token-file /root/owner.token \
     --agent-token-file /root/agent.token --audit-file /var/lib/onemind/audit.jsonl --app "$APP" \
     > "$WORK/verify.log" 2>&1; then
  res PASS "verify.sh on the hub ($(grep '^Summary' "$WORK/verify.log"))"
else
  res FAIL "verify.sh on the hub"; grep -E '^(FAIL|Summary)' "$WORK/verify.log" || tail -20 "$WORK/verify.log"
fi
# verify.sh removes its app at the end (its --keep clashes with the agent MCP check), so install it
# once more the way the owner does: request app.install, approve it, then wait for k3s.
check "owner requests and approves app.install of $APP -> succeeded" on "$HUB" python3 -I -c '
import datetime, json, sys, urllib.request, uuid
app, tok = sys.argv[1], open("/root/owner.token").read().strip()
def call(path, body=None):
    rq = urllib.request.Request("http://127.0.0.1:8080" + path, method="POST", data=json.dumps(body or {}).encode(),
                                headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(rq, timeout=420))
exp = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
a = call("/v1/actions", {"type": "app.install", "params": {"app_id": app}, "idempotency_key": "e2e-" + uuid.uuid4().hex, "expires_at": exp})
sys.exit(0 if call("/v1/actions/%s/approve" % a["id"]).get("state") == "succeeded" else 1)' "$APP"
check "$APP becomes Available in k3s" \
  on "$HUB" k3s kubectl -n "app-$APP" wait --for=condition=Available "deploy/$APP" --timeout=300s

echo "== dry run and uninstall"
SUM_BEFORE=$(on "$HUB" sh -c 'find /etc/onemind /etc/systemd/system /opt/onemind -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum')
check "--dry-run on the installed hub exits 0" sh -c "docker exec $HUB $INSTALL --role hub --dry-run > '$WORK/dry.log' 2>&1"
SUM_AFTER=$(on "$HUB" sh -c 'find /etc/onemind /etc/systemd/system /opt/onemind -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum')
check "--dry-run changed no file" [ "$SUM_BEFORE" = "$SUM_AFTER" ]
check "node --uninstall --purge exits 0" sh -c "docker exec $NODE $INSTALL --uninstall --purge > '$WORK/uninstall.log' 2>&1"
check "nothing of OneMind or k3s left on the node" \
  on "$NODE" sh -c '! systemctl list-unit-files --no-legend "k3s*" "onemind*" | grep -q . && [ ! -e /usr/local/bin/k3s ] && [ ! -e /etc/onemind ] && [ ! -e /var/lib/onemind ]'

echo
echo "== summary"
printf '%s' "$RESULTS"
if [ "$FAILED" = 0 ]; then echo "E2E PASSED"; else echo "E2E FAILED (KEEP=1 keeps $HUB and $NODE for docker exec)"; fi
exit "$FAILED"
