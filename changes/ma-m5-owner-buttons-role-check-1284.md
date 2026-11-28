---
pr: 1303
branch: ma/m5-owner-buttons-role-check-1284
---
Owner-only dashboard controls (agent kill switch button, Add a device, Transfer media, own ISO or disk upload in Request a machine, the app passwords holder check, the rollout buttons on Updates, the maintenance window buttons on Automation, and Confirm what this is for radios) now read the role from the shell, which asks GET /v1/me, instead of the session principal that a real hub never sets. They no longer hide from the owner on a real hub, and the app passwords card and the "only an owner" notes wait for the role instead of showing early. The own-file upload also needs the signed-in person's id. New tests mount the app without knownPrincipal and check an owner sees each control and an adult or child does not. Refs #1284, Refs #1232, Refs #234.
