---
pr: pending
branch: claude/ready-nas-mount-socket
---
The storage service offers NAS mounts on its local socket (#718, part 4 of 4): onemindd storage serve answers GET, PUT and DELETE under /v1/netmounts behind the socket's peer check, with --net-base and --net-owner flags (SMB files belong to the gateway's user so Files can read them). A request body is never echoed, logged or quoted in an error, and the routes stay off on a hub whose mount folder is not set. An acceptance script runs the engine against real Samba and NFS servers in a throwaway Debian 13 container and proves the password is never on any command line, in a log or left in a file, that a wrong password is named as such, and that a killed server reads as failing and then as mounted again. The gateway side (net: roots in Files, the owner-approved action, sealed input) comes in the next PR on #718.
