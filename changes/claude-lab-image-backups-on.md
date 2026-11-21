---
pr: pending
branch: claude/lab-image-backups-on
status_rows:
  - CORE-BACKUP-2 | in-review | image now ships restic and wires the agent
---
IMG-BACKUP-01: a hub built from the OS image can now back up and restore. The image ships the pinned restic (checked against the same sha256 the backup agent enforces) and sqlite3, an onemindd drop-in with the four capabilities and writable folders a restore needs, and a tmpfiles rule for them. On a hub, first boot creates the gateway's backup job key, writes the agent settings with no destination, and turns backups on for the gateway and onemindd; hubs set up before this get the same on their next boot without a new key. Setup stays gated on the emergency kit, and the owner still adds and approves a destination. Refs 163 and 145.
