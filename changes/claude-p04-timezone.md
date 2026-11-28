---
pr: 1144
branch: claude/p04-timezone
---
The hub's time zone is now applied for real, and the clock shows live. An owner (or an agent, who can only ask) requests a zone change on Settings, Date and time or with onemind time set-zone; it waits in Approvals, and once an owner approves it the host service swaps the zone on the data partition, so it is live at once and survives a reboot and an A/B update. GET /v1/system/time and onemind time status report the zone, whether the clock is synchronised, the time server and the last sync. New boot checks F14 and F15 prove the zone changes and survives the reboot.
