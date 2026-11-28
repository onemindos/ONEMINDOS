---
pr: 1357
branch: claude/fix-1148-backup-roots
---
Backups now carry the owner's files on the @storage subvolume. On a btrfs box the image mounts @storage at /data/storage, but the backup agent's system unit listed only the settings, the box CA, the NATS keys, the built-ins' export and /data/onemind/files, so anything kept in /data/storage was in no backup. onemind-firstboot now adds /data/storage to the system unit on a box that has it, leaves out snapper's /data/storage/.snapshots (on-disk undo copies that restic would otherwise walk on every run), and adds both to an existing hub's agent.json on its next boot. onemindd's backup sandbox may now write /data/storage so a restore can put the files back. An ext4 box installed before the btrfs layout has no /data/storage and is unchanged, because a missing source would fail the whole unit. One path in firstboot is checked against the mount unit, snapper's config and data_encrypt.py, so they cannot drift apart again.
