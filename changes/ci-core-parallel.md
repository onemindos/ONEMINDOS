---
pr: 264
branch: ci/core-parallel
---
ci-core runs in parallel. The suite is split into seven jobs, three for SQLite and four for PostgreSQL, and every job runs pytest-xdist on all runner cores with its own PostgreSQL database per worker. A new push to a PR cancels its older run. Same tests, about 20 minutes per job instead of about 2 hours in one job (CI-03, issue 228).
