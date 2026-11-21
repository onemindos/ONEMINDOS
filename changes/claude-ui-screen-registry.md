---
pr: pending
branch: claude/ui-screen-registry
---
Dashboard screen registry: each screen and each Settings sub-page now declares itself in its own file under dashboard/src/screens, and the routes, dock, Launchpad, sidebar, Pro gating and tile colours read that registry instead of hand-kept lists, so a new screen no longer edits the same shared files as every other open PR. No behaviour change.
