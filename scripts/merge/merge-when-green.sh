#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Wait for every check on a PR to finish; merge only if all passed (skipped is fine).
# usage: scripts/merge/merge-when-green.sh <pr-number> [owner/repo]
R=${2:-onemindos/ONEMINDOS}; PR=$1
sleep 30
until out=$(gh pr checks "$PR" -R "$R" 2>/dev/null) && [ -n "$out" ] && ! echo "$out" | awk -F"	" '{print $2}' | grep -qE "pending|queued|in_progress"; do sleep 30; done
fails=$(gh pr checks "$PR" -R "$R" 2>/dev/null | awk -F"	" '$2!="pass" && $2!="skipping"{print $1": "$2}')
if [ -n "$fails" ]; then echo "PR #$PR NOT MERGED, failing checks:"; echo "$fails"; exit 1; fi
gh pr merge "$PR" -R "$R" --merge >/dev/null 2>&1
echo "PR #$PR $(gh pr view "$PR" -R "$R" --json state -q .state)"
