---
pr: pending
branch: claude/areas-b-files-quotas
---
Files has a Storage limits tab for the owner: what each person's files use and the limit they may reach, with a field to change one person's limit (in GB, the same decimal unit the command line uses) or remove it. A limit of 0 is refused because it would stop that person saving anything. The command line side is `onemind files quotas` and `onemind files stat`, added by the CLI data groups change (#1247).
