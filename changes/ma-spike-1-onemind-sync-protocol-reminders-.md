---
pr: pending
branch: ma/spike-1-onemind-sync-protocol-reminders-
---
Spike 1 of D-032, OneMind Sync (F1): docs/design/SYNC.md proposes one offline sync protocol for every OneMind app (a per-app changes feed with a monotonic cursor, pushes with idempotency keys, tombstones, conflicts kept as copies, the age of every cached item, the normal gateway principal, 409 app_disabled from BuiltinGate, and how the log maps onto JetStream later). The gateway prototype adds one change-log table and GET /v1/sync/reminders/changes and POST /v1/sync/reminders/push for the Reminders proof record, each person seeing only their own items and agents refused. clients/sync is a plain TypeScript kit (memory and expo-sqlite-shaped storage, outbox, backoff loop, conflict copies) with Jest tests and an end-to-end script for a real box. Reminders is not yet on the signed system apps list and has no screen, CLI or MCP tools.
