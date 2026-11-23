---
pr: 990
branch: claude/ready-nas-mount-host
---
The NAS-mount engine gets its host side (#718, part 2 of 4): the mount command line forces SMB 3 or NFS 4 and soft, nosuid, nodev and noexec mounts and never carries a password; the SMB password goes into a 0600 credentials file with a fresh random name in a folder that must be in memory (tmpfs), so it never reaches a disk or a command line; a mount point holds a marker file while nothing is mounted and one with files written into it is refused; mount and umount run with an empty environment and their output is redacted before it is logged; a hub folder such as /, /etc or /data is never a mount base, and a hub without cifs-utils or nfs-common says so. Part 3 puts this to work in the mount manager.
