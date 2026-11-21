---
pr: 496
branch: ci/unit-old-cryptography
---
The `unit` check no longer fails on GitHub-hosted Ubuntu runners: the one rescue-console test that makes the box CA skips when the system `cryptography` lacks the `*_utc` accessors, the same guard `test_firstboot.py` already uses (the gateway venv, where these tests matter, pins a newer version).
