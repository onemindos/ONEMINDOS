---
pr: pending
branch: claude/e-275
---
deploy/install.sh starts the apt-daily timers as its last step instead of during the package step. On a machine where they were off, such as a CI runner, the upgrade timer could fire at once and unattended-upgrades could replace systemd or D-Bus while a later `systemctl` call was waiting, which made the hub install die with "D-Bus connection terminated" (the perf-smoke flake, #275). When the install fails, perf-smoke now also prints the package upgrades and apt timer runs that happened during it.
