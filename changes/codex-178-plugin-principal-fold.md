---
pr: 450
branch: codex/178-plugin-principal-fold
---
Consolidates installation-owned plugin principals, exact request grants, scoped HTTP routes and own-action polling. Approved installation delivers plugin-only credentials; removal, replacement, failure and recovery retire them persistently. Plugins cannot approve actions, widen scopes or rotate managed credentials.
The install and update plan now lists every grant the plugin token will hold, in plain words, and the plan hash binds them, so the owner approves exactly what the plugin can later ask for (#409).
