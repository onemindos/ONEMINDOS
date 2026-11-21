---
pr: pending
branch: claude/155-offline-grace-mirror
---
Offline grace and USB/LAN mirror installs for OS updates (CORE-UPDATE-7, first slice). `onemind update check` and `onemind update apply` accept `--mirror <dir>`, a USB stick or mounted share laid out like the channel. Metadata and bundle are verified exactly as online (image-shipped root, rollback cache, signed length and sha256, RAUC signature check), and only the expiry check is relaxed by the new `offline_grace` setting (default 90 days, mirror only). Unit tests cover an install with no network from 60-day-old metadata, grace exceeded, strict mode, online never using grace, an untrusted root, a tampered bundle and replayed older metadata.
