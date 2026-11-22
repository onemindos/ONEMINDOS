---
pr: 861
branch: claude/ab-aipolicy
---
aiPolicy enforcement for agent reads of app data (Refs #165): one deny-by-default rule in ai_policy.py decides whether an app's data may reach an AI agent, and the MCP tools apply it before any action leaves, so a plugin tool's output (the app's own data) is withheld from get_action, list_actions and onemind://actions/{id} unless the app's aiPolicy is allowed (no policy, display-only, prohibited, consent-required, official-mcp-only and unknown values all withhold it; the owner still sees the output). The REST agent filter and the MCP catalogue now read the policy through the same helper. GET /v1/apps carries aiPolicy (null when none is declared, unknown for a value the gateway does not know), MCP list_apps and get_app show the same value, and onemind apps list adds an AI column while onemind apps info says what the policy means.
