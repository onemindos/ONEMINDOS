---
type: fixed
area: core
---
Backups: content-tier sizes and run byte counts are stored as 64-bit numbers, so switching on a backup of an app's content larger than 2 GiB no longer fails on PostgreSQL.
