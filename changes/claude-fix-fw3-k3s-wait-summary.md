---
pr: 1108
branch: claude/fix-fw3-k3s-wait-summary
---
Battery T5 firewall test (FW3) now waits, bounded to 10 minutes, for k3s to listen on 6443 and 10250 before it scans the box. The scan used to start about one minute after first boot, before k3s was up, so FW3 saw no listeners. The CI job-summary renderer test/qemu/summary.py no longer fails on results files that lack env or upto.
