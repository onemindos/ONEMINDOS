---
pr: 1212
branch: claude/ci-apps-changed-only
---
ci-apps no longer queues a gate job for every Market app (about 80) on pull requests that change no app. A pull request into release/next now gates only the apps whose apps/<id>/ files it changes (plus apps whose licence-matrix rows change), and every app only when it changes a shared gate input listed in sdk/tools/applib/selection.py (the gate tools, their pinned tools and packages, the app schema, the workflow). With no app change the gate job is skipped and the run still passes. A landing into main, the merge queue, a new nightly run on release/next and a manual run still gate every app, and every run still validates every manifest. The plan is now a tested command (sdk/tools/app-select plan), and test/unit/test_ci_apps_plan.py locks the wiring in (founder decision 2026-11-25).
