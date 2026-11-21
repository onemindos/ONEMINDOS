---
pr: pending
branch: claude/170-leaf-mode
status_rows:
  - CORE-FABRIC-5 | in-review | first slice: JetStream outbox on the leaf, hub source stream, onemind fabric outbox
---
Leaf-only nodes (no k3s) get store-and-forward: a bounded JetStream outbox on the local leaf that refuses new messages when full instead of dropping unread ones, retry-safe sends by message id, a hub source stream definition, and `onemind fabric outbox` (init, status, send). A lab test shows a leaf buffering through a hub outage and the hub receiving every message once.
