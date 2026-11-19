---
pr: pending
branch: ci/visual-vs-main
---
The browser checks no longer compare screenshots with pictures stored in the repository. On every pull request the ui-quality workflow also builds main and draws its screenshots in the same job, on the same machine, then compares the PR with them, so two dashboard PRs that change the same screen no longer break each other and can merge in any order. If no screen looks different the check passes. If some do, the run lists them, keeps the expected, actual and diff pictures in its report, and fails until a reviewer adds the visual:accepted label; adding or removing a label re-checks cheaply without redrawing anything. The 82 committed screenshots, the update_baseline run and the bot job that committed them are gone, and ui/test/visual-vs-main.sh runs the same comparison on a developer machine. Accessibility and flow checks in Chromium, Firefox and WebKit run exactly as before.
