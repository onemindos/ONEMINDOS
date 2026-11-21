---
pr: pending
branch: claude/233-one-api-client
---
The dashboard's hand-written API types are now checked against the generated SDK schema at compile time, so changing or removing a field in the API breaks the dashboard typecheck in CI. A new test also blocks raw fetch calls outside the two SDK transport files and fails if the dashboard calls a /v1 path that is not in the OpenAPI file.
