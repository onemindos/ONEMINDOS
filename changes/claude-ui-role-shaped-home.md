---
pr: pending
branch: claude/ui-role-shaped-home
---
UX-01 (#206): the dashboard is shaped by role. Whether you can approve or request now comes from the scopes `GET /v1/me` reports, so a guest or child is no longer offered buttons that fail. Guests and children get a simple Home (my apps, my requests, family status) with no Needs you, Approvals dock icon or job pill. Machines and Alerts join the Pro screens. Acknowledge, Resolve and Ask to fix on Alerts follow scope. In the Market the install buttons are disabled with the reason, and a child is told to ask a parent. Sources and Import Compose are hidden from non-owners. The gateway still enforces every route.
