---
pr: 1182
branch: claude/fix-qemu-reboot-hang
---
Fixes the first-boot QEMU check F3 hanging for 30 minutes after a reboot on fast build machines (#1159), without weakening it. On a normal (committed) boot the health gate decides at once, and nothing orders it against the first-boot service, so its "HEALTH-GATE ... RESULT" line can be printed before "already configured". The harness waited for "already configured" first and then searched for the gate line only after it, so it missed that boot's one gate line and waited out the 1800 s timeout. F3 now searches for the gate line from the reboot on, the way F1, the edge test and the cloud test already do; both lines are still required and must come from the new boot. New unit tests feed both line orders to the real harness code.
