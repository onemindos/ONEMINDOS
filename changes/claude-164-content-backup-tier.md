---
pr: pending
branch: claude/164-content-backup-tier
---
Backups for offline content and models (BAK-03, REC-NOMAD-07): an app manifest can mark large, re-downloadable content with spec.backup.content (Kiwix ZIM files, Offline Maps archives, Ollama models). That content is left out of the app's snapshots until the owner switches the content tier on for the app. GET /v1/backups/content shows each such app with the size the node agent measures on its volumes now (read only, symlinks never followed), and POST /v1/backups/content files an owner-only backup.content.set that must carry the size the owner was shown. Each app snapshot is tagged content=included or excluded, and a restore plan says which, with a warning when the content is not in the snapshot. Tests restore a library app with and without the content tier, on the gateway and in the agent with real files.
