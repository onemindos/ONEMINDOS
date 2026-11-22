---
pr: pending
branch: claude/c12-tips-gateway
---
Tips becomes a built-in app on the gateway (#669). At start the gateway reads the tips pack that ships in the OS image (/usr/share/onemind/tips), checks its Ed25519 signature against the key in the image before parsing it, checks that the running OneMind version is inside the pack's OS range, and serves no tips when either check fails, so a tampered or too-new pack is never shown. New routes GET /v1/tips, /v1/tips/collections, /v1/tips/whats-new, /v1/tips/{tip_id} and POST /v1/tips/{tip_id}/state give each person the tips for their role and OS version and keep their dismissed or done state in the tips_state table, which survives restarts and is in the backup set. Tips is on the signed built-in list with its descriptor, so the owner can switch it off and every Tips route then answers 409 app_disabled. Building and signing the pack into the image is a follow-up.
