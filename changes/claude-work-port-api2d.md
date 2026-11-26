---
pr: 1139
branch: claude/work-port-api2d
---
Work part 2d, ported from #798 onto the Work engine: the Work screen now has Today, Upcoming, Inbox and All views, a quick-add line ("Pay rent tomorrow at 5pm #Home @bills p1", read in the browser's time zone) and a Done button that uses the task's revision, so a task changed elsewhere reports a conflict instead of being overwritten. The TypeScript SDK client accepts PATCH and DELETE.

The Today and Upcoming views now end at midnight in the browser's (or CLI machine's) time zone, sent as `tz`, instead of UTC midnight.
