---
pr: pending
branch: claude/perf-budget-gateway-120
---
The idle gateway memory ceiling in the performance budget is 120 MiB instead of 100 MiB, a founder decision after new features grew the gateway to about 114 MiB with no leak; follow-up work will bring it back down.
