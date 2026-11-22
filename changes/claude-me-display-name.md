---
pr: pending
branch: claude/me-display-name
---
People can now choose the name Home greets them by. GET /v1/me returns a top-level display_name, null until the person sets one, and PATCH /v1/me sets it (or clears it with null) for the caller only: 1 to 60 characters after trimming, no control characters and no angle brackets. It is display text only: it grants nothing and never replaces the stable id or role in authorisation or audit, and the audit record notes that the name changed without storing the name. It lives in a new nullable identity column (schema step 2) so the existing account name is untouched. Refs #440.
