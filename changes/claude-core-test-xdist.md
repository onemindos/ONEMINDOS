---
pr: 1333
branch: claude/core-test-xdist
---
The core test target now passes PYTEST_ARGS to pytest, so CI's parallel flags (-n auto --dist loadgroup) take effect; since 2026-11-14 they were silently dropped and every core shard ran on one core, reaching the 60-minute limit. With the suite parallel, a loaded runner exposed a short SQLite lock wait, so the gateway now waits up to 30 seconds (was 5) for another writer before answering "database is locked", which also protects a busy home box. No test is skipped or loosened; a new test checks the lock wait.
