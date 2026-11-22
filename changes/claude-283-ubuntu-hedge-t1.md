---
pr: pending
branch: claude/283-ubuntu-hedge-t1
---
The Ubuntu 26.04 CI hedge no longer fails T1 on the RAUC version check. Cause, read from the nightly run 44740692617 serial log: Ubuntu's newer systemd writes a shell-integration mark (an OSC 3008 escape sequence) on the console right before each command's output, so the harness saw "ESC]3008;...ESC\rauc v1.15.2" and its line-anchored match for "rauc 1.15.2" failed even though the image holds the right RAUC (T0 and the image build checks passed). The QEMU harness now strips those marks from guest command output. The TD1 to TD3 failures read the same way (every check anchors on the start of a line) and should clear with it, which only the nightly run can confirm. Debian images do not emit the mark, so that leg is unchanged.
