#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Scripted pass/fail check of the poc-v0 contract (sdk/contracts/poc-v0.md §6) against a running
# hub, over HTTP and NATS only. Needs bash, curl and python3 (stdlib). Works from a Mac or the hub.
#
#   deploy/verify/verify.sh <hub-url> --token-file <owner> [--agent-token-file <agent>] [options]
#
#   --token-file F     file holding the owner token (person/owner). Without a token only the open
#                      checks run. Or set ONEMIND_TOKEN. --token T also works, but then the token
#                      shows in `ps` and in shell history.
#   --agent-token-file F  an agent principal's token (or ONEMIND_AGENT_TOKEN, or --agent-token T):
#                      checks that an agent can request but never approve, and the §11.3 MCP tools.
#   --nats URL         hub NATS (default nats://<hub host>:4222); "none" skips the NATS checks.
#   --app ID           app used for the action flow (default ntfy).
#   --audit-file F     also verify the whole hash chain of the gateway's audit.jsonl (hub only).
#   --no-execute       deny the action instead of approving it (nothing is installed).
#   --keep             leave the app installed after the flow (default: remove it again).
#   --strict           treat SKIP (wave-2 features the gateway does not have yet) as FAIL.
#
# Output: one PASS/FAIL/SKIP line per contract item, then a summary. Exit 0 only if nothing failed.
# Tokens never reach a command line: curl reads the Authorization header from a 0600 file.
set -uo pipefail

HUB="" TOKEN=${ONEMIND_TOKEN:-} AGENT=${ONEMIND_AGENT_TOKEN:-} NATS="" APP=ntfy AUDIT_FILE="" EXECUTE=1 KEEP=0 STRICT=0
readtok() { [ -r "$1" ] || { echo "cannot read token file $1" >&2; exit 2; }; tr -d ' \t\r\n' < "$1"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --token) TOKEN=$2; shift 2 ;;
    --token-file) TOKEN=$(readtok "$2") || exit 2; shift 2 ;;
    --agent-token) AGENT=$2; shift 2 ;;
    --agent-token-file) AGENT=$(readtok "$2") || exit 2; shift 2 ;;
    --nats) NATS=$2; shift 2 ;;
    --app) APP=$2; shift 2 ;;
    --audit-file) AUDIT_FILE=$2; shift 2 ;;
    --no-execute) EXECUTE=0; shift ;;
    --keep) KEEP=1; shift ;;
    --strict) STRICT=1; shift ;;
    -h|--help) sed -n '4,23p' "$0"; exit 0 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) HUB=${1%/}; shift ;;
  esac
done
[ -n "$HUB" ] || { echo "usage: $0 <hub-url> --token-file <owner-token-file> [--agent-token-file F] ..." >&2; exit 2; }
for t in curl python3; do command -v "$t" >/dev/null || { echo "needs $t" >&2; exit 2; }; done
# APP goes into JSON bodies and URLs: allow only a §4/§11.5 app id.
printf '%s' "$APP" | grep -Eqx '[a-z0-9]([a-z0-9-]{0,57}[a-z0-9])?' || { echo "--app: not a valid app id: $APP" >&2; exit 2; }

HOST=${HUB#*://}; HOST=${HOST%%/*}; HOST=${HOST%:*}
[ -n "$NATS" ] || NATS="nats://$HOST:4222"
WORK=$(mktemp -d); NATS_PID=""
trap '[ -n "$NATS_PID" ] && kill "$NATS_PID" 2>/dev/null; rm -rf "$WORK"' EXIT
chmod 0700 "$WORK"
# One header file per token (curl -H @file), so no token appears in the process list.
hdr() { (umask 077; printf 'Authorization: Bearer %s\n' "$2" > "$WORK/$1.hdr"); }
hdr owner "$TOKEN"; hdr agent "$AGENT"; hdr bogus "not-a-real-token-0000000000000000"
(umask 077; printf '%s' "$AGENT" > "$WORK/agent.tok")
NP=0 NF=0 NS=0
pass() { NP=$((NP+1)); printf 'PASS  %s\n' "$*"; }
fail() { NF=$((NF+1)); printf 'FAIL  %s\n' "$*"; }
skip() { if [ "$STRICT" = 1 ]; then fail "$* (--strict)"; else NS=$((NS+1)); printf 'SKIP  %s\n' "$*"; fi; }
tally() { local l; while IFS= read -r l; do case "$l" in PASS*) pass "${l#PASS  }" ;; FAIL*) fail "${l#FAIL  }" ;; SKIP*) skip "${l#SKIP  }" ;; *) [ -n "$l" ] && echo "      $l" ;; esac; done < "$1"; }
on200() { # on200 EXPR LABEL [VALUE...]: the last response must be HTTP 200 and EXPR must hold
  if [ "$CODE" = 200 ]; then check "$(jpy "$1" "${@:3}")" "$2"; else fail "$2 -- HTTP $CODE $(head -c 300 "$WORK/body" 2>/dev/null)"; fi; }
