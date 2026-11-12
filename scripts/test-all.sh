#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Dispatch every automated test workflow, wait for them, and write a pass/fail table.
# Used by .github/workflows/test-all.yml (docs/testing/README.md §2). Needs gh and jq, and
# GH_TOKEN with actions: write. Env: REF (branch or tag), HEAVY (true|false), WAIT_MINUTES.
set -euo pipefail

REF=${REF:-main}
HEAVY=${HEAVY:-true}
WAIT_MINUTES=${WAIT_MINUTES:-300}
SUMMARY=${GITHUB_STEP_SUMMARY:-/dev/stdout}
WF_DIR=.github/workflows

# file|extra gh workflow run flags. Light: minutes each. Heavy: image builds and QEMU batteries.
# battery.yml is not listed: image.yml and nightly.yml call it (TR-262 dispatches it alone).
LIGHT=(
  "ci.yml|"
  "hygiene.yml|"
  "ci-core.yml|"
  "ci-onemindd.yml|"
  "ci-dashboard.yml|"
  "ci-ui.yml|"
  "ci-deploy.yml|"
  "ci-apps.yml|"
  "site.yml|"
)
HEAVY_LIST=(
  "image.yml|"
  "nightly.yml|"
  "security-nightly.yml|-f dry_run=true -f force_rebuild=true"
)
# Workflows that are not tests, or that run test-all itself.
SKIP=(test-all.yml battery.yml)

list=("${LIGHT[@]}")
[ "$HEAVY" = "true" ] && list+=("${HEAVY_LIST[@]}")

declare -A RUN_ID STATE CONCL URL
order=()

known() { local f=$1 e; for e in "${LIGHT[@]}" "${HEAVY_LIST[@]}"; do [ "${e%%|*}" = "$f" ] && return 0; done; for e in "${SKIP[@]}"; do [ "$e" = "$f" ] && return 0; done; return 1; }

for entry in "${list[@]}"; do
  wf=${entry%%|*}; extra=${entry#*|}
  order+=("$wf")
  if [ ! -f "$WF_DIR/$wf" ]; then STATE[$wf]="missing on $REF"; continue; fi
  if ! grep -qE '^[[:space:]]*workflow_dispatch:' "$WF_DIR/$wf"; then STATE[$wf]="not dispatchable (no workflow_dispatch)"; continue; fi
  since=$(date -u -d '-30 seconds' +%Y-%m-%dT%H:%M:%SZ)
  # shellcheck disable=SC2086 # $extra is a list of flags
  if ! gh workflow run "$wf" --ref "$REF" $extra; then STATE[$wf]="dispatch failed"; continue; fi
  id=""
  for _ in $(seq 1 24); do
    sleep 5
    id=$(gh run list --workflow "$wf" --event workflow_dispatch --branch "$REF" --limit 20 \
           --json databaseId,createdAt \
           --jq "[.[] | select(.createdAt >= \"$since\")] | sort_by(.createdAt) | .[0].databaseId // empty")
    [ -n "$id" ] && break
  done
  if [ -z "$id" ]; then STATE[$wf]="dispatched, run not found"; continue; fi
  RUN_ID[$wf]=$id; STATE[$wf]=queued
  echo "dispatched $wf -> run $id"
done

deadline=$(( $(date +%s) + WAIT_MINUTES * 60 ))
while :; do
  pending=0
  for wf in "${order[@]}"; do
    id=${RUN_ID[$wf]:-}; [ -n "$id" ] || continue
    [ "${STATE[$wf]}" = completed ] && continue
    j=$(gh run view "$id" --json status,conclusion,url)
    STATE[$wf]=$(jq -r .status <<<"$j"); CONCL[$wf]=$(jq -r '.conclusion // ""' <<<"$j"); URL[$wf]=$(jq -r .url <<<"$j")
    [ "${STATE[$wf]}" = completed ] || pending=$((pending + 1))
  done
  [ "$pending" -eq 0 ] && break
  [ "$(date +%s)" -ge "$deadline" ] && break
  echo "$pending run(s) still going; next check in 60 s"
  sleep 60
done

fail=0
{
  echo "## test-all on \`$REF\` (heavy: $HEAVY)"
  echo
  echo "| Workflow | Run | Outcome |"
  echo "|---|---|---|"
  for wf in "${order[@]}"; do
    id=${RUN_ID[$wf]:-}
    if [ -z "$id" ]; then echo "| \`$wf\` | – | ${STATE[$wf]} |"; fail=1; continue; fi
    if [ "${STATE[$wf]}" != completed ]; then out="still running after ${WAIT_MINUTES} min (${STATE[$wf]})"; fail=1
    else out=${CONCL[$wf]}; [ "$out" = success ] || fail=1; fi
    echo "| \`$wf\` | [${id}](${URL[$wf]:-}) | $out |"
  done
  extra_wf=()
  for f in "$WF_DIR"/*.yml; do b=$(basename "$f"); known "$b" || extra_wf+=("$b"); done
  if [ "${#extra_wf[@]}" -gt 0 ]; then
    echo
    echo "**Not in test-all** (add them to \`scripts/test-all.sh\` if they are tests): ${extra_wf[*]}"
  fi
  echo
  echo "Record results in \`docs/testing/RESULTS.md\` (TR-260 to TR-263 and each workflow's own rows)."
} >> "$SUMMARY"

exit "$fail"
