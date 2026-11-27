---
pr: pending
branch: claude/fix-map-packs-unset
---
Map packs on a box without Offline Maps set up no longer look like a server fault. `GET /v1/map/packs` now lists no packs (with `free_bytes` null) when no packs volume is configured, and a request to add or remove a pack is refused 409 with reason `map_storage_not_configured`. A configured volume that did not mount stays 503 `map_storage_unavailable`. Found by the api-fuzz agent run (ST101 on `GET /v1/map/packs`).
