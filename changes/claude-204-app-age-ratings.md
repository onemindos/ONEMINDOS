---
pr: pending
branch: claude/204-app-age-ratings
---
FAM-01 (#204): every Market app now carries a proposed minimum age in its manifest (`metadata.age_rating` of 0, 7, 12, 16 or 18, plus a one-line `age_reason`), rated by what the app does with the higher number when unsure (founder decision, 2026-11-21: yes, rate the apps). The schema and validate-apps require the field, the scaffolder starts new apps at 18 marked UNVERIFIED, and apps/README.md holds the rubric. The gateway uses the manifest rating as the default for family filtering when the owner has not set a minimum age for the app; an owner classification still wins and an unrated app stays hidden under a limit. GET /v1/apps returns age_rating and age_reason. The review table for the founder is docs/learning/founder/app-age-ratings.md.
