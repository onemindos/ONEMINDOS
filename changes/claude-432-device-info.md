---
pr: pending
branch: claude/432-device-info
---
About this box (UMB-P14): Settings, About now shows the device facts an owner reads out when asking for help: hostname, OneMind version and booted A/B slot, the Debian base, kernel, CPU, memory, disk, uptime and board per node, and the node count on a hub. They come from the heartbeats through a new read-only route, GET /v1/os/about, which rebuilds every field from an allow-list and re-checks it because heartbeats are untrusted. A Copy details button and the new onemind about --support command produce a support block with no serial numbers or addresses (the box never reports them) and no node id unless the owner turns it on.
