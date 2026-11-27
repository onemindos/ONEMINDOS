---
pr: pending
branch: ma/fix-dashboard-sign-in-keys-reads-the-rol
---
Fixes Sign-in keys hiding the owner controls on a real hub (Refs #1284, Refs #234). The page read the role from the signed-in principal, which a real gateway does not carry, so an owner never saw the trusted key models. It now reads the role from the shell, which asks GET /v1/me, as Security settings does, and stays closed until the role is known. The test now models a real session with no role on the principal.
