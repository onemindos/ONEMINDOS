---
pr: pending
branch: claude/ab-notify-watchdog
---
Node-side hub watchdog (#687): `onemindd` watches its NATS leaf link to the hub and, when the link stays down for 60 seconds, runs a local siren or speaker hook and pushes a signed alert to LAN peers, with no internet needed. Off unless `watchdog.json` exists in the node etc dir (`/etc/onemind`, or `/data/onemind/etc` on the image), never runs on a hub. The leaf now pings every 15 s (2 missed) so a dead link reads down within 45 s. A fake-clock test proves the peer alert lands within 2 minutes; a lab kit (3 minute quiet period, LAN-only firewall drop-in for UDP 7481) covers the founder's hardware proof. The phone watcher stays with wave P.
