---
pr: pending
branch: claude/163-restore-drill
---
BAK-02 whole-box restore drill, first slice: a harness under test/restore-drill that backs up a box with real data (a file, a payload, a database) to a virtual USB disk, destroys it, boots a clean Debian 13 VM, installs OneMind, restores with only the disk and the owner key, and checks the data byte for byte. The clock covers install, restore and verify, and a run over 60 minutes or with any wrong byte fails. The judging core is unit-tested; a monthly KVM workflow (restore-drill.yml, informational) runs the VM drill. The restore uses plain restic with the owner key until onemind init --restore (UMB-P08) exists. Not yet run end to end.
