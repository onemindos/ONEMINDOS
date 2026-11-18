---
pr: pending
branch: ci/drafts-cheap-checks
---
CI-09: draft PRs now run only dco, hygiene, lint and unit; every heavier job skips on drafts and starts when the PR is marked ready. Every PR workflow cancels superseded PR runs and never cancels main, merge-queue or nightly runs. merge-gate waits for the full set after a draft is marked ready, with tests, and docs/learning/ci-capacity.md explains the numbers.
