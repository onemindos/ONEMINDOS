---
pr: pending
branch: claude/cli-groups-trust
---
The onemind command line gains three groups for what an owner lets apps and plugins do: `plugins` (list the installed plugins, show their tools and settings, request new settings, list and request host access such as a USB device or GPU and revoke a grant, list and request enrolling or revoking plugin signing keys), `data grants` (who may read or write which kind of your data, and revoke a grant) and `radios` (list the radios the box found and confirm what one is, owner only). Every command takes --json; changes only file requests that an owner approves, and taking power back (a host grant, a data grant) is the one direct call, which the gateway limits to an owner. Refs the UI and backend parity report (M3 CLI half and the plugins row).
