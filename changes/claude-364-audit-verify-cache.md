---
pr: pending
branch: claude/364-audit-verify-cache
---
The audit chain check no longer reports a stale "ok" for a tampered log. Its cache was keyed on file size and modification time, which a same-size rewrite within one kernel tick leaves unchanged; it now uses the shared racy-file signature, so a freshly changed log is checked again on every call and only a settled log is cached.
