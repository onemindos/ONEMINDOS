---
pr: pending
branch: ma/fix-dashboard-approvals-shows-names-and-
---
Approvals now shows who asked by display name (people from the users list, agents by their name) instead of raw ids like usr_..., and describes each request in plain words from one table of action types, with a readable fallback for types it does not know. The raw request name stays under Technical details. Refs #1232, Refs #234.
