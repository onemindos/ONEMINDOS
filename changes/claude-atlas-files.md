---
pr: 1350
branch: claude/atlas-files
---
Gives the desktop Files window the Atlas layout (prototype 07). A sidebar lists the spaces this person can open and Photos, the owner's disks with their SMART health and temperature, where the backup copies are kept, and machines that cannot be reached. There is no per-file copy count yet: a file's modified time can be backdated (Samba, rsync, a restore), so the count returns once the file list carries ctime. Instead the sidebar and footer say when the last backup run to the primary destination that carried Files started, or that backups need attention, and name the other destinations as daily and not checked here. A footer line totals the items and size, and a drop zone uploads dropped files with the same resumable upload as the Upload button. Roles that may not read backups or disks see neither part, and nothing is guessed.
