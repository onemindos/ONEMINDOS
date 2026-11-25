---
pr: pending
branch: claude/host-helper-after-gate-ready
---
The host helper (restart, shut down, OS install) now starts as soon as the health gate has decided the booted slot, instead of waiting out the gate's report-only k3s watch on a committed boot (up to 300 seconds). The gate is a Type=notify unit that sends READY=1 after it commits the slot (or, on a trial, marks it good), so units ordered after it start then. A trial boot still keeps the helper and OS install back until the slot is marked good. This was the root cause of first-boot check F12 reporting the helper missing for 120 seconds.
