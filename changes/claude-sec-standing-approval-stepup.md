---
pr: pending
branch: claude/sec-standing-approval-stepup
---
Creating a standing approval (POST /v1/approval-policies) and editing a maintenance window (PUT /v1/windows/id) now need a fresh passkey sign-in once passkeys are active, the same step-up that sharing an app and creating users already use. Before, a password-only owner session or a stolen owner token could pre-approve agent actions with no human passkey. Agents still get 403, and the audit record now says how the owner proved presence instead of always saying token.
