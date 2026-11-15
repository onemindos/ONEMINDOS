---
pr: 262
branch: fix/230-mac-dev-loop
---
Fix the Apple Silicon developer loop (CI-05, issue #230): canonicalize only trusted safeFS test roots, retain symlink rejection, declare isolated Python unit-test dependencies, and replace missing handbook references with a single Mac development guide distinguishing native tests from Docker builds inside Lima. No production restore policy or shipping OS decision changes.
