---
pr: pending
branch: codex/178-plugin-registry
---
Adds read-only installed plugin list/detail APIs using persisted app state, catalog declarations and the Market sharing filters. Responses use persisted installed versions, with null for missing receipts and expose no backend, secret declaration or raw manifest. Plugin issuance and request enforcement remain subsequent DEV-PLG-3 slices.
