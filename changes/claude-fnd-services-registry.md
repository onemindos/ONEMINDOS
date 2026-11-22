---
pr: pending
branch: claude/fnd-services-registry
---
Service cards (#623): the image now ships a services registry (/usr/lib/onemind/services.yaml on the signed, read-only image, contract sdk/schema/onemind.services.schema.json) that gives every systemd unit under os/ a plain name, plain description, docs page, risk, restartable flag and dependencies. The host service answers GET /v1/services by joining it with systemctl show (read-only verbs only), the gateway serves it to the owner as GET /v1/system/services after re-checking every card, and `onemind services list` prints it. A OneMind unit the registry does not list shows as unknown, and a unit test fails when a unit file ships without an entry, when an entry is stale, when a docs page is missing or when a rescue, first-boot, host or data unit is marked restartable.
