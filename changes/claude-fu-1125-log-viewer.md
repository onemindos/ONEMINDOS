---
pr: pending
branch: claude/fu-1125-log-viewer
---
Follow-ups from the Opus review of the whole-system log viewer: IPv6 addresses (full, compressed, link-local with a zone, bracketed and IPv4-mapped) are now masked like IPv4, an SSH fingerprint is masked even when it ends in plus or slash, the 1 MiB cut counts bytes so non-ASCII text cannot pass it, and a follow stream frees its slot as soon as the viewer leaves, even on a quiet unit, with a keep-alive comment every 15 seconds.
