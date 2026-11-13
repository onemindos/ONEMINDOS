---
pr: 75
branch: feat/automation
status_rows:
  - CORE-AUTO-2 | in-review | schedule and event rules built; webhook triggers and the NATS JetStream consumer not yet
  - CORE-AUTO-3 | in-review | built with windows, F-6 and kill switch; passkey step-up waits for identity
  - CORE-AUTO-4 | in-review | dry run and enable gate built; CLI and page not yet
  - CORE-AUTO-5 | in-review | breaker publishes automation.breaker.opened; notification routing not yet
  - DEV-API-13 | in-review | automation routes of contract 12.17
---
Automation (contract section 12.17): schedule and event rules that only request actions as automation:RULE-ID; owner-set standing approvals with limits counted in the database (types, params, per day, window, expiry up to 90 days, F-6 patch updates) recorded as approved_by policy:ID@REV; maintenance windows; dry run required before enable; and a kill switch that pauses all automation.
