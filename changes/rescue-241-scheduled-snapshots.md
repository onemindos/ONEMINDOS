---
pr: 833
branch: rescue/241-scheduled-snapshots
---
Files keeps earlier versions of your files (BAK-04, #241). An administrator turns on hourly and daily read-only btrfs snapshots of the Files root with retention; the image ships the schedule (`onemind-snapshots.timer`, running `/usr/bin/onemindd snapshots-tick` only after opt-in). In Files, a member opens a file's preview, picks "Previous versions" and restores yesterday's copy as a new file beside the current one, never over it (`GET /v1/files/versions`, op `restore_version`). Only people restore; apps and agents are refused. The page says snapshots share the disk, so they are not backups, and links to Backups. `onemind snapshots` lists the versions for an administrator.

Also: the App CI gate generates the Go SDK code before it builds the `onemind` plugin validator (it failed on any PR touching `cmd/onemind`), and the window "send to workspace" button names its visible workspace number, so the accessibility check passes.
