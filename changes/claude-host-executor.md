---
pr: 385
branch: claude/host-executor
---
New onemindd host serve, a small root service on the box that carries out restart, shutdown and OS install actions the owner already approved in the gateway. It listens only on a local socket that root and the gateway can open, writes each action down by its id before acting (a retry never runs twice, and the result survives the reboot), and installs OS updates only through the update engine, so the snapshot, the A/B slot and the health-gated rollback stay in the path. Factory reset is designed in docs/leap/core/HOST-ACTIONS.md and reported unavailable until its early-boot wipe lands in the next PR. The gateway starts calling the socket in a follow-up after the system controls and OS updates PRs merge.
