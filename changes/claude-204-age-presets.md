---
pr: 454
branch: claude/204-age-presets
---
FAM-01 (#204): a new Child gets a starting age-rating limit of 12 and a new Teen gets 16 (founder decision, 2026-11-21: teens get a looser default than children). The preset is also applied when an owner changes someone to child or teen, but only if that person has no family profile yet; an owner-set or cleared profile is never overwritten. Adults, guests and owners get none. The owner can edit or clear it at any time, the audit event carries no birth date, and the People page shows each child or teen's current age-rating limit, marked as the default while it still matches the preset.
