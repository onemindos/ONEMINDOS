---
pr: 833
branch: rescue/241-scheduled-snapshots
---
Files can restore earlier file versions from the image's Snapper storage timeline (BAK-04, #241). On btrfs hubs, the schedule captures the live Files subvolume at its existing path so that both OS slots can read and write it after a rollback. Ext4 hubs keep their existing Files layout. Members can restore a copy as a new file, and administrators can inspect the timeline with `onemind snapshots`. Files links to off-box Backups and explains that snapshots can retain copies after trash is emptied.
