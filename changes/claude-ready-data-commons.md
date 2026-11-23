---
pr: pending
branch: claude/ready-data-commons
---
The data commons, part 1 (#615): the five data classes the built-in descriptors already name (public, owner, private, location, activity) now have grants per app, agent and person, each with read, write, aggregate and an expiry. A grant only comes from an approval card: an app's plugin or an agent files `data.grant` through POST /v1/actions, and only an owner approves it (agents and plugins can never approve, and no standing approval covers it). New routes under /v1/data list the classes with your access, list the grants (the owner sees all of them, anyone else their own), let the owner revoke one at once, and hold each class's shared records, with a list, a write and a live stream. Without a grant a caller gets empty data, never an error; aggregate sees only the count; a revoke or expiry ends an open stream within about a second. The Privacy screen and the MCP door follow in the next parts.
