---
pr: pending
branch: ci/core-parallel
---
ci-core runs in parallel. SQLite and PostgreSQL are separate jobs, the slow PostgreSQL leg is split into three shards, and every job runs pytest-xdist on all runner cores with its own PostgreSQL database per worker. A new push to a PR cancels its older run. Same tests, under 20 minutes instead of about 2 hours (CI-03, issue 228).
