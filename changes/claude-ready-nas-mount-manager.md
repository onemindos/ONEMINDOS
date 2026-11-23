---
pr: pending
branch: claude/ready-nas-mount-manager
---
The NAS-mount engine can mount, check and unmount a share (#718, part 3 of 4): every mount is first made read-only and read, then made with the access asked for, and a test mount that cannot be released is never covered by the real one. A repeated request for the mount in place changes nothing, but one that changes the protocol, NAS, share, user or access detaches the mount in place first and mounts the new one, so an owner who narrows a share from read-write to read-only never keeps a writable mount. A NAS that goes away reads as failing and as mounted again when it is back, a mount that cannot be released reads as failing (busy), and reading an id that was never mounted records nothing, so a stray read never shows up as a failing NAS. Part 4 offers it on the storage socket.
