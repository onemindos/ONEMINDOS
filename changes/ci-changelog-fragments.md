---
pr: pending
branch: ci/changelog-fragments
---
Change fragments: a PR now adds `changes/<branch>.md` instead of editing the shared CHANGELOG.md and docs/leap/STATUS.md rows, which made every merge conflict with every other open PR. New `scripts/changes.py` (`check`, `render`, `collect`), a fast CI check plus a soft warning for direct CHANGELOG edits, a weekly/manual `changes-collect` workflow that pushes to `bot/changes-collect`, and `merge_group` triggers on ci and hygiene so a merge queue can be turned on later. Format: `changes/README.md`.
