---
pr: 267
branch: ci/gate-job
---
One always-reporting merge gate. A new gate workflow runs on every PR and merge-queue entry, waits for every other workflow GitHub started for the same commit, and fails if a blocking one failed (fuzzers, scans, perf and net-2vm only inform). A docs-only PR passes in minutes; a PR that breaks core tests or the image battery cannot pass. Once the founder makes gate the required check on main, red component suites can no longer merge (CI-02, issue 227).
