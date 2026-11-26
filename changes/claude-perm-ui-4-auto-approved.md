---
pr: 1275
branch: claude/perm-ui-4-auto-approved
---
Auto-approval notices can now be acted on. A notice that a rule approved a request shows a Revoke rule button in the dashboard inbox, which ends the rule with one tap and no passkey (it only narrows), and never an approve button. Settings, Permissions has an Auto-approved tab (where the daily summary notice links) listing every request a rule approved in the last 30 days, newest first, with the requester, the rule and its revision, the use count that day, a Forever badge, and Revoke rule on each line; it reads the audit log. The CLI gains onemind permissions log (with --days and --json). The gateway now documents its inbox items (NotificationView, with the revoke button kind and its rule id) so the dashboard reads them through the generated SDK type.
