---
pr: pending
branch: claude/p0-ceremony-guided-script
---
Adds scripts/ceremony-guide.py, an interactive plain-language guide for the offline root-key ceremony (D-010): it refuses online machines, CI and dirty or wrong commits, runs the existing tuf-bootstrap-root.sh steps for three holders, verifies each result, prints the sheet and what to do with each stick, resumes after an interruption, and has a rehearsal mode on throwaway keys.
