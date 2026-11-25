---
pr: 1091
branch: claude/s2-clock
---
Step 2 of the Debian bones, part 1: the image now has a clock. It installs systemd-timesyncd and tzdata by name (recommends are off, so they never came in), enables the timesync unit and sets LANG=C.UTF-8. New first-boot check F17 proves the unit is enabled and running, the zone database is present and the clock reports NTP-synchronised when a server is reachable, which is what node-check.sh asks.
