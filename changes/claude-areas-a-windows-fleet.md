---
pr: pending
branch: claude/areas-a-windows-fleet
---
Two more gaps from the UI parity report are closed. Maintenance windows: the Automation page now lists every window in plain words (days, times, open now) and lets an owner add or edit one (name, time zone, up to 14 weekly ranges), with a clear message when the box wants a fresh passkey sign-in first; `onemind windows list` and `onemind windows set` do the same from the command line. OS fleet and rollouts: the Updates page shows every machine's version and the rollouts with their wave and why one paused, lets an owner cancel one and file requests to start or resume one (an owner still approves in Approvals); `onemind update fleet` and `onemind update rollouts` (list, show, start, resume, cancel) match.
