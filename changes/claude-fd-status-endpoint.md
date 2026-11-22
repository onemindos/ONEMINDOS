---
pr: pending
branch: claude/fd-status-endpoint
---
FD-01 (#498): GET /v1/status answers what needs attention on the box, with a state (ok, attention, critical or unknown) and the time it was read for each of alerts, approvals, app health, storage, backups, updates and mesh. A source that cannot be read is reported as unknown, never ok. The SDKs are regenerated and onemind status prints the new block.
