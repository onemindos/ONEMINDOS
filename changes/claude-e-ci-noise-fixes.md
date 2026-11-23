---
pr: 917
branch: claude/e-ci-noise-fixes
---
The local visual check (ui/test/visual-vs-main.sh) now builds the base the way CI's ui-quality job does. It generates the SDK schema before the base dashboard build, because the schema is no longer committed (CI-16) and a fresh base worktree without it failed to build, so no dashboard screen, dash-market in WebKit included, got a reference picture. It redraws a base screenshot that failed once, as CI does, and its default base is the branch PRs merge into (release/next while it exists). Whole-page screenshots get 20 s instead of 5 s for their two matching captures: dash-market in WebKit timed out on its second capture while the base was drawn (1 of 3 runs), so it got no reference and showed as changed; the pixel threshold is unchanged. A new browser-free check, e2e/visual-vs-main.spec.ts, fails when the script and the workflow drift apart again. No baseline image changed: none are committed since CI-17.
