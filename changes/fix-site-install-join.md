---
pr: pending
branch: fix/site-install-join
---
The site's install, updates and troubleshooting pages now show how machines really join: a one-time code from `onemind fabric ticket` (or Add a device), `install.sh --role node --join '<code>'` and owner approval. The old `--token` form, which install.sh refuses, is gone from them.
