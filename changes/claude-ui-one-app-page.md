---
pr: pending
branch: claude/ui-one-app-page
---
FD-06: one page per app at /apps/<id> (the link the gateway already puts in app notifications), opened as a window. A state dot combines health, restarts, the last scan and a waiting update, and any fact that could not be read makes it grey instead of green. A facts card and the tabs Usage, Logs, Alerts (this app's alerts and notifications), Backups (its restore points), Access (roles and people, read only), Trust and Help, plus a read-only Workloads tab for owners and adults. Nothing on the page changes anything: restart, update, remove and sharing stay approval requests. Installed > manage links to it. The screen registry gains a `hidden` flag for routed screens that have no nav entry.
