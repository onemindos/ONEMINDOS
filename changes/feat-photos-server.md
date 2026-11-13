---
pr: pending
branch: feat/photos-server
---
Photos server, the box side of phone photo backup (PHOTOS-SRV-1, UMB-PHOTO-3): `/v1/photos` sources, `check`, resumable uploads fsynced per part and SHA-256-verified before any receipt, per-person libraries of plain files hard-linked to one stored copy, dedupe without a hash oracle, and receipt levels from backup events. Library paths reuse the FILES confinement. Decision and design: docs/leap/core/PHOTOS.md
