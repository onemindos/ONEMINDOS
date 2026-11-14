---
pr: pending
branch: ci/gate-smoke-logs
---
The app gate can now save evidence when a smoke test fails: with the new `--logs-dir`, it writes each pod's last 1000 log lines (plus the previous run of any restarted container) and the namespace events there before the namespace is torn down, never on a pass. Every Secret value in the namespace (6 characters or more) and the smoke placeholder are replaced with `[REDACTED]` first, and a failure to collect logs only adds a note and never changes the gate result. The weekly all-apps gate uploads them for failed jobs as `apps-gate-logs-<app>-<arch>`, kept 7 days. Also gives the security suite (route policy table, per-role route tests, API fuzzing) the board id CORE-SEC-11 in SECURITY.md and its test docstrings.
