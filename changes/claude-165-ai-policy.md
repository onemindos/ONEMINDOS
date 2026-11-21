---
pr: pending
branch: claude/165-ai-policy
---
A small, stable aiPolicy decision interface in the gateway (core/onemind_core/ai_policy.py): decide(policy, destination) says whether an app's data may go to the catalog view, an MCP tool, a local model, a remote model or the provider's official MCP. It denies by default: a missing, unknown or malformed policy sends no data anywhere, display-only and prohibited never pass, consent-required passes only with a stored owner consent, and official-mcp-only passes only to the provider's own MCP. The model router and tainted-input approval can call it before any model or tool call, and the existing REST and MCP catalog filters now use the same rule.
