---
pr: 76
branch: feat/migrate-kit
status_rows:
  - CORE-DEPLOY-6 | review | onemind migrate role/plan/import/copy/cutover/revert
---
Migration kit (CORE-DEPLOY-6): `onemind migrate role/plan/import/copy/cutover/revert` moves a namespace of an existing Kubernetes cluster onto the box as a private app. The plan reads the namespace with GET only through an owner-provided kubeconfig (never Secrets) and prints a dry-run report; import, copy, switch-over and revert are owner-approved actions. Data moves with a restic helper pod into an append-only repository on the gateway and is checked file by file (sha256) before old and new run side by side; switch-over stops the old writers, copies the last changes and checks them again. Extends the feature-action mechanism in `actions.py` with claim, release and background runs, and adds a Lima e2e on pinned k3s. Guide: `docs/leap/core/MIGRATE.md`.
