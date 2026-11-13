# SPDX-License-Identifier: Apache-2.0
"""Backups switched on: the gateway side of contract §12.12 (CORE-BACKUP-6/7/8, BACKUP-WIRE-1).

The box's restic work happens in `onemindd backup` (internal/backup), a separate root process with
just enough rights to read and write app data. The gateway decides: it keeps the destinations,
runs each app's backup hooks inside the app's own container (never on the host), dumps the app's
database from the shared PostgreSQL, and then asks the agent to snapshot, browse, verify or
restore by sending a job signed with its Ed25519 job key. Restoring is always an owner-approved
`backup.restore` action, and it takes a pre-restore snapshot first, so every restore can be undone.

Modules: settings (the `backups` settings section), jobs (job signing, agent client), kube
(kubectl calls), manifest (`spec.backup`, `spec.database`), store (tables), kit (emergency kit),
service (the orchestration). Routes: routers/backups.py. Plain-language guide: README.md here.
"""
