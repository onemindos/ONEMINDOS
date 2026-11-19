---
pr: 377
branch: claude2/363-tokens-race
---
Fixes a race in the gateway's tokens file reload (#363): a token revoked by a same-size rewrite within one kernel clock tick kept working, because the store reloaded only when mtime changed. The store now uses the ctime-based signature from core/onemind_core/filesig.py (a copy of the file from #360): a signature is trusted only once ctime is at least 2 s old, and a more recent file is read again on each lookup (parsed only when its text changed). A frozen-stat test shows a same-tick revoke is refused at once and fails on the old code.
