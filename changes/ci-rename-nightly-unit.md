---
pr: pending
branch: ci/rename-nightly-unit
---
CI: security-nightly's `unit` job is now `update-unit`, ci-deploy's `lint` is `deploy-lint` and e2e's `unit` is `e2e-unit`, so a failed or cancelled run of it can no longer block a PR through main's required check named `unit` (it blocked #300). A test fails if any workflow other than the owner has a job named like a required check (dco, hygiene, lint, unit, merge-gate).
