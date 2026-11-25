---
pr: pending
branch: claude/147-household-apps
---
The Market list now tells the owner why an app is blocked: each failed scan in GET /v1/apps carries a reason built from scan.json's own counts (fixable CRITICAL CVEs per image, secret findings, malware hits, smoke result). For the household apps (Immich, Nextcloud, Home Assistant, Audiobookshelf, Paperless-ngx) the newest upstream tags were re-read from the registries and scanned with Trivy on 2026-11-21; none clears the gate, so no pin moves and every tier stays blocked, with the exact remaining CVEs, fixed versions and layers recorded in each app README. Apps that would need a OneMind rebuild of an upstream image wait on the founder decision.
