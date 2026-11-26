---
pr: pending
branch: claude/fix-e2e-wizard-heading
---
The golden-path and spatial end-to-end suites look for the first-run wizard by its visible step title again. The Atlas first run (PR #1071) made "Set up OneMind" the page's hidden level-1 heading and each step title a level-2 heading, so sign-in in both suites waited for a level-1 "Name your box" that no longer exists and every test that signs in failed.
