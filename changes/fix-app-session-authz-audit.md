---
pr: pending
branch: fix/app-session-authz-audit
---
`POST /v1/auth/app-session` now writes `authz.denied` to the audit log when it refuses a caller that is not a person (an agent or an app agent), like every other 403 (contract §3). The strict-xfail gap in the security table is removed.
The API fuzz run's seed step no longer stops on an app that needs other apps installed first (`library-chat`): the gateway's 409 `dependency_missing` refusal is expected there, so that app seeds no action; any other refusal still fails the run.
