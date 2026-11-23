---
pr: pending
branch: claude/fix-release-next-radios-lint-host-unit
---
Two red checks on release/next fixed: the openapi-lint now lists the two radio routes (GET /v1/radios, POST /v1/radios/{radio_id}/confirm) as signed-in routes like their siblings, and exempts the confirm route from the Idempotency-Key rule because it is an upsert; and the host unit test now reads the image's `systemctl enable` commands and checks the factory-reset wipe unit is among the enabled units, instead of matching one exact text that broke when the units were joined onto one line.
