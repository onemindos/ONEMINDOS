#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# res() always returns 0, so "A && res PASS || res FAIL" is safe; cleanup runs from the trap.
# shellcheck disable=SC2015,SC2329
#
# End-to-end test of deploy/install.sh on "stock Debian 13" machines simulated as
# systemd containers (Docker on the Mac is enough). Every OneMind part is the real one,
# built from this checkout by deploy/bundle.sh: onemindd (cmd/onemindd), the gateway
# image (core/Dockerfile) and the dashboard (dashboard/).
#
#   1. hub install (real apt, real k3s v1.37.2+k3s1 and NATS v2.15.2 downloads with
#      sha256 checks, systemd units, gateway image imported into k3s)
#   2. the same hub install again (idempotency)
#   3. a node joins with the printed join token (k3s agent + onemindd)
#   4. node-check.sh on both, 2 k3s nodes Ready, 2 heartbeats on NATS,
#      verify.sh against the hub with the kubernetes executor, so the approved
#      install really deploys a seed app (default ntfy) into k3s, and the app's pod
#      becomes Available
#
#   ./deploy/verify/tests/e2e-systemd/run.sh          # KEEP=1 leaves the containers running
#   E2E_APP=uptime-kuma ./deploy/verify/tests/e2e-systemd/run.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PFX=onemind-e2e
NET="$PFX-net"
HUB="$PFX-hub"
NODE="$PFX-node"
APP="${E2E_APP:-ntfy}"
WORK="$(mktemp -d)"
RESULTS=""
FAILED=0

case "$(docker info --format '{{.Architecture}}')" in
  aarch64|arm64) ARCH=arm64 ;;
  x86_64|amd64) ARCH=amd64 ;;
  *) echo "unsupported Docker architecture" >&2; exit 2 ;;
esac

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
check() { # name cmd...
  local name="$1"; shift
  if "$@"; then res PASS "$name"; else res FAIL "$name"; fi
}

echo "== build the bundle (real onemindd, gateway image, dashboard) for linux/$ARCH"
"$REPO/deploy/bundle.sh" --arch "$ARCH" > "$WORK/bundle.log" 2>&1 || { tail -30 "$WORK/bundle.log"; exit 1; }
BUNDLE="$REPO/out/bundle-$ARCH"

echo "== build the Debian 13 machine image"
docker build -q -t onemind/e2e-debian13:test -f "$HERE/Dockerfile.debian13" "$HERE" >/dev/null

docker rm -f "$HUB" "$NODE" >/dev/null 2>&1 || true
docker network rm "$NET" >/dev/null 2>&1 || true
docker network create "$NET" >/dev/null

boot() { # name
  # Each "machine" gets its own machine-id. Without this, systemd in every container derives
  # the same id from the Docker VM's DMI product UUID, and the hub and the node would share
  # one node_id (the same thing happens to cloned VMs: see deploy/README.md).
  python3 -I -c 'import uuid; print(uuid.uuid4().hex)' > "$WORK/$1.machine-id"
  docker run -d --name "$1" --hostname "$1" --network "$NET" --privileged --cgroupns=private \
    -v "$WORK/$1.machine-id:/etc/machine-id:ro" \
    --tmpfs /run --tmpfs /run/lock onemind/e2e-debian13:test >/dev/null
  docker exec "$1" mkdir -p /root/onemind /root/bundle
  COPYFILE_DISABLE=1 tar -C "$REPO" -cf - deploy apps sdk | docker exec -i "$1" tar --warning=no-unknown-keyword -C /root/onemind -xf -
  COPYFILE_DISABLE=1 tar -C "$BUNDLE" -cf - . | docker exec -i "$1" tar --warning=no-unknown-keyword -C /root/bundle -xf -
  for _ in $(seq 1 30); do
    st="$(docker exec "$1" systemctl is-system-running 2>/dev/null || true)"
    case "$st" in running|degraded) return 0 ;; esac
    sleep 1
  done
  echo "systemd did not come up in $1 ($st)" >&2
  return 1
}

echo "== boot hub"
boot "$HUB"

echo "== install hub"
HUB_ARGS=(--role hub --yes --bundle /root/bundle)
if docker exec "$HUB" /root/onemind/deploy/install.sh "${HUB_ARGS[@]}" > "$WORK/hub.log" 2>&1; then
  res PASS "hub install.sh exits 0"
else
  res FAIL "hub install.sh exits 0"; tail -40 "$WORK/hub.log"
