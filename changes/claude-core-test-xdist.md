---
pr: 1333
branch: claude/core-test-xdist
---
The core test target now passes PYTEST_ARGS to pytest, so CI's parallel flags (-n auto --dist loadgroup) take effect. Since 2026-11-14 the flags were silently dropped and every core shard ran on one core, growing to 54-60 minutes and hitting the 60-minute limit. No test is skipped or changed.
