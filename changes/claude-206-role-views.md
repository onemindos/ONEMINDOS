---
pr: 354
branch: claude/206-role-views
---
Dashboard Simple and Pro by role (UX-01, issue 206). There is no Pro switch: owners and adults see the Pro screens (Nodes, Control Hub, AI & Agents, Storage, Backups), while guests and children see the simple set, and a direct link to a Pro screen shows a short notice instead. The role comes from the session or GET /v1/me, and an unknown role falls back to Simple. The new Control Hub lists machines with their cluster role, readiness and A/B slot, every workload with its state, and the monitoring summary; Start, Stop and Restart only file a request that waits for owner approval. The new AI & Agents screen reads the audit chain (GET /v1/audit/events and /v1/audit/verify) and keeps the agents' records and the decisions on their requests, with a per-agent summary; when the chain cannot be read it falls back to the agents' requests and says so. UI tests cover owner, adult, guest and child.