fi
grep -q "UNSUPPORTED DEVELOPER INSTALL, NO OS ROLLBACK" "$WORK/hub.log" && res PASS "banner printed" || res FAIL "banner printed"
grep -q "sha256 ok" "$WORK/hub.log" && res PASS "downloads verified by sha256" || res FAIL "downloads verified by sha256"
JOIN="$(grep -o 'omj1\.[0-9a-f]*\.[^ ]*' "$WORK/hub.log" | head -1 || true)"
[ -n "$JOIN" ] && res PASS "join token printed" || res FAIL "join token printed"
OWNER="$(sed -n 's/^ *owner *: \([0-9a-f]\{64\}\).*/\1/p' "$WORK/hub.log" | head -1)"
AGENT="$(sed -n 's/^ *dev-agent *: \([0-9a-f]\{64\}\).*/\1/p' "$WORK/hub.log" | head -1)"
[ -n "$OWNER" ] && [ -n "$AGENT" ] && res PASS "owner and agent tokens printed once" || res FAIL "owner and agent tokens printed once"
check "tokens file stores hashes only (no raw token on disk)" \
  sh -c "! docker exec $HUB grep -rqs -e '$OWNER' -e '$AGENT' /etc/onemind /opt/onemind"

echo "== install hub again (idempotency)"
if docker exec "$HUB" /root/onemind/deploy/install.sh "${HUB_ARGS[@]}" > "$WORK/hub2.log" 2>&1; then
  res PASS "second hub install.sh exits 0"
else
  res FAIL "second hub install.sh exits 0"; tail -30 "$WORK/hub2.log"
fi
grep -q "already installed and running" "$WORK/hub2.log" && res PASS "second run skips k3s reinstall" || res FAIL "second run skips k3s reinstall"
grep -q "tokens.yaml exists" "$WORK/hub2.log" && res PASS "second run keeps existing tokens" || res FAIL "second run keeps existing tokens"

echo "== boot + install node"
boot "$NODE"
HUB_IP="$(docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$HUB")"
if docker exec "$NODE" /root/onemind/deploy/install.sh --role node --yes --hub "$HUB_IP" --token "$JOIN" --bundle /root/bundle > "$WORK/node.log" 2>&1; then
  res PASS "node install.sh exits 0"
else
  res FAIL "node install.sh exits 0"; tail -40 "$WORK/node.log"
fi

echo "== checks"
ready=0
for _ in $(seq 1 60); do
  ready="$(docker exec "$HUB" k3s kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready"' | wc -l | tr -d ' ')"
  [ "$ready" -ge 2 ] && break
  sleep 3
done
[ "$ready" -ge 2 ] && res PASS "2 k3s nodes Ready (hub + joined node)" || res FAIL "2 k3s nodes Ready (got $ready)"

NATS_URL="$(docker exec "$HUB" sed -n 's/^ONEMIND_NATS_URL=//p' /etc/onemind/onemindd.env)"
check "2 real onemindd heartbeats on hub NATS (onemind.node.*.status)" \
  docker exec "$HUB" python3 -I /root/onemind/deploy/verify/natscheck.py watch "$NATS_URL" --count 2 --timeout 40
check "NATS rejects a wrong token" \
  sh -c "! docker exec $HUB python3 -I /root/onemind/deploy/verify/natscheck.py ping nats://wrong@127.0.0.1:4222 >/dev/null 2>&1"

docker exec "$HUB" /root/onemind/deploy/verify/node-check.sh > "$WORK/nc-hub.log" 2>&1 && res PASS "node-check.sh on hub" || { res FAIL "node-check.sh on hub"; cat "$WORK/nc-hub.log"; }
docker exec "$NODE" /root/onemind/deploy/verify/node-check.sh > "$WORK/nc-node.log" 2>&1 && res PASS "node-check.sh on node" || { res FAIL "node-check.sh on node"; cat "$WORK/nc-node.log"; }

# Give the gateway one heartbeat round so both nodes are listed before verify runs.
sleep 12
docker exec -e VERIFY_TIMEOUT=300 -e VERIFY_APP_ID="$APP" -e VERIFY_KEEP=1 "$HUB" \
  /root/onemind/deploy/verify/verify.sh http://127.0.0.1:8080 "$OWNER" "$AGENT" > "$WORK/verify.log" 2>&1 \
  && res PASS "verify.sh against the installed hub (real gateway, kubernetes executor)" || res FAIL "verify.sh against the installed hub"
sed -n '/^RESULT/,$p' "$WORK/verify.log"

nodes="$(docker exec "$HUB" curl -fsS -H "Authorization: Bearer $OWNER" http://127.0.0.1:8080/v1/nodes | python3 -c 'import json,sys; print(sum(1 for n in json.load(sys.stdin) if n.get("status") == "online"))' 2>/dev/null || echo 0)"
[ "$nodes" -ge 2 ] && res PASS "gateway lists 2 online machines (hub + node)" || res FAIL "gateway lists 2 online machines (got $nodes)"

check "seed app $APP, installed through an approved action, becomes Available in k3s" \
  docker exec "$HUB" k3s kubectl -n "app-$APP" wait --for=condition=Available "deploy/$APP" --timeout=300s

echo
echo "== summary"
printf '%s' "$RESULTS"
if [ "$FAILED" -eq 0 ]; then echo "E2E PASSED"; else echo "E2E FAILED (logs: rerun with KEEP=1 and docker exec into $HUB / $NODE)"; fi
exit "$FAILED"
