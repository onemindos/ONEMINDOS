---
pr: 837
branch: claude/e-324
---
Test reliability (#324): the T-battery's TD3 could read a cut-off recovery decision ('f' instead of 'fell-back') because the RECOV match fired before the serial line ended. `VM.expect_line()` waits for the line's newline and matches again from the same start; `recovery_check`, the dataenc recovery wait and `wait_gate` use it. The checks themselves are unchanged. A unit test feeds the line in split chunks and fails without the fix.
