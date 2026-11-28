---
pr: pending
branch: claude/fu-work-repeat-tz
---
A monthly or yearly repeating task that starts on the 31st no longer drifts to the 28th for good: the rule remembers the day it started on, lands on the last day of a short month, and goes back to the 31st as soon as a month has one (the remembered day is internal and resets when the person moves the due date or edits the rule). A repeat rule's time zone can now be changed from the dashboard (a Zone control on each repeating task), from the CLI (onemind work repeat-zone PROJECT TASK ZONE, or local for this machine's zone) and through the existing task PATCH, and the task list shows the zone each rule counts its days in.
