---
pr: 264
branch: ci/core-parallel
---
ci-core runs in parallel. The suite is split into seven jobs, three for SQLite and four for PostgreSQL, and every job runs pytest-xdist on all runner cores with its own PostgreSQL database per worker. Each job takes under about 20 minutes, where the old single job took about 2 hours (CI-03, issue 228). To save the org's 20 shared runners, a PR push runs only the three SQLite jobs; the four PostgreSQL jobs run once per merge in the merge queue, and pushes to main run all seven. A new push to a PR cancels its older run.
