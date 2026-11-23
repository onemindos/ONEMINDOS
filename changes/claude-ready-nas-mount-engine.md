---
pr: 950
branch: claude/ready-nas-mount-engine
---
The hub's NAS-mount engine starts (#718, part 1 of 4): internal/storage/netmount checks a mount request before anything touches the system. SMB is always SMB 3 with its own user and password (never SMB1, guest or anonymous) and NFS is always v4; admin and hidden shares, NAS system folders, IPv6 literals, loopback hosts and option syntax smuggled into a host or share are refused with a reason the owner can read. A request never prints its host, share, user or password (not in a log line, not in an error), mount output is redacted and turned into reasons the owner can act on (wrong password, share not found, old protocol, NAS unreachable), and the kernel's mount table is read to tell whether a folder is mounted. Parts 2 to 4 add the host side (credentials file in memory, mount point marker), the mount manager and the storage-socket routes.
