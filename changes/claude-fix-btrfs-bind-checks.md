---
pr: pending
branch: claude/fix-btrfs-bind-checks
---
Fixes the first-boot smoke checks F16, F16r, F16u and NW4 on the btrfs data layout. On btrfs /data is the default subvolume @, so a bind mount of /data/state/... shows its root as /@/state/... instead of /state/.... The checks compared with a fixed /state/... path and failed although the binds were correct. They now compare with where /data itself starts, so ext4 and btrfs both pass and a bind of the wrong folder still fails. Unit tests cover both layouts.
