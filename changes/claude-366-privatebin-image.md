---
pr: pending
branch: claude/366-privatebin-image
---
Moves the PrivateBin Market app to an upstream image rebuild (still PrivateBin 2.1.1) with nginx 1.30.7 and php 8.5.13, pinned by digest, fixing the three nginx CVEs from the 2026-11-19 rescan; the committed scan.json comes from a real app-gate run (0 Trivy findings, ClamAV clean, smoke not yet run).
