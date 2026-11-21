---
pr: pending
branch: claude/perf-gateway-write-path
---
Gateway write path: the audit log now group-commits (concurrent writers share one fsync, each event is still on disk before its request is acknowledged, hash chain unchanged) and the file-backed SQLite ledger runs in WAL mode with synchronous NORMAL, so readers no longer wait for writers and a commit no longer costs several disk syncs. Crash window: after a power cut the ledger may lose its last few commits (never corrupt) while the audit log keeps every acknowledged line. Adds a write-path regression test.
