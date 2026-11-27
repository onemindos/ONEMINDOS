---
pr: pending
branch: ma/feat-dashboard-files-rename-and-share-li
---
The Files screen can now rename a file or folder and make, list and end share links (Refs #1232, Refs #234), using the gateway's existing rename operation and /v1/files/shares endpoints. The `onemind` CLI gains `files rename` and `files share (create, list, revoke)`. The matching surface-parity exemptions are removed.
