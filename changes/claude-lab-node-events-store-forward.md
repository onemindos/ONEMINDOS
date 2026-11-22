---
pr: pending
branch: claude/lab-node-events-store-forward
status_rows:
  - CORE-FABRIC-5 | in-review | node events and heartbeats of record go through the leaf outbox
---
Node events now survive a link cut. With ONEMIND_AGENT_DURABLE=1 (or --durable-events) onemindd stores each event posted to its loopback API (POST /api/v1/events) in the leaf outbox, and writes a heartbeat of record every five minutes, so after an outage the hub collects the node's history from the gap and not only a last_seen jump. Live heartbeats stay unbuffered on purpose. Found in the R530 lab run, where 41 events published during a 611 second cut were never delivered. Builds on the leaf outbox of #472.
