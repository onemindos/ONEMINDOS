---
pr: 1132
branch: claude/plg-git-01-custom-app
---
Deploy a custom app from a Git repository: the gateway fetches a ref in the sandbox, checks it like a Market app and records a revision, an owner approves the install or update, and `onemind app rollback` returns to the previous revision. Adds `onemind app deploy`, `rollback` and `history`, the `/v1/custom-apps` routes and Market > Custom apps.
