---
pr: pending
branch: release-fix/apps-r2
---
The app-factory workflow test now expects the plan, build and verify jobs on ubuntu-24.04, which is what the workflow has used since the release fix that moved them off the local pool (registry logins and QEMU need a hosted runner). Only the expected value changed.
