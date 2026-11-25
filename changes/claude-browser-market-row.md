---
pr: pending
branch: claude/browser-market-row
---
The Market gets a Browsers row with Firefox and Chromium apps: Neko 3.2.0 images pinned by digest, run as a non-root user with no sudo and no terminal, a 1 GB shared-memory volume, a memory request of 1 GB, a generated login, and a web port that is only reachable through the gateway proxy. Installing one is a request that waits for the owner in Approvals. Chrome and Edge are not offered because of their licences, and a test fails if they appear. The app gate has not scanned the images yet, so both apps stay at the community tier.
