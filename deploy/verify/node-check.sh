#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Run ON a machine after deploy/install.sh: is this hub or node healthy? Checks onemindd (service,
# local API, its own heartbeat on NATS), k3s, the hub's NATS and gateway services, and the NATS
# auth this machine actually has. Ported from PR #27, adapted to main (systemd gateway, NATS auth
# only inside ONEMIND_NATS_URL, optional H-06 leaf on loopback).
#
#   sudo deploy/verify/node-check.sh                       # reads /etc/onemind/onemindd.env
#   sudo deploy/verify/node-check.sh --env-file FILE       # another env file with ONEMIND_NATS_URL
#   sudo deploy/verify/node-check.sh --nats-url URL        # (a URL with credentials shows in ps)
#
# One PASS/FAIL/WARN/SKIP line per check, a table at the end. Exit 0 when nothing FAILed (WARN and
# SKIP are allowed). Needs bash, curl, python3 (standard library), systemd. Run as root: k3s's
# admin kubeconfig is root-only.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
NATSCHECK="$HERE/natscheck.py"
ENV_FILE=/etc/onemind/onemindd.env
NATS_URL="" ROLE=""
K3S_VERSION=""
# shellcheck source=deploy/pins.env
[ -r "$HERE/../pins.env" ] && . "$HERE/../pins.env"

while [ $# -gt 0 ]; do
  case "$1" in
    --env-file) ENV_FILE=${2:-}; shift 2 ;;
    --nats-url) NATS_URL=${2:-}; shift 2 ;;
    --role) ROLE=${2:-}; shift 2 ;;
    -h|--help) sed -n '4,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -r "$ENV_FILE" ]; then
  [ -n "$ROLE" ] || ROLE=$(sed -n 's/^ONEMIND_NODE_ROLE=//p' "$ENV_FILE" | tail -1)
elif [ -z "$NATS_URL" ]; then
  echo "note: $ENV_FILE is not readable; the NATS checks need it (or --nats-url)" >&2
fi
ROLE=${ROLE:-node}
case "$ROLE" in hub|node) ;; *) echo "role must be hub or node, got $ROLE" >&2; exit 2 ;; esac

PASS=0 FAIL=0 WARN=0 SKIP=0 ROWS=""
row() { # STATUS NAME [DETAIL]
  ROWS="$ROWS$1	$2	${3:-}
"
  case "$1" in PASS) PASS=$((PASS + 1)) ;; FAIL) FAIL=$((FAIL + 1)) ;; WARN) WARN=$((WARN + 1)) ;; SKIP) SKIP=$((SKIP + 1)) ;; esac
  printf '%-5s %s%s\n' "$1" "$2" "${3:+  ($3)}"
}
active() { systemctl is-active --quiet "$1" 2>/dev/null; }
unit_exists() { [ -n "$(systemctl list-unit-files --no-legend "$1.service" 2>/dev/null)" ]; }
svc() { if active "$1"; then row PASS "$1.service active"; else row FAIL "$1.service active" "journalctl -u $1"; fi; }
# natscheck reads the URL from the env file, so credentials never reach a command line.
nc() { local cmd=$1; shift
  if [ -n "$NATS_URL" ]; then python3 -I "$NATSCHECK" "$cmd" "$NATS_URL" "$@"
  else python3 -I "$NATSCHECK" "$cmd" --env-file "$ENV_FILE" "$@"; fi; }

echo "OneMind node check (role $ROLE)"

