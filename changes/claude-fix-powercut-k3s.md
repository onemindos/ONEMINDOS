---
pr: pending
branch: claude/fix-powercut-k3s
---
A power cut in the first minute after a hub's first boot no longer kills k3s for good (VM 501 test, bug 1). First boot now writes its files durably (temp file, fsync, rename, fsync of the folder) and syncs /data before it marks the box configured; a new onemind-k3s-settle unit keeps syncing /data while k3s starts for the first time and marks the first setup done once k3s answers. Before every k3s start, damaged k3s state (empty certificates, tokens or node password) is moved aside, never deleted, and k3s makes it again, without touching the owner's data, the apps' volumes or the gateway database. If the owner's apps are already in the cluster, nothing is moved automatically: it logs, alerts and shows the state on the rescue console, where the owner approves Reset k3s state. New pre-registered QEMU criteria F13 and F14 (make powercut) cut the power 25 s after first boot and after emptying k3s's files. Refs #234.
