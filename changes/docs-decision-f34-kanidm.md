---
pr: 401
branch: docs/decision-f34-kanidm
---
Founder decision D-015 (F-34): Kanidm runs as a host service on the hub OS, not as a chart in k3s, so sign-in keeps working when k3s is down. F-34 leaves the open-decisions list. This unblocks the Kanidm lab test (UMB-ACCT-1) and CORE-SEC-10; issue 236 still waits on that test and on issue 139.
