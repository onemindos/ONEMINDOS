---
pr: pending
branch: claude/areas-a-work
---
Work can now be managed from the dashboard and the command line, beyond list and quick-add. The Work page gets a Projects card (create with an idempotency key, rename, choose what the AI may see in plain words, delete with a question first) and each task gets Edit (title, due time, urgency) and Delete with a question first; both send the task's revision in If-Match, so a task changed meanwhile is refused and reloaded rather than overwritten. The command line gets `onemind work project-add`, `onemind work edit` and `onemind work delete`, and the Go SDK gets CreateProject, UpdateTask and DeleteTask.
