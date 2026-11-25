---
pr: 1086
branch: claude/fix-firstboot-reds
---
Fixes two first-boot test reds on release/next. F0 now reads the expected NATS server version from os/versions.lock.yaml (the same pin the image build uses) instead of a hard-coded v2.15.2, so the next NATS bump cannot break it. F10 (back-merged from main) accepts the rescue console as started at runtime but not enabled, which is how the read-only image runs it (F0 requires that only onemind-firstboot is enabled). The core test jobs get a 60-minute safety timeout instead of 40.
