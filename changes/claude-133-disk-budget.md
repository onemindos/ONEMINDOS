---
pr: pending
branch: claude/133-disk-budget
---
NMD-08 (#133): offline-aware image cleanup and a disk budget. A new hub unit, onemind-images.service (onemindd images, internal/imagegc), removes only superseded container images and never those of an installed app, stopped or not, so an offline box can start every app again (tested). It runs daily and at once when the image disk passes the box budget (default 80 %, below kubelet's 85 %), reports an images object in the heartbeat, and the gateway warns the owner with the disk.budget_near alert before the budget fills (default 70 %).
