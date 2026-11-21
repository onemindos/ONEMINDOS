---
pr: 384
branch: claude/132-update-policy
---
NMD-07 (#132): an update policy for apps on top of the maintenance windows. The owner sets a cool-off after a release, same-major-only, and a back-off that pauses auto-update of an app after repeated failed updates until the owner resumes it, plus an AI off schedule to save power (stored and evaluated; the stop and start requests are a follow-up and will wait for the owner). The knobs only hold updates back, never approve one: a held update waits for a person even under a standing approval. A dry run (GET /v1/update-policy/dry-run) answers what would update tonight and files nothing. Routes GET and PUT /v1/update-policy and POST /v1/update-policy/resume (owner only for changes), the SDKs regenerated, and the OS updates page in the dashboard (below the slots) shows and edits it through @onemind/sdk.
