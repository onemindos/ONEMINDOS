---
pr: pending
branch: claude2/364-audit-verify-race
---
Fixes a race in the gateway's audit verify cache (#364): a same-size change to the audit log within one kernel clock tick left verify() reporting the old "ok", because the cached result was keyed on size and mtime. The cache now uses the ctime-based signature from core/onemind_core/filesig.py (the same copy as in #360 and #377): a result is cached only once the file's ctime is at least 2 s old, so a fresher or missing file is always verified again. A frozen-stat test shows a same-tick, same-size forgery is reported at once and fails on the old code.
