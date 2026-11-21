---
pr: pending
branch: ci/unit-old-cryptography
---
The `unit` check no longer fails on GitHub-hosted Ubuntu runners: the rescue-console CA tests skip when the system `cryptography` lacks the `*_utc` accessors, the same guard `test_firstboot.py` already uses (the gateway venv, where these tests matter, pins a newer version).