check() { if [ "$1" = ok ]; then pass "$2"; else fail "$2 -- $1"; fi; }

# req METHOD PATH WHO [JSON]: WHO is owner, agent, bogus or "" (no token).
# Response body in $WORK/body, status in $CODE.
req() {
  local args=(-sS -o "$WORK/body" -w '%{http_code}' -X "$1" --max-time 420)
  [ -n "${3:-}" ] && args+=(-H "@$WORK/$3.hdr")
  [ -n "${4:-}" ] && args+=(-H 'Content-Type: application/json' --data "$4")
  CODE=$(curl "${args[@]}" "$HUB$2" 2>"$WORK/curl.err") || CODE=000
}
# jpy EXPR [VALUE...]: evaluate a Python expression over d = the last response body. Prints the
# result, or "ok" for True. Assertion-style expressions return "ok" or a reason string.
# Values from the hub or the command line are passed as v[0], v[1]..., NEVER pasted into EXPR:
# a hub-supplied id like  x' or __import__('os').system('...') or '  would otherwise run here.
jpy() { python3 -I -c '
import json, sys
try: d = json.load(open(sys.argv[1]))
except Exception as e: print("body is not JSON: %s" % e); sys.exit(0)
r = eval(sys.argv[2], {"d": d, "v": sys.argv[3:], "json": json})
print("ok" if r is True else ("false" if r is False else r))' "$WORK/body" "$@"; }
expect() { # expect CODE ERROR_OR_- LABEL
  if [ "$CODE" != "$1" ]; then fail "$3 -- HTTP $CODE, body: $(head -c 300 "$WORK/body" 2>/dev/null)"; return 1; fi
  if [ "$2" != - ]; then check "$(jpy "d.get('error') == v[0] or 'error=%r' % d.get('error')" "$2")" "$3"; else pass "$3"; fi
}
rfc3339() { python3 -I -c 'import datetime,sys; print((datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=int(sys.argv[1]))).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$1"; }
key() { printf 'verify-%s-%s' "$1" "$(python3 -I -c 'import uuid; print(uuid.uuid4().hex[:12])')"; }
action_body() { printf '{"type":"%s","params":{"app_id":"%s"},"idempotency_key":"%s","expires_at":"%s"}' "$1" "$APP" "$2" "$3"; }

echo "OneMind contract check (poc-v0) against $HUB"

# ---- NATS listener (started first, so it sees heartbeats and the audit lines of this run) ----
if [ "$NATS" != none ]; then
  python3 -I - "$NATS" "$WORK/nats.jsonl" > "$WORK/nats.log" 2>&1 <<'PY' &
import json, socket, sys, time
url, out = sys.argv[1], sys.argv[2]
hostport = url.split("://", 1)[-1].split("/")[0].split("@")[-1]
host, _, port = hostport.rpartition(":")
s = socket.create_connection((host.strip("[]"), int(port or 4222)), timeout=10)
f = s.makefile("rb")
info = f.readline()
with open(out, "a") as o:
    o.write(json.dumps({"info": info.decode().strip()[5:]}) + "\n"); o.flush()
    s.sendall(b'CONNECT {"verbose":false,"pedantic":false,"name":"onemind-verify","lang":"python"}\r\n'
              b"SUB onemind.node.*.status 1\r\nSUB onemind.audit 2\r\nPING\r\n")
    s.settimeout(None)
    deadline = time.time() + 900
    while time.time() < deadline:
        line = f.readline()
        if not line:
            break
        if line.startswith(b"PING"):
            s.sendall(b"PONG\r\n")
        elif line.startswith(b"MSG"):
            parts = line.split()
            size = int(parts[-1])
            payload = f.read(size + 2)[:size]
            o.write(json.dumps({"subject": parts[1].decode(), "sid": parts[2].decode(),
                                "payload": payload.decode("utf-8", "replace")}) + "\n"); o.flush()
PY
  NATS_PID=$!
fi

# ---- §3 open endpoints and authentication ----
req GET /healthz ""
on200 "d == {'ok': True} or d" "§3 GET /healthz is open and returns {\"ok\": true}"
req GET /openapi.json ""
on200 "'/v1/actions' in d.get('paths', {}) or 'no /v1/actions path'" "§3 OpenAPI published at /openapi.json"
req GET /v1/instance ""
expect 401 unauthenticated "§3 no token -> 401 unauthenticated"
req GET /v1/nodes bogus
expect 401 unauthenticated "§3 unknown token -> 401 unauthenticated"
req GET / ""
if [ "$CODE" = 200 ] && grep -qi '<html' "$WORK/body"; then pass "§3 dashboard served at /"; else fail "§3 dashboard at / -- HTTP $CODE"; fi
req GET /approvals ""
if [ "$CODE" = 200 ] && grep -qi '<html' "$WORK/body"; then pass "§3 SPA fallback (/approvals -> index.html)"; else fail "§3 SPA fallback -- HTTP $CODE"; fi

if [ -z "$TOKEN" ]; then
  skip "authenticated checks (no --token)"
else
  # ---- instance, nodes ----
  req GET /v1/instance owner
  on200 "all(k in d for k in ('name','version','hub_node_id')) or sorted(d)" "§3 GET /v1/instance has name, version, hub_node_id"
  HUB_ID=$(jpy "d.get('hub_node_id')")

  NODE_OK=""
  for _ in $(seq 1 15); do   # a fresh hub may need one heartbeat interval (10 s)
    req GET /v1/nodes owner
    [ "$CODE" = 200 ] && [ "$(jpy "isinstance(d, list) and len(d) > 0")" = ok ] && { NODE_OK=1; break; }
    sleep 2
  done
  if [ -n "$NODE_OK" ]; then
    pass "§3 GET /v1/nodes lists $(jpy "len(d)") node(s)"
    check "$(jpy "all(n.get('status') in ('online','stale','offline') and n.get('last_seen') for n in d) or [(n.get('node_id'), n.get('status'), n.get('last_seen')) for n in d]")" \
      "§3 every node has status online|stale|offline and last_seen"
    check "$(jpy "all(n.get('schema') == 'onemind.node.status/v1' and all(k in n for k in ('node_id','hostname','role','board','arch','os','k3s','rauc','gpu','observed_at')) for n in d) or 'missing §2 fields'")" \
      "§2 node objects carry the heartbeat fields"
    check "$(jpy "all(n.get('board') in ('x86_64-efi','arm64-efi','rpi5','jetson-orin','vm','vm-do','unknown') and n.get('secure_boot') in ('enabled','disabled','unsupported','unknown') for n in d) or [(n.get('board'), n.get('secure_boot')) for n in d]")" \
      "§2 board and secure_boot use the contract values"
    check "$(jpy "not any(k in json.dumps(d).lower() for k in ('\"mac\"', 'serial', '\"ip\"', 'username', 'machine_id')) or 'forbidden field present'")" \
      "§2 no MAC, serial, IP, user name or machine-id in node data"
    check "$(jpy "any(n['status'] == 'online' for n in d) or 'no node online'")" "§3 at least one node is online"
    if [ -n "$HUB_ID" ] && [ "$(jpy "any(n['node_id'] == v[0] for n in d)" "$HUB_ID")" = ok ]; then
      pass "§3 the hub's own onemindd ($HUB_ID) is in /v1/nodes"
    else
      skip "hub_node_id $HUB_ID has no heartbeat (normal for compose, where the hub runs no onemindd)"
    fi
    FIRST=$(jpy "d[0]['node_id']")
    if printf '%s' "$FIRST" | grep -Eqx '[A-Za-z0-9_-]{1,64}'; then   # §2/§1 subject-safe id
      req GET "/v1/nodes/$FIRST" owner
      on200 "d.get('node_id') == v[0] or d" "§3 GET /v1/nodes/{id} returns that node" "$FIRST"
    else
      fail "§3 first node id is not a valid node id: $(printf '%s' "$FIRST" | head -c 80)"
    fi
  else
    fail "§3 GET /v1/nodes returned no node within 30 s (HTTP $CODE)"
  fi
  req GET /v1/nodes/no-such-node-0 owner
  expect 404 not_found "§3 unknown node -> 404 not_found"

  # ---- apps catalog ----
  req GET /v1/apps owner
  if [ "$CODE" = 200 ] && [ "$(jpy "isinstance(d, list) and len(d) > 0")" = ok ]; then
    pass "§3 GET /v1/apps lists $(jpy "len(d)") app(s)"
    check "$(jpy "[a.get('id') for a in d if not all(k in a for k in ('id','name','version','description','category','icon','license','source','archs','requires','web_port','installed','status'))] == [] or 'missing fields in ' + str([a.get('id') for a in d if not all(k in a for k in ('id','name','version','description','category','icon','license','source','archs','requires','web_port','installed','status'))])")" \
      "§3 every catalog entry has the §3 fields"
    if [ "$(jpy "all(k in a for a in d for k in ('links','tier','scan'))")" = ok ]; then
      check "$(jpy "all(a['scan'] is None or ('scanned_at' in a['scan'] and 'result' in a['scan']) for a in d) or 'bad scan field'")" "§11.4 catalog entries carry links, tier and scan"
    else
      fail "§11.4 catalog entries lack links, tier or scan (the gateway must send them)"
    fi
    APP_STATUS=$(jpy "next((a['status'] for a in d if a['id'] == v[0]), 'absent')" "$APP")
  else
    fail "§3 GET /v1/apps -- HTTP $CODE"; APP_STATUS=absent
  fi

  # ---- actions ----
  if [ "$APP_STATUS" = absent ]; then
    fail "§3 action flow -- app '$APP' is not in the catalog (--app)"
  else
    if [ "$APP_STATUS" = installed ]; then   # start from a clean state
      K=$(key pre-remove); req POST /v1/actions owner "$(action_body app.remove "$K" "$(rfc3339 600)")"
      ID=$(jpy "d.get('id')"); req POST "/v1/actions/$ID/approve" owner
      echo "      ($APP was installed; removed first: $(jpy "d.get('state')"))"
    fi

    # expiry: approving after expires_at -> 409 expired
    K=$(key expiry); req POST /v1/actions owner "$(action_body app.install "$K" "$(rfc3339 2)")"
    if [ "$CODE" = 201 ]; then
      ID=$(jpy "d['id']"); sleep 4; req POST "/v1/actions/$ID/approve" owner
      expect 409 expired "§3 approving after expires_at -> 409 expired"
    else fail "§3 create short-lived action -- HTTP $CODE"; fi

    # deny: owner denies -> cancelled
    K=$(key deny); req POST /v1/actions owner "$(action_body app.install "$K" "$(rfc3339 600)")"
    if [ "$CODE" = 201 ]; then
      ID=$(jpy "d['id']"); req POST "/v1/actions/$ID/deny" owner
      on200 "d.get('state') == 'cancelled' or d.get('state')" "§3 owner deny -> cancelled"
    else fail "§3 create action to deny -- HTTP $CODE"; fi

    # main flow: requester is the agent when we have one (contract §7 demo shape), else the owner
    REQ_TOKEN=$([ -n "$AGENT" ] && echo agent || echo owner); WHO=$REQ_TOKEN
    K=$(key main); BODY=$(action_body app.install "$K" "$(rfc3339 900)")
    req POST /v1/actions "$REQ_TOKEN" "$BODY"
    if [ "$CODE" = 201 ] && [ "$(jpy "d.get('state') == 'awaiting_approval'")" = ok ]; then
      MAIN=$(jpy "d['id']"); printf '%s' "$MAIN" | grep -Eqx '[A-Za-z0-9_.:-]{1,128}' || MAIN=invalid-action-id; pass "§3 POST /v1/actions by $WHO -> 201 awaiting_approval ($MAIN)"
      [ -n "$AGENT" ] && check "$(jpy "d.get('requested_by', {}).get('kind') == 'agent' or d.get('requested_by')")" "§7 action records requester kind agent"
      req POST /v1/actions "$REQ_TOKEN" "$BODY"
      on200 "d.get('id') == v[0] or d.get('id')" "§3 same idempotency key -> 200, same action" "$MAIN"
      req GET "/v1/actions/$MAIN" owner
      on200 "d.get('params') == {'app_id': v[0]} or d.get('params')" "§3 GET /v1/actions/{id} shows the exact params" "$APP"
      req GET /v1/actions owner
      on200 "any(a['id'] == v[0] for a in d) or 'not listed'" "§3 GET /v1/actions lists it" "$MAIN"
      if [ -n "$AGENT" ]; then
        req POST "/v1/actions/$MAIN/approve" agent
        expect 403 permission_denied "§3 agent approve -> 403 permission_denied"
        req POST "/v1/actions/$MAIN/deny" agent
        expect 403 permission_denied "§3 agent deny -> 403 permission_denied"
      else
        skip "agent cannot approve (no agent token)"
      fi
      if [ "$EXECUTE" = 1 ]; then
        req POST "/v1/actions/$MAIN/approve" owner
        if [ "$CODE" = 409 ] && [ "$(jpy "d.get('error')")" = stale_precondition ]; then
          pass "§10.3/§11.1 approve of an unscanned app -> 409 stale_precondition ($(jpy "d.get('message')"))"
          req POST "/v1/actions/$MAIN/deny" owner
        elif [ "$CODE" = 200 ]; then
          STATE=$(jpy "d.get('state')")
          case "$STATE" in
            succeeded) pass "§3 owner approve -> accepted -> dispatched -> succeeded" ;;
            *) fail "§3 owner approve ended in '$STATE': $(jpy "d.get('result')")" ;;
          esac
          check "$(jpy "(d.get('decided_by') or {}).get('id') is not None or d.get('decided_by')")" "§3 action records who approved"
          req GET /v1/apps owner
          [ "$STATE" = succeeded ] && check "$(jpy "next(a for a in d if a['id'] == v[0])['installed'] is True or 'installed is false'" "$APP")" "§3 catalog shows $APP installed"
          if [ "$STATE" = succeeded ] && [ "$KEEP" = 0 ]; then
            K=$(key remove); req POST /v1/actions owner "$(action_body app.remove "$K" "$(rfc3339 600)")"
            ID=$(jpy "d.get('id')"); req POST "/v1/actions/$ID/approve" owner
            check "$(jpy "d.get('state') == 'succeeded' or d.get('state')")" "§3 app.remove approved -> succeeded"
          fi
        else
          fail "§3 owner approve -- HTTP $CODE $(head -c 300 "$WORK/body")"
        fi
      else
        req POST "/v1/actions/$MAIN/deny" owner
        skip "approve + execute (--no-execute; action denied instead)"
      fi
    else
      fail "§3 POST /v1/actions by $WHO -- HTTP $CODE $(head -c 300 "$WORK/body")"
    fi
  fi

  # ---- §11.3 MCP (wave 2): only agents may use it ----
  req POST /mcp owner '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
  case "$CODE" in
    404|405) fail "§11.3 POST /mcp is missing (HTTP $CODE): the gateway must serve /mcp" ;;
    403) check "$(jpy "d.get('error') == 'permission_denied' or d")" "§11.3 /mcp refuses a person principal (403)" ;;
    *) fail "§11.3 /mcp with an owner token should be 403, got HTTP $CODE" ;;
  esac
  MCP_CODE=$CODE
  if [ "$MCP_CODE" = 403 ] && [ -n "$AGENT" ]; then
    # Agent side: initialize, tools/list (no approve/deny tool), request_action -> an action that
    # an agent requested and that the owner can then deny. JSON or SSE answers are both accepted.
    python3 -I - "$HUB/mcp" "$WORK/agent.tok" "$APP" > "$WORK/py.out" 2>&1 <<'PY'
