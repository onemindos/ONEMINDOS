---
pr: pending
branch: claude/gw-stored-taint-exposed-agents
---
Taint is now kept in the database, so a restart no longer forgets which agents read outside text and the one-hour expiry keeps running. An agent that can read text the gateway cannot see (web, email, files, a chat host) is exposed and tainted permanently, so no standing approval accepts its requests: an installed app's agent and a plugin are exposed by default, and the owner declares the rest with PUT /v1/agents/id/inputs or onemind agents inputs set. Only the owner can change the declaration (an agent never lowers its own taint), the change is audited and needs a fresh passkey. A per-type accept-injection-risk flag is recorded for one write type at a time, owner only; it loosens nothing yet. Gateway permissions design PR 6, F-11, D-027.
