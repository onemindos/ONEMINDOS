---
pr: pending
branch: claude/430-photos-viewer
---
Built-in Photos window (#430): the gateway now lists a person's own backed-up photos newest first (GET /v1/photos/library) and serves one photo's original bytes (GET /v1/photos/assets/{id}/content), and the dashboard has a Photos screen with a timeline by day, a large view, and a badge that says whether each photo is safe in a restore-checked backup. Read only for now: delete as a request waits for Trash.
