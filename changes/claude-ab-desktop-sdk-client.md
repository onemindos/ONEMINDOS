---
pr: pending
branch: claude/ab-desktop-sdk-client
status_rows:
  - CI-08 | in-progress | desktop slice: cargo contract test against the committed OpenAPI spec
---
The desktop app reads gateway JSON by key, so a renamed API field used to fail silently. A new cargo integration test reads sdk/openapi/onemind-v1.json and fails when a route, query parameter or typed response field the desktop uses is missing from the spec. Dashboard and mobile are separate.
