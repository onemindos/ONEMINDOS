---
pr: pending
branch: codex/177-plugin-ci-validator
---
Runs the built box plugin validator from app validation whenever a manifest declares extensions. Plugin checks fail closed without an explicit executable path, including subprocess failures; ordinary apps retain their checks. Declarative plugins skip workload checks only after shared validation succeeds. App CI builds the validator with pinned Go setup and re-gates apps when its Go sources or dependencies change.
