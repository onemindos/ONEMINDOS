---
pr: 1350
branch: claude/atlas-files
---
Gives the desktop Files window the Atlas layout (prototype 07). A sidebar lists the spaces this person can open and Photos, the owner's disks with their SMART health and temperature, where the backup copies are kept, and machines that cannot be reached. The file list gains a Copies column read from the backup status: a file counts the box plus every backup destination only when backups are healthy, the last successful snapshot carried the Files built-in and the file changed before it; otherwise it shows one copy and the time of the next run. A footer line totals the items and copies, and a drop zone uploads dropped files with the same resumable upload as the Upload button. Roles that may not read backups or disks see neither, and nothing is guessed.
