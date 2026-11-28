---
pr: 1350
branch: claude/atlas-files
---
Gives the desktop Files window the Atlas layout (prototype 07). A sidebar lists the spaces this person can open and Photos, the owner's disks with their SMART health and temperature, where the backup copies are kept, and machines that cannot be reached. The file list gains a Copies column read from the backup status and runs: a file counts two copies, the box and the primary backup destination, only when a run to the primary that carried the Files built-in started after the file last changed; otherwise it shows one copy and the time of the next run. Other destinations, which get a daily run, are named but never counted. A footer line totals the items and copies, and a drop zone uploads dropped files with the same resumable upload as the Upload button. Roles that may not read backups or disks see neither, and nothing is guessed.
