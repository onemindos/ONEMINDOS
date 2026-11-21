---
pr: 369
branch: codex/204-family-controls
---
FAM-01 (#204): owner-managed private family profiles add app allowlists, age-rating limits, tag blocks, time-zone-aware schedules and child and teen birth dates. A new Teen role (founder decision, 2026-11-21) sits between Child and Adult: it signs in on its own with the same API scopes as a child, is narrowed by the same per-person controls, never approves anything and sees no Pro or owner screens. Controls intersect existing sharing and apply to catalog and proxy access. App classifications and family profiles are persisted through authenticated gateway routes with passkey step-up and generated SDK models.
