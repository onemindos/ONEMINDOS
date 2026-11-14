# SPDX-License-Identifier: Apache-2.0
# Phase 10: the gateway (core/, in a venv; user onemind-gw in group onemind) drives the real storage
# service over its socket: an agent requests storage.mirror.add of vdd, the agent's approval is
# refused, the owner approves, the poller closes the action from the node's journal. The dev tokens
# are the repository's public examples (core/examples/tokens.example.yaml).
. ./common.sh
wait_service
mkdir -p /var/lib/lab/gw && chown onemind-gw:onemind /var/lib/lab/gw
systemctl stop lab-gw 2>/dev/null || true
systemd-run --unit lab-gw -p User=onemind-gw -p Group=onemind -p WorkingDirectory=/var/lib/lab/gw \
  -E ONEMIND_TOKENS_FILE=/opt/gw/core/examples/tokens.example.yaml -E ONEMIND_DATA_DIR=/var/lib/lab/gw \
  -E ONEMIND_APPS_DIR=/opt/gw/core/tests/fixtures/apps -E ONEMIND_NATS_URL= -E ONEMIND_HOST=127.0.0.1 \
  -E ONEMIND_NODE_ID=lab0node0001 -E ONEMIND_STORAGE_ENABLED=1 -E ONEMIND_STORAGE_POLL_S=5 \
  /opt/gw/venv/bin/python -m onemind_core >/dev/null
OWN='Authorization: Bearer dev-owner-token-change-me'
AGT='Authorization: Bearer dev-agent-token-change-me'
gw() { curl -sS -H 'Content-Type: application/json' "$@"; }
i=0; until gw http://127.0.0.1:8080/healthz >/dev/null 2>&1; do sleep 0.5; i=$((i + 1)); [ $i -lt 60 ] || break; done
echo "== a user outside the group cannot reach the socket"
runuser -u nobody -- curl -sS --unix-socket "$SOCK" http://storage/v1/status 2>&1 | head -1
echo "== GET /v1/storage (any principal; no disk identities)"
gw -H "$AGT" http://127.0.0.1:8080/v1/storage | jq -c '{enabled, available, state, encrypted, generation, members: (.members | length)}'
echo "== agent requests storage.mirror.add of /dev/vdd"
r=$(gw -H "$AGT" -X POST http://127.0.0.1:8080/v1/storage/actions -d '{"type":"storage.mirror.add","params":{"device":"/dev/vdd"},"reason":"third disk for raid1c3 metadata"}')
echo "$r" | jq -c '{action: .action | {id, state, type, requested_by}, risk, plan_sha256: .plan_sha256[0:12], targets: .plan.targets | map({path, serial_tail, size_bytes})}'
id=$(echo "$r" | jq -r .action.id)
printf 'agent approves: '; gw -H "$AGT" -X POST "http://127.0.0.1:8080/v1/actions/$id/approve" | jq -c '{error}'
printf 'owner approves: '; gw -H "$OWN" -X POST "http://127.0.0.1:8080/v1/actions/$id/approve" | jq -c '{state}'
i=0
while [ $i -lt 120 ]; do
  s=$(gw -H "$OWN" "http://127.0.0.1:8080/v1/actions/$id" | jq -r .state)
  [ "$s" = dispatched ] || break
  sleep 2; i=$((i + 1))
done
gw -H "$OWN" "http://127.0.0.1:8080/v1/actions/$id" | jq -c '{state, result: .result.message}'
gw -H "$OWN" "http://127.0.0.1:8080/v1/storage/operations/$id" | jq -c '{state, progress}'
gw -H "$OWN" http://127.0.0.1:8080/v1/storage | jq -c '{state, generation, members: (.members | length), profiles: [.profiles[] | "\(.kind)=\(.profile)"]}'
echo "== audit trail of the action"
jq -c --arg id "$id" 'select(.action_id == $id) | {event, by: .principal.id}' /var/lib/lab/gw/audit.jsonl
echo "== events the notifier would receive"
jq -c 'select(.event | startswith("storage.")) | {event, severity: .data.severity, dedupe: .data.dedupe_key}' /var/lib/lab/gw/audit.jsonl
corpus_check
systemctl stop lab-gw
