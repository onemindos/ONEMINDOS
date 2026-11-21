---
pr: pending
branch: claude/239-network-view
---
A read-only Network screen (NET-UI-01, first step of #239): the dashboard shows the box's interfaces and addresses, gateway, DNS servers, Wi-Fi signal and every port it listens on, and says plainly when the host service cannot be reached. The facts come from the host service (`onemindd host serve`, new `GET /v1/network` read from /sys and /proc) through an owner-only gateway route `GET /v1/network`, because the gateway runs in a container and heartbeats must not carry IP or MAC addresses. The gateway re-checks every field and drops entries that fail. Changing the IP, Wi-Fi or firewall, with automatic revert, is the next PR.
