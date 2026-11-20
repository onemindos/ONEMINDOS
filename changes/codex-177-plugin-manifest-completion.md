---
pr: pending
branch: codex/177-plugin-manifest-completion
---
Completes declaration-only plugin validation without requiring an unused tool/backend/workload. Backend-bearing extensions still require their workload and backend. Adds bounded publisher declarations, rejects simultaneous plugin and agent credentials, and preserves ordinary App requirements.
