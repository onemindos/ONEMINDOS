---
pr: pending
branch: claude/r530-runner-instances-cap
---
CI-14: the R530 KVM runner kit now allows 1 to 16 job VMs (was 6). A new `instances-check` runs before any VM starts and refuses a count whose last job VM address or VM id would leave its range or reach the template, that needs more than host RAM minus 16 GiB (8 GiB per VM), or more than 2x the host threads (4 vCPU per VM).
