---
pr: pending
branch: w0/core3-domains
---
The API property test now allows exactly two documented 503 answers for a switched-off optional feature: backups (reason backups_disabled) and bring-your-own-domain (reason domains_disabled), each only on its own route tree, matched by whole path segments, with error unavailable. A 503 with no reason, another error code or another tree's reason still fails, and a table test pins every one of those cases.
