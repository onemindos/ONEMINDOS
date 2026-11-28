---
pr: pending
branch: claude/fix-backup-bigint
---
Backups: content-tier sizes and run byte counts are stored as 64-bit numbers, so switching on the content backup of an app larger than 2 GiB no longer fails on PostgreSQL (found by the landing PR #810 in main's merge queue).
