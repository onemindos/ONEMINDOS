---
pr: pending
branch: ma/fix-snapshots-before-any-backup-destinat
---
Fixes the snapshot list before any backup destination exists (Refs #1232, Refs #234). The gateway now answers GET /v1/backups/snapshots with an empty list and an OneMind-Reason header (no backup destination yet) instead of an error or a wait on the backup agent. The dashboard restore points card and the onemind backup snapshots command say plainly that there is nothing yet and that a destination is needed if there is none (the wording is right whether or not one exists), instead of failing or hanging for 60 seconds. A box with backups switched off still answers 503 backups_disabled. The header is declared in the OpenAPI spec. The MCP list_backup_snapshots tool returns a bare empty list with no reason.
