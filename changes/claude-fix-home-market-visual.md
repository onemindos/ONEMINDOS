---
pr: 1224
branch: claude/fix-home-market-visual
---
Home and Market fixes from the visual review of landing PR 1192. Home puts the greeting first again (IA 2.1): Box health now sits under the greeting and search, Recent visits moves to the end as a design-system card, and both line up with the rest of Home on a phone. When the box has not reported its status, Box health says so once instead of showing seven Unknown pills, and Needs you shows the waiting approval first with one Not reported line, so Approve and Deny stay in view. On a phone the menu bar fits from 360 to 430 px: Live usage moves into the account menu and, below 390 px, the hub pill keeps only its glyph, so Search no longer covers the Demo badge. The Market demo catalogue now carries each app's real licence class from its manifest, so Discover lists apps under the default green-licence filter and Uptime Kuma's licence reads Permissive instead of Unclear.
