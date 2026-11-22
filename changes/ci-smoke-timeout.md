---
pr: pending
branch: ci/smoke-timeout
---
CI: the image workflow's smoke job (one quick first boot before the heavy image jobs) gets 90 minutes instead of 45. On a busy KVM runner a passing smoke took about 44 minutes, so about half were cancelled at the limit and showed as failed checks; a unit test keeps the limit at 90 or more.
