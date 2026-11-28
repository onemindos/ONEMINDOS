---
pr: 1134
branch: claude/work-port-api2
---
Work part 2a, ported from #798 onto the Work engine: project list, get, rename and delete, project members (list, add, remove), a task activity log (field names only, never values; new `work_activity` table), and `POST /v1/work/parse`, a preview of what a quick-add line would file. `onemind work` gains `projects`, `project-edit`, `project-delete`, `member-add`, `member-remove`, `parse` and `activity`. The Inbox cannot be renamed or deleted. Comments, sections, repeat rules and reminders follow in the next PR, the dashboard views after that.
