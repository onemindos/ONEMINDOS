---
pr: pending
branch: claude/sso-ups-nut-status
---
UPS status on the dashboard (IMG-06, part 2 of 2). GET /v1/system/ups reads the UPS from NUT's upsd on the box (read only, never a command) and says whether it is on mains or battery, the charge, the minutes left on battery, the load and the model, or that the box has no UPS. Settings, About shows it in a Power and UPS card, with what happens on a low battery and how to add a UPS. Household members with device access read it; a child does not.
