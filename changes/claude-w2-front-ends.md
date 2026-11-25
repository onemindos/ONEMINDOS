---
pr: pending
branch: claude/w2-front-ends
---
Front ends for backends that already existed, each wired to its route and the CLI. Settings > Appearance gets an owner-only switch for the box's own screen (kiosk) over GET and PUT /v1/instance/kiosk. The Network screen gets "Your own domains" over /v1/domains: add a domain and read the TXT proof record, check it, remove it, and see the names asked for under it, with an honest note when the feature is off on the box. Settings > About gets a "What leaves this box" card that reads the mesh mode and the own-domain switch from the box and says plainly that no usage data is sent. The six Settings sections that still said coming soon (Automation, Backups, Devices, Network, Storage, Updates) now link to the screens users already reach through the redirects, and a test keeps the two in step. `onemind domain list` and `onemind domain add` reach the same route through the Go SDK, and the TypeScript SDK gains instance.kiosk and domains calls.
