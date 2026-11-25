---
pr: pending
branch: claude/gwperm-4-mcp-scope-escalation
---
Closes the MCP privilege escalation: an agent token minted through identity with a broad actions:request scope but no work:read used to get the whole static-token v0 bundle at /mcp (nodes, apps, audit, backups, alerts), more than it was minted with. The /mcp tool scopes are now always rebuilt from the scopes on the token, with a broad scope covering its narrowed forms. A token narrowed to actions:request:app.install could not call /mcp at all; it now can, for that one request type only. Gateway permissions design PR 4 (gap 4, review item 17). No setting changes here, so no new dashboard or CLI control.
