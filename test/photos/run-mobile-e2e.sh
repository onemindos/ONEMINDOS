#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# End to end: the phone's backup engine (mobile/src/photos) against a live gateway with Photos on.
#
#   test/photos/run-mobile-e2e.sh [MOBILE_DIR]
#
# MOBILE_DIR defaults to ./mobile and must hold src/photos (branch feat/mobile-photos, PR #34)
# with `npm ci` already run. Needs uv (for core/). Set ONEMIND_E2E_DB_URL=postgresql://... to run
# the gateway on PostgreSQL instead of a throwaway SQLite file. Tokens are made fresh each run.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
mobile=$(cd "${1:-$repo/mobile}" && pwd)
if [ ! -f "$mobile/src/photos/engine.ts" ]; then
  echo "skip: $mobile has no src/photos/engine.ts (feat/mobile-photos not merged)"
  exit 0
fi

work=$(mktemp -d)
e2e_dir="$mobile/src/photos/__e2e__"
gw_pid=""
cleanup() {
  [ -n "$gw_pid" ] && kill "$gw_pid" 2>/dev/null || true
  rm -rf "$e2e_dir"
  rm -rf "$work"
}
trap cleanup EXIT

tok() { python3 -c 'import secrets; print(secrets.token_hex(32))'; }
t1=$(tok)
t2=$(tok)
cat >"$work/tokens.yaml" <<EOF
tokens:
  "$t1": {id: e2e-ana, kind: person, role: owner}
  "$t2": {id: e2e-ben, kind: person, role: adult}
EOF
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')

(
  cd "$repo/core"
  ONEMIND_TOKENS_FILE="$work/tokens.yaml" \
  ONEMIND_DB_URL="${ONEMIND_E2E_DB_URL:-sqlite:///$work/onemind.db}" \
  ONEMIND_AUDIT_PATH="$work/audit.jsonl" \
  ONEMIND_APPS_DIR="$repo/core/tests/fixtures/apps" \
  ONEMIND_NATS_URL="" \
  ONEMIND_NODE_ID="e2e000000000" \
  ONEMIND_HOST=127.0.0.1 ONEMIND_PORT="$port" \
  ONEMIND_PHOTOS_ENABLED=1 ONEMIND_PHOTOS_DIR="$work/photos" ONEMIND_PHOTOS_RESERVE_BYTES=0 \
  exec uv run --quiet python -m onemind_core
) >"$work/gateway.log" 2>&1 &
gw_pid=$!

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$port/healthz" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$port/healthz" >/dev/null || { cat "$work/gateway.log"; exit 1; }

mkdir -p "$e2e_dir"
cp "$here/mobile-e2e.test.ts" "$e2e_dir/server.e2e.test.ts"
rc=0
(
  cd "$mobile"
  ONEMIND_E2E_URL="http://127.0.0.1:$port" ONEMIND_E2E_TOKEN="$t1" ONEMIND_E2E_TOKEN2="$t2" \
    npx jest --ci src/photos/__e2e__
) || rc=$?

# Server side: one stored copy per distinct set of bytes, a library file per person's photo.
stored=$(find "$work/photos/library/.shared-store" -type f | wc -l | tr -d ' ')
ana=$(find "$work/photos/library/e2e-ana" -type f | wc -l | tr -d ' ')
ben=$(find "$work/photos/library/e2e-ben" -type f | wc -l | tr -d ' ')
staged=$(find "$work/photos/staging" -type f | wc -l | tr -d ' ')
echo "box: stored copies=$stored ana files=$ana ben files=$ben staging=$staged"
if [ "$rc" -eq 0 ] && { [ "$stored" != 6 ] || [ "$ana" != 6 ] || [ "$ben" != 1 ] || [ "$staged" != 0 ]; }; then
  echo "unexpected files on the box (want stored=6 ana=6 ben=1 staging=0)"
  rc=1
fi
exit "$rc"