# ---- onemindd (contract §1, §2) ----
svc onemindd
NODE_ID=""
NODE_JSON=$(curl -fsS --max-time 5 http://127.0.0.1:7480/api/v1/node 2>/dev/null || true)
if [ -n "$NODE_JSON" ]; then
  SUMMARY=$(printf '%s' "$NODE_JSON" | python3 -I -c '
import json, re, sys
d = json.load(sys.stdin)
ok = d.get("schema") == "onemind.node.status/v1" and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(d.get("node_id", ""))) is not None
print("ok" if ok else "bad", d.get("node_id", "-") if ok else "-", d.get("board", "?"), d.get("arch", "?"), d.get("role", "?"))
' 2>/dev/null || echo "bad - ? ? ?")
  read -r VERDICT NID BOARD ARCH NROLE <<EOF
$SUMMARY
EOF
  if [ "$VERDICT" = ok ]; then
    NODE_ID=$NID
    row PASS "onemindd API :7480/api/v1/node (§2)" "node $NID, board $BOARD, arch $ARCH"
    if [ "$NROLE" = "$ROLE" ]; then row PASS "onemindd reports role $ROLE"; else row FAIL "onemindd reports role $ROLE" "it says $NROLE"; fi
  else
    row FAIL "onemindd API :7480/api/v1/node (§2)" "wrong schema or node_id"
  fi
else
  row FAIL "onemindd API :7480/api/v1/node (§2)" "no answer on 127.0.0.1:7480"
fi

# ---- k3s ----
if command -v k3s >/dev/null 2>&1; then
  V=$(k3s --version 2>/dev/null | awk 'NR==1{print $3}')
  if [ -z "$K3S_VERSION" ]; then row SKIP "k3s version" "found $V; no pins.env next to this script"
  elif [ "$V" = "$K3S_VERSION" ]; then row PASS "k3s $K3S_VERSION (pins.env)"
  else row WARN "k3s $K3S_VERSION (pins.env)" "found ${V:-unknown}"; fi
else
  row FAIL "k3s installed" "no k3s on PATH"
fi
if [ "$ROLE" = hub ]; then
  svc k3s
  if k3s kubectl get --raw /readyz >/dev/null 2>&1; then row PASS "k3s API /readyz"; else row FAIL "k3s API /readyz" "run as root, or k3s is not ready"; fi
  NR=$(k3s kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready"' | wc -l | tr -d ' ')
  NT=$(k3s kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
  if [ "${NR:-0}" -ge 1 ]; then row PASS "k3s nodes Ready" "$NR of $NT"; else row FAIL "k3s nodes Ready" "$NR of $NT"; fi
  svc onemind-nats
  svc onemind-gateway
  if curl -fsS --max-time 5 http://127.0.0.1:8080/healthz >/dev/null 2>&1; then row PASS "gateway :8080/healthz (§3)"
  else row FAIL "gateway :8080/healthz (§3)" "journalctl -u onemind-gateway"; fi
else
  svc k3s-agent
  # D-B6.2: a node joins as an agent and holds no cluster-admin kubeconfig.
  if [ -e /etc/rancher/k3s/k3s.yaml ] || [ -d /var/lib/rancher/k3s/server ]; then
    row FAIL "no k3s admin kubeconfig or server data on a node (D-B6.2)" "/etc/rancher/k3s/k3s.yaml or /var/lib/rancher/k3s/server exists"
  else
    row PASS "no k3s admin kubeconfig or server data on a node (D-B6.2)"
  fi
fi

# ---- NATS: the auth this machine has, and its own heartbeat ----
if [ -z "$NATS_URL" ] && ! [ -r "$ENV_FILE" ]; then
  row FAIL "NATS reachable" "no ONEMIND_NATS_URL ($ENV_FILE not readable; run with sudo)"
elif OUT=$(nc ping 2>&1); then
  row PASS "NATS answers with this machine's credentials" "${OUT#ok: }"
  case "$OUT" in
    *auth_required=False*) row WARN "NATS requires credentials" "no: anyone who reaches the port can publish (v0 shortcut until per-node users, H-06)" ;;
    *) row PASS "NATS requires credentials" ;;
  esac
  if [ -n "$NODE_ID" ]; then
    if nc watch --subject "onemind.node.$NODE_ID.status" --count 1 --timeout 25 >/dev/null 2>&1; then
      row PASS "own heartbeat on onemind.node.$NODE_ID.status (§1)" "within 25 s"
    else
      row FAIL "own heartbeat on onemind.node.$NODE_ID.status (§1)" "none in 25 s (onemindd sends one every 10 s)"
    fi
  fi
else
  row FAIL "NATS answers with this machine's credentials" "$(printf '%s' "$OUT" | tail -1)"
fi

# ---- H-06 leaf link (when this node runs a NATS leaf; NETWORKING §7) ----
if [ "$ROLE" = node ]; then
  if unit_exists onemind-nats-leaf; then
    svc onemind-nats-leaf
    if OUT=$(python3 -I "$NATSCHECK" leafz 2>&1); then row PASS "leaf link to the hub is up (/leafz)" "${OUT#ok: }"
    else row FAIL "leaf link to the hub is up (/leafz)" "$OUT"; fi
  else
    row SKIP "leaf link (H-06)" "no onemind-nats-leaf unit: this node publishes straight to the hub (v0)"
  fi
fi

# ---- clock (stale and offline are computed from timestamps) ----
if command -v timedatectl >/dev/null 2>&1; then
  if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ]; then row PASS "clock synchronised (NTP)"
  else row WARN "clock synchronised (NTP)" "an unsynchronised clock makes nodes look stale"; fi
fi

echo
printf '%-6s| %-60s| %s\n' RESULT CHECK DETAIL
printf '%s\n' '------+-------------------------------------------------------------+-----------------'
printf '%s' "$ROWS" | while IFS="$(printf '\t')" read -r st name detail; do
  [ -n "$st" ] && printf '%-6s| %-60s| %s\n' "$st" "$name" "$detail"
done
echo
echo "passed $PASS, failed $FAIL, warnings $WARN, skipped $SKIP"
[ "$FAIL" -eq 0 ]
