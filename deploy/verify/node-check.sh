#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run ON a machine after deploy/install.sh to check that this node is healthy:
# onemindd (service + local API + heartbeat on NATS), k3s, and NATS connectivity.
#
#   sudo ./deploy/verify/node-check.sh                 # reads /etc/onemind/onemindd.env
#   sudo ./deploy/verify/node-check.sh --nats-url nats://<token>@hub:4222
#
# Exit status: 0 all checks passed (warnings allowed), 1 a check failed.
# Needs: bash, curl, python3 (standard library only), systemd.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NATSCHECK="$HERE/natscheck.py"
ENV_FILE=/etc/onemind/onemindd.env
K3S_VERSION="v1.37.2+k3s1"
NATS_URL="" ROLE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --nats-url) NATS_URL="${2:-}"; shift 2 ;;
    --role) ROLE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -r "$ENV_FILE" ]; then
  [ -n "$NATS_URL" ] || NATS_URL="$(sed -n 's/^ONEMIND_NATS_URL=//p' "$ENV_FILE")"
  [ -n "$ROLE" ] || ROLE="$(sed -n 's/^ONEMIND_NODE_ROLE=//p' "$ENV_FILE")"
elif [ -e "$ENV_FILE" ]; then
  echo "note: $ENV_FILE is root-only; run with sudo for the NATS checks" >&2
fi
ROLE="${ROLE:-node}"

PASS=0 FAIL=0 WARN=0
ROWS=""
row() { # status name detail
  ROWS="$ROWS$1	$2	$3
"
  case "$1" in PASS) PASS=$((PASS + 1)) ;; FAIL) FAIL=$((FAIL + 1)) ;; WARN) WARN=$((WARN + 1)) ;; esac
  printf '  %-4s %s\n' "$1" "$2"
}
active() { systemctl is-active --quiet "$1" 2>/dev/null; }

echo "OneMind node check (role: $ROLE)"
echo

# --- onemindd
if active onemindd; then row PASS "onemindd.service active" ""; else row FAIL "onemindd.service active" "systemctl status onemindd"; fi
NODE_JSON="$(curl -fsS --max-time 5 http://127.0.0.1:7480/api/v1/node 2>/dev/null || true)"
NODE_ID=""
if [ -n "$NODE_JSON" ]; then
  summary="$(printf '%s' "$NODE_JSON" | python3 -I -c '
import json, re, sys
d = json.load(sys.stdin)
ok = d.get("schema") == "onemind.node.status/v1" and re.fullmatch(r"[0-9a-f]{12}", d.get("node_id", "")) is not None
print(("ok" if ok else "bad"), d.get("node_id", ""), d.get("board", "?"), d.get("arch", "?"), d.get("role", "?"))
' 2>/dev/null || echo "bad")"
  read -r verdict nid board arch nrole <<EOF
$summary
EOF
  if [ "${verdict:-bad}" = ok ]; then
    NODE_ID="$nid"
    row PASS "onemindd API :7480/api/v1/node (contract section 2)" "node $nid, board $board, arch $arch, role $nrole"
    [ "${nrole:-}" = "$ROLE" ] || row WARN "onemindd reports the configured role" "reports ${nrole:-?}, env says $ROLE"
  else
    row FAIL "onemindd API :7480/api/v1/node (contract section 2)" "schema or node_id wrong"
  fi
else
  row FAIL "onemindd API :7480/api/v1/node (contract section 2)" "no answer on 127.0.0.1:7480"
fi

# --- k3s
if command -v k3s >/dev/null 2>&1; then
  v="$(k3s --version 2>/dev/null | head -1 | awk '{print $3}')"
  if [ "$v" = "$K3S_VERSION" ]; then row PASS "k3s binary $K3S_VERSION" ""; else row WARN "k3s binary $K3S_VERSION" "found ${v:-unknown}"; fi
else
  row FAIL "k3s binary present" "not installed"
fi
if [ "$ROLE" = hub ]; then
  if active k3s; then row PASS "k3s.service (server) active" ""; else row FAIL "k3s.service (server) active" "journalctl -u k3s"; fi
  if k3s kubectl get --raw /readyz >/dev/null 2>&1; then row PASS "k3s API /readyz" ""; else row FAIL "k3s API /readyz" "needs sudo, or k3s not ready"; fi
  nr="$(k3s kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready"' | wc -l | tr -d ' ')"
  nt="$(k3s kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${nr:-0}" -ge 1 ]; then row PASS "cluster nodes Ready" "$nr of $nt"; else row FAIL "cluster nodes Ready" "$nr of $nt"; fi
  if active onemind-nats; then row PASS "onemind-nats.service active" ""; else row FAIL "onemind-nats.service active" "systemctl status onemind-nats"; fi
  if curl -fsS --max-time 5 http://127.0.0.1:8080/healthz >/dev/null 2>&1; then row PASS "gateway :8080/healthz" ""; else row FAIL "gateway :8080/healthz" "k3s kubectl -n onemind-system get pods"; fi
else
  if active k3s-agent; then row PASS "k3s-agent.service active" ""; else row FAIL "k3s-agent.service active" "journalctl -u k3s-agent"; fi
fi

# --- NATS
if [ -z "$NATS_URL" ]; then
  row FAIL "NATS reachable" "no ONEMIND_NATS_URL (run with sudo, or pass --nats-url)"
else
  if out="$(python3 -I "$NATSCHECK" ping "$NATS_URL" 2>&1)"; then
    row PASS "NATS reachable and accepts our credentials" "${out#ok: }"
  else
    row FAIL "NATS reachable and accepts our credentials" "$out"
  fi
  if [ -n "$NODE_ID" ]; then
    if python3 -I "$NATSCHECK" watch "$NATS_URL" --subject "onemind.node.$NODE_ID.status" --count 1 --timeout 25 >/dev/null 2>&1; then
      row PASS "own heartbeat seen on onemind.node.$NODE_ID.status" "within 25 s"
    else
      row FAIL "own heartbeat seen on onemind.node.$NODE_ID.status" "none in 25 s (contract: every 10 s)"
    fi
  fi
fi

# --- clock (stale/offline status is computed from timestamps)
if command -v timedatectl >/dev/null 2>&1; then
  if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo no)" = yes ]; then
    row PASS "clock synchronised (NTP)" ""
  else
    row WARN "clock synchronised (NTP)" "unsynchronised clocks make nodes look stale"
  fi
fi

echo
printf '%-5s | %-52s | %s\n' RESULT CHECK DETAIL
printf '%s\n' "------+------------------------------------------------------+------------------------"
printf '%s' "$ROWS" | while IFS="$(printf '\t')" read -r st name detail; do
  [ -n "$st" ] && printf '%-5s | %-52s | %s\n' "$st" "$name" "$detail"
done
echo
echo "passed $PASS, failed $FAIL, warnings $WARN"
[ "$FAIL" -eq 0 ]
