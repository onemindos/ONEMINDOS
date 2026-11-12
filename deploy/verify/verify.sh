#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Scripted pass/fail check of a OneMind hub against contract section 3
# (sdk/contracts/poc-v0.md). Works against the Mac compose hub and real hubs.
#
#   ./deploy/verify/verify.sh <hub-url> <owner-token> [agent-token]
#   ./deploy/verify/verify.sh http://localhost:8080 "$(cat deploy/compose/.secrets/owner.token)" "$(cat deploy/compose/.secrets/agent.token)"
#
# Environment:
#   VERIFY_AGENT_TOKEN  agent token, if not given as the 3rd argument
#   VERIFY_APP_ID       app to install (default: uptime-kuma if it is not installed,
#                       else the first app that is not installed)
#   VERIFY_TIMEOUT      seconds to wait for an approved action to finish (default 180)
#   VERIFY_KEEP=1       leave the test app installed. By default it is removed again
#                       through an approved app.remove, so the hub is left as found.
#
# Exit status: 0 all checks passed; 1 a check failed; 2 usage error;
# 3 nothing failed but a check was skipped (for example no agent token given).
# Needs: bash, curl, python3 (standard library only).
set -euo pipefail

usage() { sed -n '3,19p' "$0" | sed 's/^# \{0,1\}//'; }
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then usage; exit 0; fi
[ $# -ge 2 ] || { usage >&2; exit 2; }

HUB="${1%/}"
OWNER="$2"
AGENT="${3:-${VERIFY_AGENT_TOKEN:-}}"
TIMEOUT="${VERIFY_TIMEOUT:-180}"
command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
RESULTS="$WORK/results"
: > "$RESULTS"
PASS=0 FAIL=0 SKIP=0

record() { # status name detail
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$RESULTS"
  case "$1" in PASS) PASS=$((PASS + 1)) ;; FAIL) FAIL=$((FAIL + 1)) ;; SKIP) SKIP=$((SKIP + 1)) ;; esac
  printf '  %-4s %s\n' "$1" "$2"
}

