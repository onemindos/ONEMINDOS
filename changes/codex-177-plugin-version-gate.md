---
pr: 395
branch: codex/177-plugin-version-gate
---
Checks plugin tool API changes when comparing an update: tool removals, effect changes and changed input schemas require a higher plugin major version. Input changes are conservatively treated as breaking rather than guessing whether arbitrary JSON Schemas remain compatible.
