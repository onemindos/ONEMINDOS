---
pr: 1098
branch: claude/work-port-from-798
---
Port the missing pieces of the old Work PR #798 onto the landed Work engine (#644): quick-add text (`POST /v1/work/quick-add`: #project, @label, p1-p4, +person-id, dates and times in the caller's time zone) and the `onemind work` CLI (add, list, today, upcoming, inbox, done) through the Go SDK. Comments, sections and repeat rules follow in a stacked PR.
