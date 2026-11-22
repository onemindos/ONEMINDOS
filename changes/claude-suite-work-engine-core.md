---
pr: pending
branch: claude/suite-work-engine-core
---
Work engine core, first slice of the built-in to-do and project app that people and AI agents share. The gateway gets projects, sections and tasks (status, priority, assignee, due date, repeat rule, labels, custom fields, a reference to a file or photo, dependencies with a cycle check, comments and an activity trail) under /v1/work, plus Todoist-style quick add (/capture, /parse, with an Idempotency-Key), Today, Upcoming and Inbox views. Changes need the revision you read (If-Match), a project is visible only to its members, and an AI agent sees only what the project's ai_access allows (none, read or work), never creates or deletes anything, and is never assigned work in a project that does not let AI work. Every write emits a work.task.* event and an audit row, and assignments, due soon and overdue tasks notify only the assignee. New command: onemind work add, today, list, done.
