---
pr: pending
branch: claude/perf-gateway-write-path
---
Gateway write path: the audit log now group-commits (concurrent writers share one fsync, each event is still on disk before its request is acknowledged, hash chain unchanged) and the file-backed SQLite database runs in WAL mode with synchronous FULL, so readers no longer wait for writers and a commit costs one disk sync instead of several. FULL is kept on purpose: the database also holds revocations and single-use markers (agent tokens, fabric tickets, sessions) that are not rebuilt from the audit log, so every acknowledged commit must survive a power cut. Adds a write-path regression test.
