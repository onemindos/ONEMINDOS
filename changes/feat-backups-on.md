---
pr: 86
branch: feat/backups-on
---
Backups switched on: one backup service inside onemindd, owner-only backup and restore routes, restores run as gateway-signed approved actions, manifest backup hooks and the shared PostgreSQL for apps with a database. Merged with the app lifecycle work (plan binding, credentials route, delete_data) so both sets of rules apply.
