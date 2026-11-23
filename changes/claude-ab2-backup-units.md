---
pr: 937
branch: claude/ab2-backup-units
---
Backups now know each built-in's own data (#616). The backup set is the gateway database plus every switched-on built-in's declared tables and folders, shown in GET /v1/backups/status as builtin_units (whether each folder is set, never its host path); a box run reports a built-in whose declared table is missing as a failed unit. A new export writes those units in a portable form (one JSON-lines file per table with its checksum, plus the folders with hard links kept) and a restore replays them on a fresh box in one database transaction: it refuses an undeclared table or folder, a changed file, another schema version, a table that already holds rows (unless asked to replace) and a folder that is not empty. On the box: python -m onemind_core.backups.units list, export or restore; export --tar - is the stream the backup agent's command hook can keep.
