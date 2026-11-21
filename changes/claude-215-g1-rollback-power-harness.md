---
pr: pending
branch: claude/215-g1-rollback-power-harness
status_rows:
  - CORE-UPDATE-4 | in-review | power-pull harness for G1 (manual, Redfish, IPMI, smart-plug backends); not run on metal
---
Adds g1-power.py to the G1 lab kit: a controller-side harness that drives the 20-pull power-cycle protocol (PP-10) against a box over SSH, with manual, Redfish, IPMI and smart-plug power backends, a RAUC and gate and HTTP health check, resumable results and a line for the G1 record. Credentials come only from the environment. Tested against fakes only; the metal run stays the founder's.
