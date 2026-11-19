---
pr: pending
branch: codex/178-plugin-token-policy
---
Adds the DEV-PLG-3 read-only policy foundation for installation-owned plugin identity tokens. Only explicitly stored apps and nodes read grants work while the app is installed or stopped; writes, self-service, MCP, unknown routes and malformed grants are denied. No plugin issuer, action requests or lifecycle credential changes are enabled.
