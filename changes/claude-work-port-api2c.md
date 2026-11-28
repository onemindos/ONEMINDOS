---
pr: 1138
branch: claude/work-port-api2c
---
Work part 2c, ported from #798 onto the Work engine: reminders in the assignee's inbox. Giving a task to someone else sends "Assigned to you", and a sweep every five minutes sends "Due soon" (within 24 hours) and "Overdue" once per task and due date (new `work_reminders` table). The notifications go only to the person named, never to owners by role, and carry the title only at render time: events and the audit log hold ids. The notifier gains per-domain enrichers (`Gateway.notify_enrichers`) for that.
