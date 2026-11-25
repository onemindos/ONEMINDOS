---
pr: pending
branch: claude/apps-rescan-release-next
---
The daily apps-rescan bot now checks out release/next in every job and opens its pull request against release/next instead of main, so its scan.json, tier and README updates land with all other work and reach main through the release/next landing PR. A leftover open bot PR that targets another base is closed and replaced on the next run.
