---
pr: pending
branch: claude/suite-system-apps-framework
---
Built in apps, first slice: system apps can be switched off but never uninstalled. A signed list in the OS image (system-apps.json) is the only authority for which ids are system apps; the app schema gains spec.system, validate-apps and the catalog refuse a system claim outside apps/_system/ or off the list, and community sources can never claim it. The gateway adds app.disable and app.enable (owner approves, an agent may only request), which scale the workload to zero and keep volumes, secrets and settings, hide the app from GET /v1/apps and MCP, and answer 409 app_disabled on its routes. Removal of a system app is refused for everyone, and Files, Approvals, Settings and Market can never be switched off. New GET /v1/system-apps, SDK regenerated, and onemind apps built-in, disable and enable. Desktop and phone screens follow once the design is in the repo.
