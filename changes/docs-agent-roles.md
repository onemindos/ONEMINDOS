---
pr: 257
branch: docs/agent-roles
---
Splits the parallel build into three seats in docs/leap/AGENT-QUEUE.md: Codex in Hermes as the workhorse (up to 4 parallel workers, one per code area), a Claude builder for CI, OS, update and security work, and an Opus gate that reviews every PR and alone queues merges. Adds the hand-off labels (builder, needs-review, review approved or changes) and one copy-paste prompt for each seat.
