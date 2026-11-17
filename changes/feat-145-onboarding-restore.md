---
pr: pending
branch: feat/145-onboarding-restore
---
First slice of UMB-P08: the first-run wizard can list what a backup holds. A new owner-only, read-only, audited route POST /v1/onboarding/restore/candidates lists the restore points on a configured backup destination, one entry per backup run with its apps and system snapshot, and refuses a box that already has apps. The backup agent's signed snapshots job takes an optional box id and the owner recovery key from the kit, so a new box can open the old box's repository (sealed with that box's own device key) and list its restore points when moving to new hardware; the key is held in a short-lived 0600 file, never logged or audited, and this path never creates a repository. The restore itself, the wizard screen, drain a node, stuck-app Repair and the VM test are not done yet.
