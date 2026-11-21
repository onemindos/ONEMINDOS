---
pr: pending
branch: claude/ui-migrate-wizard
---
A "Move from a cluster" window in the dashboard for the migration kit (CORE-DEPLOY-6): plan from an old cluster's kubeconfig, preview the helper pod, then request import, copy, cutover and revert. Every step files an approval request bound to its exact choices, with live progress and a link to Approvals. The 409 refusals are shown in plain words (a Market app id, a name already installed, an old cluster that is not live). The kubeconfig is held in the tab only and sent only with the step that needs it.
