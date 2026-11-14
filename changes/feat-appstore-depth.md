---
pr: 57
branch: feat/appstore-depth
status_rows:
  - UMB-APP-9 | in-review | host port declarations, CI and per-node conflict checks; avahi names with CORE-NET
  - UMB-APP-10 | in-review | pinned community sources and source actions; install needs the CORE-DEPLOY-2 image scanner
---
App store depth (contract section 12.22): per-app settings read from spec.settings and checked on app.configure (the lifecycle executor writes the ConfigMap); dependencies with alternatives and remove these first; host port declarations checked in CI and per node; Docker Compose import into a private app that refuses what the install sandbox refuses; community app sources pinned to a commit, fetched without running anything, SSRF-guarded and scanned on the box; exposure tiers private, mesh and public (parked) as separate owner requests. App logs stay with section 12.15.
