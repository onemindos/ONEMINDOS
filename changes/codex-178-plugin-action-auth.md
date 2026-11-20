---
pr: pending
branch: codex/178-plugin-action-auth
---
Allows installation-owned plugin tokens with explicit action-type grants to file matching requests through the common action endpoint. Requests stay subject to exact-type guards, live installed-app state, owner-only action rules and human approval; revoked grants cannot replay earlier requests. Other writes, admin and MCP remain denied.