import json, sys, urllib.request, urllib.error
url, tok, app = sys.argv[1], open(sys.argv[2]).read().strip(), sys.argv[3]
sid, n = None, 0
def out(ok, msg): print(("PASS  " if ok else "FAIL  ") + msg)
def call(method, params=None, notify=False):
    global sid, n
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None: msg["params"] = params
    if not notify: n += 1; msg["id"] = n
    h = {"Authorization": "Bearer " + tok, "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    if method != "initialize": h["MCP-Protocol-Version"] = "2025-06-18"
    if sid: h["Mcp-Session-Id"] = sid
    rq = urllib.request.Request(url, data=json.dumps(msg).encode(), headers=h, method="POST")
    with urllib.request.urlopen(rq, timeout=60) as r:
        sid = r.headers.get("Mcp-Session-Id") or sid
        body = r.read().decode("utf-8", "replace")
        if notify or not body.strip(): return None
        if "text/event-stream" in (r.headers.get("Content-Type") or ""):
            for line in body.splitlines():
                if line.startswith("data:"):
                    m = json.loads(line[5:])
                    if m.get("id") == msg["id"]: return m
            return None
        return json.loads(body)
try:
    init = call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "onemind-verify", "version": "0"}})
    out(bool(init and "result" in init), "§11.3 /mcp initialize as an agent")
    call("notifications/initialized", notify=True)
    tl = call("tools/list") or {}
    names = {t.get("name") for t in (tl.get("result") or {}).get("tools", [])}
    need = {"list_nodes", "list_apps", "request_action"}
    out(need <= names, "§11.3 agent tools include list_nodes, list_apps, request_action (%s)" % sorted(names))
    out(not any("approve" in (x or "") or "deny" in (x or "") for x in names), "§11.3 no approve or deny tool")
    rc = call("tools/call", {"name": "request_action", "arguments": {"type": "app.install", "app_id": app,
                                                                     "reason": "verify.sh §11.3 check"}}) or {}
    res = rc.get("result") or {}
    sc = res.get("structuredContent")
    if sc is None:
        for c in res.get("content", []):
            try: sc = json.loads(c.get("text", "")); break
            except ValueError: pass
    sc = sc or {}
    ok = not res.get("isError") and sc.get("state") == "awaiting_approval" and sc.get("action_id")
    out(bool(ok), "§11.3 request_action -> action awaiting_approval (%s)" % (sc or rc))
    if ok: print("MCP_ACTION " + str(sc["action_id"]))
