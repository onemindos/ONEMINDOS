---
pr: 1334
branch: claude/core-six-sqlite-shards
---
Each PR push now runs the core SQLite suite in 6 shards instead of 3, so every PR finishes its core tests in about half the time on the 4-core CI runners. The tests are the same; conftest.py splits them by ONEMIND_TEST_SHARD=k/n for any n, and the matrix test checks every k from 1 to 6 is present once.
