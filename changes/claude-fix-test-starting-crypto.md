---
pr: pending
branch: claude/fix-test-starting-crypto
---
The handover test in test/unit/test_starting.py now skips cleanly when the system cryptography is older than 42 (GitHub's ubuntu-24.04 runners ship 41.x, which lacks Certificate.not_valid_after_utc), instead of erroring and turning every unit job on those runners red. The same file now also runs in CI with the gateway's own Python, so the test still runs with the pinned cryptography.
