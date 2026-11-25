---
pr: 1157
branch: claude/fix-powercut-durable
---
A power cut in the first minute after a hub's first boot no longer leaves k3s's files empty or its freshly unpacked images torn (VM 501 test, bug 1, part 1 of 2: durability). First boot writes its files atomically and durably (temp file, fsync, rename, fsync of the folder) and syncs /data before it marks the box configured. /data is mounted with nodelalloc on every board, so a file's data reaches the disk before the metadata that names it, and containerd's and sqlite's own fsyncs carry the files written before them. A new onemind-k3s-settle unit keeps syncing /data while k3s starts for the first time and marks the first setup done once the OS's own pods are up. New pre-registered QEMU criterion F13 (make powercut, CI image workflow) cuts the power 25 s after first boot. Repairing k3s state that is already damaged follows in the stacked recovery PR. Refs #234.
