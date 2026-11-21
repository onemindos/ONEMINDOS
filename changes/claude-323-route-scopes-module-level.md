---
pr: pending
branch: claude/323-route-scopes-module-level
---
Route scopes are now guarded for good: a test fails when a new gateway route is added without its own register_route_scope row at module level, so a forgotten scope can no longer hide behind the owner-only fallback. The routes that still use that fallback today are listed in a baseline that may only shrink.
