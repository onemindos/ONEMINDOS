---
pr: 77
branch: feat/files
status_rows:
  - UMB-FILES-1 | in-review | resumable uploads (tus, sha256 checks) and confined paths built in the gateway; the node file server in onemindd is not yet
  - UMB-FILES-2 | in-review | gateway file API built: Home and Shared spaces by role, browse, preview, ranged downloads, moves, trash, quotas
  - UMB-FILES-6 | in-review | folder grants to apps and agents behind owner approval built; executor mount hook and MCP tools not yet
---
FILES as a core service: a private Home per person and a household Shared folder on /data, with access by role; browse, preview, downloads that resume (HTTP ranges), uploads that resume (tus, sha256-checked, capped per person, partial files swept on expiry), move, rename, trash with 30-day retention and quotas. Paths are walked with openat and O_NOFOLLOW so nothing leaves a space. Folder grants to apps and agents exist only after an owner approval, and every write is audited. API guide for the dashboard: docs/leap/core/FILES.md.
