---
pr: 1313
branch: ma/sf-role-gating
---
The dashboard now hides what a role cannot use, using the role from the shell (GET /v1/me) instead of the token. Approvals is no longer in the dock or Launchpad for guests, children, teens and adults (or before the role is known), a guest, child or teen who opens it gets a calm role line instead of a raw error, an adult sees no enabled Approve or Deny buttons on Home or Approvals (one rule, decideState in roles.ts, also used by the palette), and a list the hub refuses for a role no longer keeps the connection pill on connecting. Refs #1232, Refs #234.
