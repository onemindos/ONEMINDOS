---
pr: pending
branch: ci/go-fuzz-deadline-flake
---
The Go fuzz job no longer fails a clean run when Go's fuzz engine reports "context deadline exceeded" while shutting down at the end of its time budget. Only that exact error with no failing input written passes, with a warning; any real finding still fails the job and saves its input.
