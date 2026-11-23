---
pr: 978
branch: claude/roots-hub-sourcing
---
The hub now keeps a copy of every joined node's leaf outbox across the per-node NATS accounts (#747). Each NODE account exports to the hub only its outbox consumer API, the flow-control replies and a delivery subject under its own prefix, and the hub imports them; approving a join makes the node's hub source stream (the shape of internal/leaf HubSourceStream). A two-leaf lab test proves a node cut for 10 minutes while writing 600 events delivers exactly those 600 in order, and that node A reaches neither node B's stream nor its JetStream API. Known gap with a follow-up: the empty flow-control replies still reach every node until leaves turn on the js_ack_fc_v2 flag.
