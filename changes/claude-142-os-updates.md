---
pr: 357
branch: claude/142-os-updates
status_rows:
  - CORE-UPDATE-2 | in-progress | /v1/os/updates read routes and the os.update.install approval landed; the local update socket is still missing
  - CORE-UPDATE-3 | in-review | Updates screen reads real heartbeat data
---
OS updates in the gateway and the dashboard (UMB-P05, #142). GET /v1/os/updates shows, per machine, the system version it runs, its booted A or B slot, the slots, the update on offer and the update engine's state, all read from the node heartbeats that internal/update already feeds. GET /v1/os/updates/history lists every commit and rollback a machine reported (kept in its own table, at most 100 per machine) and the install requests filed. Installing is the new os.update.install action: a person asks, only an owner approves, and the check runs again at approval. The gateway still has no path to the update engine on the box, so an approved install ends failed with reason engine_unreachable and tells the owner to run onemind update apply at the box; the page says so too. The new OS updates page in the dashboard shows all of this and its install button only files the request.
