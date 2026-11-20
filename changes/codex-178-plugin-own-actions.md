---
pr: 411
branch: codex/178-plugin-own-actions
---
Allows installation-owned plugin credentials with the exact internal actions:read:own grant to poll only their own action requests. Known operation IDs and live app state are required; other actors' action details are indistinguishable from missing IDs. No broad ledger scope or approval capability is added.
