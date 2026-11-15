---
pr: pending
branch: feat/141-backups-dashboard
---
Add a Backups page using the generated SDK transport and gateway backup status, destination and run routes. Show reported protection and restore verification without claiming an unverified backup is safe. Explicit confirmation files a whole-box backup request with approval disabled; ambiguous replies retain the exact request identity across in-tab navigation. Route legacy backup settings links to the page and remove only Backups from Coming soon. This is the Backups slice of issue 141; other pages remain separate work.
