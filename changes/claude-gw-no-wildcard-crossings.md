---
pr: pending
branch: claude/gw-no-wildcard-crossings
---
Standing approvals can no longer be written with a wildcard (person star or automation star): each one names who it covers. Rules made before this keep a narrow reading, so an old person star covers only an owner or adult (never a child, teen or guest) and an old automation star covers only an automation a person wrote by hand, never one an agent proposed. Migration pauses old automation star rules until the owner confirms them (POST /v1/approval-policies/{id}/confirm), automations now show their author and proposed_by, and revoking a rule sets its state and bumps its revision in one statement so a use racing the revoke is refused. Gateway permissions design PR 5, D-027 and D-029.
