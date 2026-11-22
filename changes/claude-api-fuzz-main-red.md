---
pr: pending
branch: claude/api-fuzz-main-red
---
api-fuzz was red on every main run since 2026-11-20. The failing finding on all four runs was the first-run restore step (POST /v1/onboarding/restore/candidates) answering its documented 503 backups_disabled: it is a backup route, but the fuzz config and the 503 envelope check only knew the backups and restores paths, so the check called a correct answer a server error. Both now cover the onboarding restore path, still pinning the exact envelope and refusing any other 503 elsewhere. Two intermittent findings from the same runs are fixed in the server: the files quota limit accepted a numeric string such as "0", and the approve flag on file requests accepted 1, 0 and "true"; both now answer 422 as the schema says. The If-Match contract for Home stays with issue 327.