# req METHOD PATH TOKEN [JSON-BODY] -> sets CODE, body in $WORK/body
CODE=""
req() {
  local method="$1" path="$2" token="$3" body="${4:-}"
  local args=(-sS -o "$WORK/body" -w '%{http_code}' -X "$method" --max-time 60)
  [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
  if [ -n "$body" ]; then args+=(-H 'Content-Type: application/json' --data "$body"); fi
  CODE="$(curl "${args[@]}" "$HUB$path" 2>"$WORK/curl.err" || true)"
  [ -n "$CODE" ] || CODE="000"
}

# js 'python expression over d' -> prints result; d is the parsed body (None if not JSON)
js() {
  python3 -I -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = None
try:
    # d goes in globals so generator expressions can see it
    v = eval(sys.argv[2], {"__builtins__": {"len": len, "isinstance": isinstance, "dict": dict, "list": list, "str": str, "all": all, "any": any, "set": set, "sorted": sorted, "next": next}, "d": d})
except Exception as e:
    v = "<error: %s>" % e
print(v if not isinstance(v, (dict, list)) else json.dumps(v))
' "$WORK/body" "$1"
}

# The action's lifecycle field (contract section 3, "Action states"). core/ names it "state".
STATE='(d.get("state") or d.get("status")) if isinstance(d, dict) else None'
ERR='d.get("error") if isinstance(d, dict) else None'

now_plus() { python3 -I -c 'import sys,datetime; print((datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=int(sys.argv[1]))).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$1"; }
rand() { python3 -I -c 'import secrets; print(secrets.token_hex(8))'; }

create_action() { # token type app_id key expires_in_s -> sets CODE, body
  local body
  body="$(printf '{"type":"%s","params":{"app_id":"%s"},"idempotency_key":"%s","expires_at":"%s"}' "$2" "$3" "$4" "$(now_plus "$5")")"
  req POST /v1/actions "$1" "$body"
}

wait_final() { # id -> echoes final state
  local id="$1" st="" deadline=$((SECONDS + TIMEOUT))
  while [ $SECONDS -lt $deadline ]; do
    req GET "/v1/actions/$id" "$OWNER"
    st="$(js "$STATE")"
    case "$st" in succeeded|failed|outcome_unknown|expired|cancelled) echo "$st"; return 0 ;; esac
    sleep 2
  done
  echo "${st:-timeout}"
}

echo "OneMind hub verification: $HUB"
echo

# 1. health
req GET /healthz ""
if [ "$CODE" = 200 ] && [ "$(js 'd.get("ok") is True if isinstance(d, dict) else False')" = True ]; then
  record PASS "GET /healthz is open and ok" "200 {ok: true}"
else
  record FAIL "GET /healthz is open and ok" "HTTP $CODE"
fi

# 2. auth required
req GET /v1/instance ""
if [ "$CODE" = 401 ] && [ "$(js "$ERR")" = unauthenticated ]; then
  record PASS "no token -> 401 unauthenticated" "401"
else
  record FAIL "no token -> 401 unauthenticated" "HTTP $CODE $(js 'd')"
fi
req GET /v1/instance "not-a-real-token-$(rand)"
if [ "$CODE" = 401 ]; then record PASS "unknown token -> 401" "401"; else record FAIL "unknown token -> 401" "HTTP $CODE"; fi

# 3. instance
HUB_NODE_ID=""
req GET /v1/instance "$OWNER"
if [ "$CODE" = 200 ] && [ "$(js 'all(k in d for k in ("name","version","hub_node_id")) if isinstance(d, dict) else False')" = True ]; then
  record PASS "GET /v1/instance" "$(js 'd["name"] + " " + str(d["version"]) + ", hub " + str(d["hub_node_id"])')"
  HUB_NODE_ID="$(js 'd["hub_node_id"]')"
else
  record FAIL "GET /v1/instance" "HTTP $CODE $(js 'd')"
fi

# 4. nodes
req GET /v1/nodes "$OWNER"
if [ "$CODE" = 200 ] && [ "$(js 'isinstance(d, list)')" = True ]; then
  online="$(js 'len([n for n in d if isinstance(n, dict) and n.get("status") == "online"])')"
  total="$(js 'len(d)')"
  if [ "$online" -ge 1 ] 2>/dev/null; then
    record PASS "GET /v1/nodes has >= 1 online node" "$online online of $total: $(js '", ".join(str(n.get("hostname")) + "/" + str(n.get("board")) for n in d)')"
  else
    record FAIL "GET /v1/nodes has >= 1 online node" "$online online of $total"
  fi
  shape="$(js 'all(isinstance(n, dict) and n.get("schema") == "onemind.node.status/v1" and n.get("status") in ("online","stale","offline") and "last_seen" in n and isinstance(n.get("node_id"), str) and len(n["node_id"]) == 12 for n in d)')"
  if [ "$shape" = True ]; then record PASS "node objects match contract section 2" "schema, status, last_seen, 12-hex node_id"; else record FAIL "node objects match contract section 2" "a node is missing schema/status/last_seen or has a bad node_id"; fi
  leak="$(js 'sorted(set(k for n in d if isinstance(n, dict) for k in n if any(w in k.lower() for w in ("serial","mac_addr","macaddr","ip_addr","ipaddr","address","username","user_name"))))')"
  if [ "$leak" = "[]" ]; then record PASS "nodes carry no serial/MAC/IP/user fields" ""; else record FAIL "nodes carry no serial/MAC/IP/user fields" "$leak"; fi
  if [ -n "$HUB_NODE_ID" ]; then
    hubst="$(js "next((n.get(\"status\") for n in d if n.get(\"node_id\") == \"$HUB_NODE_ID\"), \"missing\")")"
    if [ "$hubst" = online ]; then
      record PASS "the hub's own node (hub_node_id) is online" "$HUB_NODE_ID"
    else
      record FAIL "the hub's own node (hub_node_id) is online" "$HUB_NODE_ID is $hubst (is onemindd running on the hub, with the same node id?)"
    fi
  fi
  NODE_ID="$(js 'd[0]["node_id"] if d else ""')"
  if [ -n "$NODE_ID" ]; then
    req GET "/v1/nodes/$NODE_ID" "$OWNER"
    if [ "$CODE" = 200 ]; then record PASS "GET /v1/nodes/{id}" "$NODE_ID"; else record FAIL "GET /v1/nodes/{id}" "HTTP $CODE"; fi
  fi
  req GET "/v1/nodes/000000000000" "$OWNER"
  if [ "$CODE" = 404 ]; then record PASS "GET /v1/nodes/{unknown} -> 404" ""; else record FAIL "GET /v1/nodes/{unknown} -> 404" "HTTP $CODE"; fi
else
  record FAIL "GET /v1/nodes" "HTTP $CODE"
fi

# 5. apps
APP_ID=""
req GET /v1/apps "$OWNER"
if [ "$CODE" = 200 ] && [ "$(js 'isinstance(d, list) and len(d) > 0')" = True ]; then
  bad="$(js '[a.get("id") for a in d if not all(k in a for k in ("id","name","version","description","category","icon","license","source","archs","requires","web_port","installed","status"))]')"
  if [ "$bad" = "[]" ]; then
    record PASS "GET /v1/apps catalog entries are complete" "$(js 'len(d)') app(s): $(js '",".join(a["id"] for a in d)')"
  else
    record FAIL "GET /v1/apps catalog entries are complete" "incomplete: $bad"
  fi
  want="${VERIFY_APP_ID:-uptime-kuma}"
  APP_ID="$(js "next((a[\"id\"] for a in d if a.get(\"id\") == \"$want\" and not a.get(\"installed\")), next((a[\"id\"] for a in d if not a.get(\"installed\")), \"\"))")"
  if [ -n "${VERIFY_APP_ID:-}" ] && [ "$APP_ID" != "$VERIFY_APP_ID" ]; then
    record FAIL "VERIFY_APP_ID is in the catalog and not installed" "$VERIFY_APP_ID"
    APP_ID=""
  fi
else
  record FAIL "GET /v1/apps returns a non-empty catalog" "HTTP $CODE"
fi

if [ -z "$APP_ID" ]; then
  record FAIL "actions flow" "no app that is not installed yet (remove one, or set VERIFY_APP_ID)"
else
  # 6. owner requests an install -> awaiting_approval
  KEY="verify-$(rand)"
  create_action "$OWNER" app.install "$APP_ID" "$KEY" 600
  ACTION_ID="$(js 'd.get("id") if isinstance(d, dict) else ""')"
  if [ "$CODE" = 201 ] && [ "$(js "$STATE")" = awaiting_approval ]; then
    record PASS "POST /v1/actions app.install -> 201 awaiting_approval" "$APP_ID, action $ACTION_ID"
  else
    record FAIL "POST /v1/actions app.install -> 201 awaiting_approval" "HTTP $CODE $(js 'd')"
  fi

  # 7. idempotency
  create_action "$OWNER" app.install "$APP_ID" "$KEY" 600
  if [ "$CODE" = 200 ] && [ "$(js 'd.get("id") if isinstance(d, dict) else None')" = "$ACTION_ID" ]; then
    record PASS "same idempotency_key -> 200 same action" ""
  else
    record FAIL "same idempotency_key -> 200 same action" "HTTP $CODE id $(js 'd.get("id") if isinstance(d, dict) else d')"
  fi

  # 8. the agent can request but never approve (AI never actuates without a human)
  if [ -n "$AGENT" ]; then
    req POST "/v1/actions/$ACTION_ID/approve" "$AGENT"
    if [ "$CODE" = 403 ] && [ "$(js "$ERR")" = permission_denied ]; then
      record PASS "agent approve -> 403 permission_denied" ""
    else
      record FAIL "agent approve -> 403 permission_denied" "HTTP $CODE $(js 'd')"
    fi
    req GET "/v1/actions/$ACTION_ID" "$OWNER"
    if [ "$(js "$STATE")" = awaiting_approval ]; then record PASS "action still awaiting_approval after agent tried" ""; else record FAIL "action still awaiting_approval after agent tried" "state $(js "$STATE")"; fi
    create_action "$AGENT" app.install "$APP_ID" "verify-agent-$(rand)" 600
    AGENT_ACTION="$(js 'd.get("id") if isinstance(d, dict) else ""')"
    if [ "$CODE" = 201 ] && [ "$(js "$STATE")" = awaiting_approval ]; then
      record PASS "agent may request an action (awaiting_approval)" "$AGENT_ACTION by $(js 'd.get("requested_by", {}).get("kind")')"
      req POST "/v1/actions/$AGENT_ACTION/deny" "$AGENT"
      if [ "$CODE" = 403 ]; then record PASS "agent deny -> 403" ""; else record FAIL "agent deny -> 403" "HTTP $CODE"; fi
      req POST "/v1/actions/$AGENT_ACTION/deny" "$OWNER"
      if [ "$CODE" = 200 ] && [ "$(js "$STATE")" = cancelled ]; then
        record PASS "owner deny -> cancelled" ""
      else
        record FAIL "owner deny -> cancelled" "HTTP $CODE $(js 'd')"
      fi
    else
      record FAIL "agent may request an action (awaiting_approval)" "HTTP $CODE $(js 'd')"
    fi
  else
    record SKIP "agent approve -> 403 permission_denied" "no agent token given (3rd argument or VERIFY_AGENT_TOKEN)"
  fi

  # 9. expired actions cannot be approved (done before the install, so the app is still absent)
  create_action "$OWNER" app.install "$APP_ID" "verify-exp-$(rand)" 3
  EXP_ID="$(js 'd.get("id") if isinstance(d, dict) else ""')"
  if [ "$CODE" = 201 ] && [ -n "$EXP_ID" ]; then
    sleep 5
    req POST "/v1/actions/$EXP_ID/approve" "$OWNER"
    if [ "$CODE" = 409 ] && [ "$(js "$ERR")" = expired ]; then
      record PASS "approve after expires_at -> 409 expired" ""
    else
      record FAIL "approve after expires_at -> 409 expired" "HTTP $CODE $(js 'd')"
    fi
  else
    record FAIL "approve after expires_at -> 409 expired" "could not create the action (HTTP $CODE $(js 'd'))"
  fi

  # 10. owner approves -> succeeded (noop executor: marked done; kubernetes: kubectl apply -k)
  req POST "/v1/actions/$ACTION_ID/approve" "$OWNER"
  if [ "$CODE" = 200 ] || [ "$CODE" = 202 ]; then
    final="$(wait_final "$ACTION_ID")"
    if [ "$final" = succeeded ]; then
      record PASS "owner approve -> succeeded" "$APP_ID"
    else
      record FAIL "owner approve -> succeeded" "final state: $final $(js 'd.get("result") if isinstance(d, dict) else ""')"
    fi
  else
    record FAIL "owner approve -> succeeded" "approve returned HTTP $CODE $(js 'd')"
  fi
  req GET /v1/apps "$OWNER"
  inst="$(js "[a.get(\"installed\") for a in d if a.get(\"id\") == \"$APP_ID\"]")"
  if [ "$inst" = "[True]" ] || [ "$inst" = "[true]" ]; then record PASS "catalog shows $APP_ID installed" ""; else record FAIL "catalog shows $APP_ID installed" "installed=$inst"; fi

  # 11. a second install of an installed app is refused (stale precondition)
  create_action "$OWNER" app.install "$APP_ID" "verify-dup-$(rand)" 600
  if [ "$CODE" = 409 ] && [ "$(js "$ERR")" = stale_precondition ]; then
    record PASS "install of an installed app -> 409 stale_precondition" ""
  else
    record FAIL "install of an installed app -> 409 stale_precondition" "HTTP $CODE $(js 'd')"
  fi

  req GET /v1/actions "$OWNER"
  if [ "$CODE" = 200 ] && [ "$(js 'isinstance(d, list)')" = True ]; then record PASS "GET /v1/actions lists actions" "$(js 'len(d)') action(s)"; else record FAIL "GET /v1/actions lists actions" "HTTP $CODE"; fi
  req GET "/v1/actions/does-not-exist-$(rand)" "$OWNER"
  if [ "$CODE" = 404 ]; then record PASS "GET /v1/actions/{unknown} -> 404" ""; else record FAIL "GET /v1/actions/{unknown} -> 404" "HTTP $CODE"; fi

  # 12. leave the hub as found
  if [ "${VERIFY_KEEP:-0}" != 1 ]; then
    create_action "$OWNER" app.remove "$APP_ID" "verify-rm-$(rand)" 600
    RM_ID="$(js 'd.get("id") if isinstance(d, dict) else ""')"
    req POST "/v1/actions/$RM_ID/approve" "$OWNER"
    final="$(wait_final "$RM_ID")"
    if [ "$final" = succeeded ]; then record PASS "cleanup: app.remove -> succeeded" "$APP_ID"; else record FAIL "cleanup: app.remove -> succeeded" "$final"; fi
  fi
fi

# 13. OpenAPI and dashboard
req GET /openapi.json ""
if [ "$CODE" = 200 ] && [ "$(js 'isinstance(d, dict) and "paths" in d')" = True ]; then record PASS "GET /openapi.json" ""; else record FAIL "GET /openapi.json" "HTTP $CODE"; fi
req GET / ""
if [ "$CODE" = 200 ] && grep -qi '<html' "$WORK/body"; then record PASS "GET / serves the dashboard" ""; else record FAIL "GET / serves the dashboard" "HTTP $CODE (was the dashboard built and ONEMIND_DASHBOARD_DIST set?)"; fi

echo
printf '%-5s | %-55s | %s\n' RESULT CHECK DETAIL
printf '%s\n' "------+---------------------------------------------------------+------------------------------"
while IFS="$(printf '\t')" read -r st name detail; do
  printf '%-5s | %-55s | %s\n' "$st" "$name" "$detail"
done < "$RESULTS"
echo
echo "passed $PASS, failed $FAIL, skipped $SKIP"
[ "$FAIL" -eq 0 ] || exit 1
[ "$SKIP" -eq 0 ] || exit 3
exit 0
