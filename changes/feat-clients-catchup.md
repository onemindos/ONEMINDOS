---
pr: pending
branch: feat/clients-catchup
---
Mobile and desktop clients catch up with the gateway APIs the dashboard already uses (Wave G item 6, lane A10). The phone gains app lifecycle requests with a plan preview (start, stop, restart, update, remove), Backups (status, destinations, runs, back up now, check latest), Automation (rules, pause, turn off or on), read-only Files and Migration, and owner-only first-run settings (contract 12.41). The desktop tray gains a Manage view with app lifecycle, backups and first-run settings. Every change is filed as an action request bound to the plan hash and shows its approval state; backup requests always send approve false, restore and delete-data stay on the dashboard, and a migration copy (which needs a kubeconfig) is never entered on a client. Owner-only parts are hidden or disabled for others and handle 403. Desktop automation, files and migration views are left for a follow-up.
