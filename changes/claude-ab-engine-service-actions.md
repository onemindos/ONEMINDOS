---
pr: pending
branch: claude/ab-engine-service-actions
---
Service logs and restart as an approved action (#636). GET /v1/system/services/{unit}/logs reads a registry unit's journal from the host service, with every line passed through the app-log redaction filter (tokens, keys, passwords, e-mail and IP addresses masked) and follow=true streaming for at most 15 minutes, owner only. POST /v1/system/services/{unit}/restart files a service.restart action for a unit the image's registry marks restartable: an owner or an agent may ask, only the owner approves, always with a passkey, and the host service checks the registry again and journals the restart by action id. A unit that is not restartable answers 403, and rescue, first-boot, host and data-layout units never show a restart button even if the registry or the host says otherwise. The CLI gains onemind services logs (-f, -n) and onemind services restart, which prints the approval id.
