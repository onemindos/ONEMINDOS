---
pr: pending
branch: claude/p0-daily-driver-gate-script
---
Adds the daily-driver gate kit lab-kits/LT-X86-DD: one controller-side script that checks a OneMind box for daily use (install and TLS ready time, Debian 13 and read-only root, passkey registered, G1 rollback result, power-pull results, port scan, restore timing, load budget) and writes a pass or fail evidence file with timings, with unit tests. It has not run on the R530 VM or the Dell yet.
