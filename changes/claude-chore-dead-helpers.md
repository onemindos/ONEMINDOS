---
pr: pending
branch: claude/chore-dead-helpers
---
Repo clutter cleanup (hardening H-34, CORE-NET-8 hygiene): removes three helpers that nothing calls, registered_sections in the gateway section registry, fsync_dir in the photos file store, and the errTooLong variable in the MCP bridge. Each had exactly one occurrence, its definition, with no dynamic use. write_secret_file stays because CORE-NET-8 needs it.
