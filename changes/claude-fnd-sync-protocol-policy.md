---
pr: pending
branch: claude/fnd-sync-protocol-policy
---
Client protocol versions (issue 697): apps now send X-OneMind-Protocol on every request and every gateway answer carries X-OneMind-Protocol-Min and -Max. The gateway serves the current generation and the one before it for at least 12 months, refuses older apps with 400 upgrade_required, and lists the generations at the open GET /v1/protocol. A recorded corpus of generation 1 requests is replayed in CI so a breaking change fails a test instead of an old phone app. The dashboard and the phone app show an Update needed screen instead of breaking. Contract in sdk/contracts/protocol-versions.md.
