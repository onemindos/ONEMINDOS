---
pr: pending
branch: claude/fix-restore-drill-app-install
---
The backup and restore drills install a small test app (backup-probe) that had fallen behind the app schema: it lacked the age_rating and licenceClass fields that became required, so the gateway skipped it, filing app.install answered 404 unknown app, and the restore drill stopped before any backup ran. The fixture now carries both fields, a new sdk/tools test loads it through the gateway's own catalog so a later schema change fails in ci-apps instead of in a VM run, and the drill prints the gateway's error body when an install cannot be filed.
