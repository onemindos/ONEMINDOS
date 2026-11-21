---
pr: pending
branch: claude/232-status-generated
---
Adds `scripts/changes.py audit`, which compares every STATUS epic row with the real GitHub state of its PR and lists rows that provably drifted (says review or in-progress but the PR is merged, says done but the PR is open, PR closed unmerged). The nightly changes-collect job now runs it and writes the result to its job summary. On today's STATUS it finds 19 stale rows. It reports only and never edits rows.
