---
pr: pending
branch: ci/api-fuzz-nightly-timeout
---
The nightly and manual API fuzz run (400 generated cases per operation, ten times the PR budget) now has 180 minutes instead of 45; the first full run on main was cancelled at the 45-minute limit before it finished. Pull requests keep 45 minutes.
