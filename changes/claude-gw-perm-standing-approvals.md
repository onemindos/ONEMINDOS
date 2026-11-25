---
pr: pending
branch: claude/gw-perm-standing-approvals
---
Gateway permissions PR 2, standing approvals on every request path. An owner-set rule now covers requests filed through the handler and feature paths as well as the app lifecycle path, and the audit line names the rule that approved. Requests a rule could cover carry a plan so the approval is bound to those parameters, and a requester that read third-party text still waits for a person on every path. The configure-with-secrets path is never offered to a rule, and a rule naming a type this gateway does not file is refused when it is made.
