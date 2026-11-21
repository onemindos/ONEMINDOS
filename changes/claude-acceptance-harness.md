---
pr: pending
branch: claude/acceptance-harness
---
Adds test/acceptance, an API acceptance suite that runs against a live hub (hub URL and owner token from the environment) and skips cleanly without one. It checks health, owner sign-in, refusals without a token or with the wrong scope, that a Child token cannot request installs, that an app install and an AI-proposed action wait for approval with nothing installed, that the audit log records them and verifies, and that the backup lists answer.
