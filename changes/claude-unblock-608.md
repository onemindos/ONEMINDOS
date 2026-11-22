---
pr: pending
branch: claude/unblock-608
---
Machines now say goodbye when they stop on purpose, and the hub notices a pulled plug in under 15 seconds (#608, first part). onemindd sends one departure message on its own status subject as the very last thing it does on a clean stop, so the hub shows the machine offline at once instead of after the heartbeats run out. The gateway adds a fast presence view (online, or offline once a heartbeat is clearly missed after 14 s or straight after a departure) and a departed_at time to GET /v1/nodes, while status keeps its 30 s and 120 s meaning so placement and alerts do not flap. GET /v1/events now looks at the nodes on every half-second poll and reports presence changes in node.status events. The dashboard and phone moving onto the stream come in follow-up pull requests.
