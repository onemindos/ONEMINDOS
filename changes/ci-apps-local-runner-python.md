---
pr: pending
branch: ci/apps-local-runner-python
---
The apps validate job works on the local Mac runner again: setup-python has no Python 3.13 build for its Debian 13 arm64 VM, so every PR's validate job failed before running a check. On that runner the job now uses Debian's own Python 3.13 in a venv; GitHub-hosted runners still use setup-python.
