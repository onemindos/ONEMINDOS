---
pr: 1183
branch: claude/fix-bootlock-b2-gate
---
Fixes the boot menu lock check B2 failing on an unmodified image (#1150), without weakening it. B2 reboots a configured box; on that normal (committed) boot the health gate decides at once and nothing orders it against the first-boot service, so its "HEALTH-GATE ... RESULT" line can be printed before "already configured". The harness searched for the gate line only after "already configured", missed it, and failed after 1800 s. B2 now searches for the gate line from the reboot on, as B1 and the edge and cloud tests already do; both lines are still required and must come from the new boot. New unit tests in test_bootlock.py feed both line orders to the real harness code.
