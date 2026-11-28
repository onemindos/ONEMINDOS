---
pr: 1310
branch: ma/sf-files-rename
---
The Files screen and `onemind files` CLI can request renames and create or end public share links through the Files approval queue (Refs #1232, Refs #234, Refs #237). The owner reviews requests in the Files screen under Sharing. An agent can still rename files within an owner-approved read-write folder grant. Owners and adults can request public links. The URL appears once, at request time, and works after approval. Recipients use an API client, with the OneMind-Share-Password header for protected links. The CLI reads link passwords with `--password-stdin` and accepts expiries from 6m to 719h. A share link stops serving a file when its original identity changes. Gateway access logs redact the link credential. The matching surface-parity exemptions are removed.
