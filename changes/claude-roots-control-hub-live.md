---
pr: 954
branch: claude/roots-control-hub-live
---
Control Hub is now the live board (Refs #502, FD-05): open alerts (critical first), app health, machines, storage, backups, the A/B system slots and, for owners and adults only, Kubernetes readiness per machine. One subscription to GET /v1/events through @onemind/sdk refreshes just the panels an event touches; every panel also re-reads every 30 s, so a hub without the stream never freezes the board. A panel whose refresh failed or whose answer is older than three polls turns stale and says so. The demo gateway shows "does not report" for storage and backups instead of invented numbers. Kubernetes Warning events are not on the board yet: the gateway has no route for them.
