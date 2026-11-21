---
pr: pending
branch: claude/sec-agent-token-lifecycle
---
Security: a static-file adult can no longer mint an agent API token that no account owns (it outlived the adult's removal and could not be listed or revoked), and an app update whose manifest drops `spec.agent` now revokes the app's agent principal instead of leaving it live.
