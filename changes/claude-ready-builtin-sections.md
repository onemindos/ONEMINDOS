---
pr: pending
branch: claude/ready-builtin-sections
---
Built in apps in the dashboard (#617): a Built in tab in the Market (/built-in) and an Apps section in Settings (/settings/apps), both reading GET /v1/system-apps through @onemind/sdk. Each built-in app gets a licence card with its version, update channel and licence. Apps that can be switched off have a switch: switching off first reads which installed apps need it (GET /v1/apps/<id>/dependencies) and shows what else stops, then files an app.disable request that waits in Approvals; switching back on files app.enable. Apps that can never be switched off (Files, Approvals, Settings, Market, Updates, Backups, Notifications) show no switch. Deep links onemind://app/<id>/<route> now open the matching web path /apps/<id>/<route>, and a built-in app the dashboard draws itself opens its own screen there. The phone Built in section stays with wave P.
