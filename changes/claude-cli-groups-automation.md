---
pr: pending
branch: claude/cli-groups-automation
---
The onemind command line gains `automation` (list, show, add, turn on and off, dry-run and delete rules; run history and schedules; the pause switch; standing approvals to list and revoke; maintenance windows to list and set), `alerts` (list, show, acknowledge, resolve, and request an alert's suggested fix, which a person still approves) and `monitoring summary` (machines, apps and open alerts at a glance). Every command takes --json. A rule can only file requests, the CLI never approves anything, creating a standing approval stays in the dashboard with its passkey step, and the passkey step the gateway wants for a window is explained rather than skipped. Refs the UI and backend parity report (S7 windows CLI, S8 automation, alerts and monitoring rows).
