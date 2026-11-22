---
pr: 917
branch: claude/e-ci-noise-fixes
---
The local visual check (ui/test/visual-vs-main.sh) now builds the base the way CI's ui-quality job does. It generates the SDK schema before the base dashboard build, because the schema is no longer committed (CI-16) and a fresh base worktree without it failed to build, so no dashboard screen, dash-market in WebKit included, got a reference picture. It redraws a base screenshot that failed once, as CI does, and its default base is the branch PRs merge into (release/next while it exists). A new browser-free check, e2e/visual-vs-main.spec.ts, fails when the script and the workflow drift apart again. No baseline image changed: none are committed since CI-17.
