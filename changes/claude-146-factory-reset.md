---
branch: claude/146-factory-reset
pr: pending
---
Factory reset, the box's half. A new fast wipe for the data disks: the host service can now list exactly what a reset would erase (every disk of the encrypted data set, what is erased, what survives) with a warning that restoring off-box backups afterwards needs the printed recovery key, and the owner's approval is bound to that exact plan by its hash. After approval the box arms a marker on the boot partition and restarts; an early-boot unit destroys the encryption keys of every member of the set before the data is ever opened, and refuses (recovery mode, old data never mounted) if the marker is stale or the wipe fails. If the data disk is not encrypted yet the reset refuses with that reason instead of pretending or falling back to a slow overwrite. The gateway and dashboard side follows once the system controls and host link PRs merge.
