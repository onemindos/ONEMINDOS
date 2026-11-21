---
pr: pending
branch: claude/p0-onbox-image-scan
status_rows:
  - CORE-DEPLOY-2 | in-review | first slice: sandboxed Trivy and cosign Job, pinned by digest, offline after first sync; community sources and migrate use it; ClamAV, scheduled DB refresh and a CLI verb are left
---
The gateway can now scan images on the box itself. A hardened one-shot Kubernetes Job runs a Trivy pinned by digest against a vulnerability database also pinned by digest, offline after the first sync, and writes a scan record in the same shape as apps/*/scan.json. Community sources and migrated apps use it, so the existing rule "install needs a passing scan under 7 days old" can now be met on the box. A fixable CRITICAL vulnerability or a secret fails the scan, and any error counts as unavailable, never pass.
