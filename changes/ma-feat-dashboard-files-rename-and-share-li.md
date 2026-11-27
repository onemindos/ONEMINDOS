---
pr: 1310
branch: ma/feat-dashboard-files-rename-and-share-li
---
The Files screen can now rename a file or folder and make, list and end share links (Refs #1232, Refs #234), using the gateway's existing rename operation and /v1/files/shares endpoints. Share links are offered only to an owner or an adult, the link is shown once in a read-only field with a Copy button, and a create is never retried. The `onemind` CLI gains `files rename` and `files share (create, list, revoke)`; a link password is read with `--password-stdin`, never taken as a flag, and `--expires-in` runs from 6m to 719h so it stays inside the gateway's limits. Rename and share links act at once, as the gateway has no request path for them. The matching surface-parity exemptions are removed.
