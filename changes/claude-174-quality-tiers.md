---
pr: 996
branch: claude/174-quality-tiers
---
APPS-02 (#174): quality tiers for apps and plugins, Bronze, Silver and Gold. The app gate computes the tier from its own evidence (the scan, the manifest, non-root, upstream health) and writes it to `scan.json` as `quality`, with the yes/no checks behind it; no manifest field sets it, and a committed claim above what the gate computes fails the pull request. The gateway derives the tier again from the checks, serves it in `GET /v1/apps` under `scan.quality`, and the Market shows a quality pill on each card, the checks on the app page, and a quality filter. A scan from before this field shows "Not rated yet" until the next gate run. Stacked on #867 (licence classes: Bronze needs a green licence).
