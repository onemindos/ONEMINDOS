---
pr: 1331
branch: claude/pg-backup-bigint-migration
---
Upgrading the gateway widens the PostgreSQL byte counters for backup runs and the optional content tier. Large backups can record their size, and existing backup history and content settings are preserved.
