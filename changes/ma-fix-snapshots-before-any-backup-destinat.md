---
pr: pending
branch: ma/fix-snapshots-before-any-backup-destinat
---
Fixes the snapshot list before any backup destination exists (Refs #1232, Refs #234). The gateway now answers GET /v1/backups/snapshots with an empty list and an OneMind-Reason header (no backup destination yet) instead of an error or a wait on the backup agent. The dashboard restore points card and the onemind backup snapshots command say plainly that there is nothing yet and what to do, instead of failing or hanging for 60 seconds.
