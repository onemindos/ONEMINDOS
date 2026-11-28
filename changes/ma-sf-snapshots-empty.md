---
pr: 1311
branch: ma/sf-snapshots-empty
---
Fixes the snapshot list before any backup destination exists (Refs #1232, Refs #234). When the gateway has no destination records and the backup agent confirms zero configured targets, GET /v1/backups/snapshots returns an empty list with the OpenAPI-declared OneMind-Reason header without opening a backup repository. Targets configured only on the agent still support snapshot lookup and restore planning. The dashboard and CLI show an empty-state message, and MCP list_backup_snapshots keeps its array response. A box with backups switched off still answers 503 backups_disabled.
