---
pr: pending
branch: codex/178-plugin-settings
---
Plugin settings are validated against a bounded offline schema snapshotted at installation. Changes remain pending until owner approval, then apply a fixed plugin-settings ConfigMap through the existing executor. Receipt checks and shared app-state claims prevent stale or concurrent lifecycle changes.
