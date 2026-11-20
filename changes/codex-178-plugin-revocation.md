---
pr: 408
branch: codex/178-plugin-revocation
---
Retires app-managed plugin credentials before removal or reinstall, after unsuccessful installs and during recovery of inactive workloads. A failed removal cannot reactivate an old bearer; a revocation storage failure prevents executor dispatch. Token issuance and workload Secret delivery follow separately.
