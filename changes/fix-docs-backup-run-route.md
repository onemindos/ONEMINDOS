---
pr: pending
branch: fix/docs-backup-run-route
---
Docs now match the code after #91 removed the unsigned POST /api/v1/backup/run route: BACKUPS.md (section 6.1 and the K2 row), the CONTRACT-12 draft, sdk/contracts/poc-v0.md (section 12.12) and internal/backup/README.md say that runs start only as gateway-signed backup.run jobs on POST /api/v1/backup/jobs, and that the updater's pre-update run still has to be wired that way.
