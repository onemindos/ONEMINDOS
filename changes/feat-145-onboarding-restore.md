---
pr: pending
branch: feat/145-onboarding-restore
---
First slice of UMB-P08: the first-run wizard can list what a backup holds. A new owner-only, read-only, audited route POST /v1/onboarding/restore/candidates lists the restore points on a configured backup destination, one entry per backup run with its apps and system snapshot, and refuses a box that already has apps. The backup agent's signed snapshots job takes an optional box id so a new box can list the old box's restore points when moving to new hardware. The restore itself, the wizard screen, drain a node, stuck-app Repair and the VM test are not done yet.
