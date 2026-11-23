---
pr: pending
branch: claude/fix-release-next-reds
---
Turns the four gateway tests that were red on release/next green without loosening any of them. The motion lockout routes (GET and PUT /v1/physical/lockout) get owner-only rows in the route permission matrix, and a new test proves lifting the lockout needs a fresh passkey once passkeys are active. The error contract test now expects upgrade_required (the protocol gate's refusal), the router order test pins the protocol gate just before guard so guard still wraps its refusals, and the property test accepts the documented 503 domains_disabled the same way as backups_disabled. Tests also read a 0644 copy of the signed system apps list when a checkout made under umask 0002 leaves the repo copy group-writable, which the gateway rightly refuses.
