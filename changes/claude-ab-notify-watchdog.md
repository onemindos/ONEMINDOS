---
pr: pending
branch: claude/ab-notify-watchdog
---
Node-side hub watchdog (#687): `onemindd` watches the hub heartbeat and, when it stops for 60 seconds, runs a local siren or speaker hook and pushes a signed alert to LAN peers, with no internet needed. Off unless `/etc/onemind/watchdog.json` exists, never runs on a hub. A fake-clock test proves the peer alert lands within 2 minutes; a lab kit covers the founder's hardware proof. The phone watcher stays with wave P.