except (urllib.error.URLError, ValueError, OSError) as e:
    out(False, "§11.3 /mcp as an agent: %s" % e)
PY
    tally "$WORK/py.out"
    MCP_ACTION=$(sed -n 's/^      MCP_ACTION //p; s/^MCP_ACTION //p' "$WORK/py.out" | head -1)
    if printf '%s' "$MCP_ACTION" | grep -Eqx '[A-Za-z0-9_.:-]{1,128}'; then
      req GET "/v1/actions/$MCP_ACTION" owner
      on200 "(d.get('requested_by') or {}).get('kind') == 'agent' and d.get('params') == {'app_id': v[0]} or [d.get('requested_by'), d.get('params')]" \
        "§11.3 the MCP action is an ordinary action requested by the agent" "$APP"
      req POST "/v1/actions/$MCP_ACTION/deny" owner
      on200 "d.get('state') == 'cancelled' or d.get('state')" "§11.3 owner denies the MCP-requested action -> cancelled"
    fi
  elif [ "$MCP_CODE" = 403 ]; then
    skip "§11.3 agent MCP tools (no --agent-token-file)"
  fi
fi

# ---- NATS: heartbeats on the bus and the audit stream ----
if [ "$NATS" != none ]; then
  for _ in $(seq 1 12); do grep -q '"subject": "onemind.node' "$WORK/nats.jsonl" 2>/dev/null && break; sleep 1; done
  sleep 1
  kill "$NATS_PID" 2>/dev/null; wait "$NATS_PID" 2>/dev/null
  if [ ! -s "$WORK/nats.jsonl" ]; then
    fail "NATS $NATS not reachable: $(tail -1 "$WORK/nats.log")"
  else
    pass "§1 NATS answers at $NATS"
    python3 -I - "$WORK/nats.jsonl" "${MAIN:-}" "$([ -n "$AGENT" ] && echo agent)" > "$WORK/py.out" 2>&1 <<'PY'
