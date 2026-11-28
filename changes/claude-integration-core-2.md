---
pr: 1166
branch: claude/integration-core-2
---
Lands seven approved PRs that the merge train skipped because they collided on release/next: gateway permissions 5 and 6 (no wildcard standing approvals, stored taint and exposed agents), the whole-system log viewer, and Work port part 2 (projects, comments, sections, repeat rules, reminders and the Today, Upcoming and Inbox views). The combination fixes keep person-filed requests and the fabric's node.join request untainted while any other request from a node token counts as exposed (a node token may hold actions:request, so it gets the taint check agents get), register the Work member route scope, refuse a child or teen at Work member adds and section changes with an audit record, and list the log viewer as a streamed-text transport in the dashboard API contract test.
