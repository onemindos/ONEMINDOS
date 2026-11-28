---
pr: pending
branch: ci/apps-gate-parallel-30
---
App checks on the KVM droplet pool now run 48 at a time instead of 12. A pull request that touches every Market app (about 80 checks at 20-30 minutes each) finishes in about 45 minutes instead of two and a half hours, and the pool keeps 60 runners, so other jobs still get runners.
