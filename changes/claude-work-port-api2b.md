---
pr: 1137
branch: claude/work-port-api2b
---
Work part 2b, ported from #798 onto the Work engine: task comments (list, add with an Idempotency-Key, delete your own), project sections (list, add, rename, delete; a task can sit in one section), and repeat rules (every day, weekday, week, month or year, with an interval). Finishing a repeating task moves it to its next due date and keeps it open. Quick-add and `POST /v1/work/parse` read "every 2 weeks". New tables `work_comments` and `work_sections`, and `section_id` and `repeat` columns on tasks (schema step 3). `onemind work notes ...` covers comments and sections. Reminders and the dashboard views follow.
