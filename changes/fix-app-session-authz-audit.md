---
pr: pending
branch: fix/app-session-authz-audit
---
`POST /v1/auth/app-session` now writes `authz.denied` to the audit log when it refuses a caller that is not a person (an agent or an app agent), like every other 403 (contract §3). The strict-xfail gap in the security table is removed.
