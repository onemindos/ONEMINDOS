---
pr: 389
branch: codex/177-plugin-events
---
Adds DEV-PLG-1 event declarations to tool plugins: publish names remain local to the app, and every subscription requires an explicit covering permission. Invalid wildcard patterns and unrestricted subscriptions or grants are rejected by the shared offline Go validator.
