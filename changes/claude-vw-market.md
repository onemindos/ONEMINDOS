---
pr: 953
branch: claude/vw-market
---
Vaultwarden stays an ordinary Market app in apps/vaultwarden (founder, 2026-11-25), not a built-in Passwords system app. App pages now show the upstream source as a real link, which the AGPL-3.0 source duty wants, and a new test holds the app to its licence class, pinned image, age rating and hardening (non-root, seccomp, no service account token, no planted tokens). The README records that the Bitwarden apps cannot sync through the app proxy yet (#994).
