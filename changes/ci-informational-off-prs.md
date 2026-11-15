---
pr: pending
branch: ci/informational-off-prs
---
CI-11 (issue 298): the informational workflows no longer run on every pull request. perf-smoke, api-fuzz, go-fuzz and net-2vm run on a schedule, on a push to main and by hand; a PR runs one only when it changes that workflow's own harness. merge-gate's informational list is unchanged. A policy test enforces it, and docs/learning/ci-capacity.md has the measured savings (about 354 PR runs and 9,500 run-minutes a week).
