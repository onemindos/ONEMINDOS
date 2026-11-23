---
pr: pending
branch: claude/d12-mcp-read-tools
---
Agents can now read the box's state through MCP (#632). Thirteen new read tools cover backups (status, runs, snapshots), OS updates (status, history), file details, virtual machines, storage, alerts, update settings and app logs. Each tool calls the same service as its REST route and follows that route's rule for who may read. Before anything reaches the model, secret-named fields and secret-looking text (keys, bearer tokens, URL passwords, private keys, e-mail and IP addresses) are redacted, third-party text is marked untrusted, and lists are capped at 100 rows and paged with a cursor. App logs return at most 500 lines; asking for more returns 500 with `truncated: true`. Logs and file details need the `logs:read` or `files:read` scope granted by name, so agents without scopes keep their old access. The parity list now records the eight read areas, and the 13 routes moved from AWAITING_TOOL to tools.
