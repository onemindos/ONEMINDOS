#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Dispatch every automated test workflow, wait for them, and write a pass/fail table.
# Used by .github/workflows/test-all.yml (docs/testing/README.md §2). Needs bash 4+, gh and jq, and
# GH_TOKEN with actions: write. Env: REF (branch or tag), HEAVY (true|false), WAIT_MINUTES (<= 330,
# the job's timeout leaves room for the summary), WF_DIR (the ref's .github/workflows checkout).
set -euo pipefail

REF=${REF:-main}
HEAVY=${HEAVY:-true}
WAIT_MINUTES=${WAIT_MINUTES:-300}
WF_DIR=${WF_DIR:-.github/workflows}
SUMMARY=${GITHUB_STEP_SUMMARY:-/dev/stdout}
[[ $WAIT_MINUTES =~ ^[0-9]+$ ]] || { echo "WAIT_MINUTES must be a whole number of minutes" >&2; exit 2; }
[ "$WAIT_MINUTES" -le 330 ] || WAIT_MINUTES=330

# file|extra gh workflow run flags. Light: minutes each. Heavy: image builds, QEMU batteries and the
# full app gate (ci-apps gates every app when it is started by hand).
LIGHT=(
  "ci.yml|"
  "hygiene.yml|"
  "ci-core.yml|"
  "ci-onemindd.yml|"
  "ci-dashboard.yml|"
  "ci-ui.yml|"
  "ci-deploy.yml|"
  "site.yml|"
)
HEAVY_LIST=(
  "ci-apps.yml|"
  "image.yml|"
  "nightly.yml|"
  "security-nightly.yml|-f dry_run=true -f force_rebuild=true"
)
# Not dispatched: test-all itself; battery.yml (image.yml and nightly.yml call it; TR-262 dispatches
# it alone); apps-rescan.yml (it opens a pull request; TR-087 runs it by hand).
SKIP=(test-all.yml battery.yml apps-rescan.yml)

list=("${LIGHT[@]}")
[ "$HEAVY" = "true" ] && list+=("${HEAVY_LIST[@]}")

declare -A RUN_ID STATE CONCL URL
order=()

known() { local f=$1 e; for e in "${LIGHT[@]}" "${HEAVY_LIST[@]}"; do [ "${e%%|*}" = "$f" ] && return 0; done; for e in "${SKIP[@]}"; do [ "$e" = "$f" ] && return 0; done; return 1; }

for entry in "${list[@]}"; do
  wf=${entry%%|*}; extra=${entry#*|}
  order+=("$wf")
  if [ ! -f "$WF_DIR/$wf" ]; then STATE[$wf]="absent"; continue; fi
  if ! grep -qE '^[[:space:]]*workflow_dispatch:' "$WF_DIR/$wf"; then STATE[$wf]="not dispatchable (no workflow_dispatch)"; continue; fi
  # Runs that already exist, so the new run is the one id not in this list (no clock comparison).
  before=$(gh run list --workflow "$wf" --event workflow_dispatch --limit 100 --json databaseId --jq '[.[].databaseId]' 2>/dev/null) || before='[]'
  [ -n "$before" ] || before='[]'
  # shellcheck disable=SC2086 # $extra is a list of flags
  if ! gh workflow run "$wf" --ref "$REF" $extra; then STATE[$wf]="dispatch failed"; continue; fi
  id=""
  for _ in $(seq 1 24); do
    sleep 5
    id=$(gh run list --workflow "$wf" --event workflow_dispatch --branch "$REF" --limit 20 --json databaseId \
           --jq "[.[].databaseId] - $before | max // empty" 2>/dev/null) || id=""
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
    if j=$(gh run view "$id" --json status,conclusion,url 2>/dev/null); then
      STATE[$wf]=$(jq -r .status <<<"$j"); CONCL[$wf]=$(jq -r '.conclusion // ""' <<<"$j"); URL[$wf]=$(jq -r .url <<<"$j")
    fi
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
    if [ -z "$id" ]; then
      if [ "${STATE[$wf]}" = absent ]; then echo "| \`$wf\` | – | not on this ref (skipped) |"
      else echo "| \`$wf\` | – | ${STATE[$wf]} |"; fail=1; fi
      continue
    fi
    if [ "${STATE[$wf]}" != completed ]; then out="still running after ${WAIT_MINUTES} min (${STATE[$wf]})"; fail=1
    else out=${CONCL[$wf]}; [ "$out" = success ] || fail=1; fi
    echo "| \`$wf\` | [${id}](${URL[$wf]:-${GITHUB_SERVER_URL:-https://github.com}/${GH_REPO:-}/actions/runs/$id}) | $out |"
  done
  extra_wf=()
  for f in "$WF_DIR"/*.yml; do [ -e "$f" ] || continue; b=$(basename "$f"); known "$b" || extra_wf+=("$b"); done
  if [ "${#extra_wf[@]}" -gt 0 ]; then
    echo
    echo "**Not in test-all** (add them to \`scripts/test-all.sh\` if they are tests): ${extra_wf[*]}"
  fi
  echo
  echo "Record results in \`docs/testing/RESULTS.md\` (TR-260 to TR-263 and each workflow's own rows)."
} >> "$SUMMARY"

exit "$fail"
