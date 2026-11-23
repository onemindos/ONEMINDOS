---
pr: pending
branch: claude/ready-engine-feed-ui
---
Engine feed (#619), part 2: Settings, About shows an Engine panel (Simple view: is the message bus running, how many machines are connected, how full the message store is; the owner also sees each machine's link and how many messages it is behind, and connections per NATS account under Technical details), and onemind nats status prints the same numbers on the box. Both read GET /v1/engine; a child, who has no monitoring:read, does not see the panel.
