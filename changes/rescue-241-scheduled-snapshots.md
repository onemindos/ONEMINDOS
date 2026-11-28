---
pr: 833
branch: rescue/241-scheduled-snapshots
---
Files can restore earlier file versions from the image's Snapper storage timeline (BAK-04, #241). On btrfs hubs the live Files tree moves into the snapshotted storage subvolume while gateway, Samba and backup paths stay stable. Ext4 hubs keep their existing Files layout. Members can restore a copy as a new file, and administrators can inspect the timeline with `onemind snapshots`. Files links to off-box Backups and explains that snapshots can retain copies after trash is emptied.
