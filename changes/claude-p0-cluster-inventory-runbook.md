---
pr: pending
branch: claude/p0-cluster-inventory-runbook
---
Cluster replacement runbook: a compressed phase plan (freeze and prove backups, agent, small apps, worker and data, message-bus authority flip last, decommission) and a target table that gives every workload class on a hosted cluster a place on the box (Market app, OS part, private deploy, or archive and drop), with a test that checks every row. Written from a read-only inventory; no names, hosts or secrets in the repo. Linked from the migrate kit README.