import hashlib, json, re, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
main, agent = sys.argv[2], sys.argv[3]
def out(ok, msg): print(("PASS  " if ok else "FAIL  ") + msg)
hb = [r for r in rows if r.get("sid") == "1"]
good = []
for r in hb:
    try: p = json.loads(r["payload"])
    except ValueError: continue
    m = re.fullmatch(r"onemind\.node\.([A-Za-z0-9_-]{1,64})\.status", r["subject"])
    if m and p.get("schema") == "onemind.node.status/v1" and p.get("node_id") == m.group(1): good.append(p)
out(bool(good), "§1/§2 heartbeat on onemind.node.<node_id>.status with schema onemind.node.status/v1 (%d seen)" % len(good))
aud = []
for r in rows:
    if r.get("sid") == "2":
        try: aud.append(json.loads(r["payload"]))
        except ValueError: pass
if not aud:
    print("SKIP  §3 audit lines on NATS onemind.audit (none seen; needs --token and a gateway connected to NATS)")
    sys.exit(0)
canon = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
bad = [a.get("seq") for a in aud
       if hashlib.sha256((a["prev_hash"] + canon({k: v for k, v in a.items() if k not in ("prev_hash", "hash")})).encode()).hexdigest() != a["hash"]]
links = all(b["prev_hash"] == a["hash"] for a, b in zip(aud, aud[1:]) if b["seq"] == a["seq"] + 1)
out(not bad and links, "§3 %d audit lines on NATS onemind.audit; every hash and prev_hash link checks" % len(aud) + ("" if not bad else " (bad seq %s)" % bad))
if main:
    ev = {a["event"]: a for a in aud if a.get("action_id") == main}
    req = (ev.get("action.requested") or {}).get("principal") or {}
    out("action.requested" in ev and (req.get("kind") == ("agent" if agent else "person")),
        "§3/§7 audit records the requester of the action (%s %s)" % (req.get("kind"), req.get("id")))
    appr = ev.get("action.approved") or ev.get("action.denied")
    if appr:
        out((appr.get("principal") or {}).get("kind") == "person", "§3/§7 audit records the owner who decided (%s)" % (appr.get("principal") or {}).get("id"))
PY
    tally "$WORK/py.out"
  fi
fi

# ---- full audit file (hub only) ----
if [ -n "$AUDIT_FILE" ]; then
  if [ -r "$AUDIT_FILE" ]; then
    python3 -I - "$AUDIT_FILE" > "$WORK/py.out" 2>&1 <<'PY'
import hashlib, json, sys
canon = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
prev, n = "0" * 64, 0
for i, line in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    if not line.strip(): continue
    r = json.loads(line); ph, h = r.pop("prev_hash"), r.pop("hash")
    if ph != prev or r.get("seq") != n + 1 or hashlib.sha256((prev + canon(r)).encode()).hexdigest() != h:
        print("FAIL  §3 audit file hash chain breaks at line %d" % i); sys.exit(0)
    prev, n = h, n + 1
print("PASS  §3 audit file hash chain intact (%d lines)" % n)
PY
    tally "$WORK/py.out"
  else
    fail "§3 audit file $AUDIT_FILE not readable (run as root on the hub)"
  fi
fi

echo
echo "Summary: $NP passed, $NF failed, $NS skipped"
[ "$NF" = 0 ]
