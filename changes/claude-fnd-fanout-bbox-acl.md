---
pr: 998
branch: claude/fnd-fanout-bbox-acl
---
The live event stream no longer reveals a hidden location through bbox=. Before, the map filter placed an asset using a position taken from any of its values, before the caller's asset filters ran, so a person allowed to see a camera's status but not its location (design rule 8) could narrow the box and watch whether the status showed up. Each stream now places an asset only from values that person may see, the caller's filters run before the box, and a removed value no longer keeps its position. Follow-up to PR #959, issue #606.
