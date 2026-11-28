---
pr: 1308
branch: ma/sf-signinkeys-role
---
Fixes Sign-in keys hiding the owner controls on a real hub (Refs #1284, Refs #234). The page read the role from the signed-in principal, which a real gateway does not carry, so an owner never saw the trusted key models. It now reads the role from the shell, which asks GET /v1/me, as Security settings does. Owner-only content stays closed until the role is known, and when the role arrives after the page opened the page reloads, so the owner still gets the verification table and the two-key hints. Tests cover a real session with no role on the principal (owner, adult, agent, a late GET /v1/me) through the whole app.
