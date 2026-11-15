---
pr: pending
branch: feat/rescue-console
status_rows:
  - CORE-UPDATE-8 | in-review | onemindd rescue, owner token, rollback with k3s stopped
---
Rescue console (CORE-UPDATE-8): `onemindd rescue` serves a small owner-only web page on its own unit, outside Kubernetes, that shows the booted RAUC slot, slot versions and k3s state, downloads a bounded log file, and rolls back to the other slot (rauc mark-active other, then reboot) only after an owner POST with a CSRF token and a typed confirmation. It checks the owner token against the gateway's hash-only tokens file, serves HTTPS with the box CA on LAN addresses, rate-limits failures and keeps working with k3s and the gateway stopped.
