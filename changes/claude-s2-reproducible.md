---
pr: 1089
branch: claude/s2-reproducible
---
Reproducible OS build (Step 2 of the Debian bones, PR 8): two from-scratch builds of one commit now give the same rootfs tar and the same rootfs.ext4. SOURCE_DATE_EPOCH is the pinned snapshot's own timestamp, the root filesystem gets a fixed UUID and directory hash seed, the gateway's Python bytecode is keyed to its source instead of build time, and build-run leftovers (random machine id, ldconfig cache, alternatives log) are dropped. `make repro-check` and a CI job build twice and compare.
