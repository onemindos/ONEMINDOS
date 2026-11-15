---
pr: pending
branch: fix/117-app-gate
---
App-gate summaries retain explicit failure findings when the job's exit status was not recorded, rather than misreporting completed vulnerability scans as setup errors. Interrupted gate output remains visible and a missing exit status can never count as a pass. Part of #117; no scan threshold or app tier changes.
