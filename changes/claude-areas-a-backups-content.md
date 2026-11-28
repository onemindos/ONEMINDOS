---
pr: pending
branch: claude/areas-a-backups-content
---
Two backup views that had an API and no screen now have one. Backup checks: the Backups page lists every restore test and repository check and what it found, and has an Ask for a check button that files the request for an owner to approve. Downloadable content: it lists the apps whose large re-downloadable files can be added to backups, shows the size before anyone decides, and files the include or leave-out request carrying that size so the gateway refuses it if the content grew meanwhile. The same is in the command line as `onemind backup verifications` and `onemind backup content` (list, set with include or leave-out); nothing here approves anything.
