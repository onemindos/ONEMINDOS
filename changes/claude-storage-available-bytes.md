---
pr: pending
branch: claude/storage-available-bytes
---
Measured free space for the data set (Refs #841): the storage service now reads `btrfs filesystem usage -b` and reports `available_bytes`, the space a person can still write after mirroring (the smaller of btrfs's documented Free (estimated) and Free (statfs, df) figures), and `GET /v1/storage` forwards it as a nullable, documented field in the OpenAPI spec. Null means unknown and is never estimated from the members, whose sizes count mirrored data twice; on a set mounted degraded the statfs figure keeps the missing disk's space out. `onemind storage status` shows it. Tests replay real Debian 13 recordings of a raid1 set, a single disk and a degraded set, plus the unknown cases.
