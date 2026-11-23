---
pr: pending
branch: claude/d12-market-unblock
---
Market unblock (#147): copyparty leaves tier blocked. Upstream v1.20.27 rebuilt its image on a patched Alpine, and Trivy on amd64 and arm64 finds no CRITICAL or HIGH, so the pin moves to that digest and the tier to community (the PR's CI app gate, with ClamAV and the smoke test, wrote the committed scan). Home Assistant moves to 2026.11.2 and Audiobookshelf to 2.38.0, the newest releases; both still carry CRITICALs with a fix on both architectures (openssh and Authlib; form-data, proxy-addr, sequelize and tar), so they stay blocked with those reasons. A new test checks that each bumped app's committed scan covers exactly its pinned images and that its tier matches. The gate was not changed.
