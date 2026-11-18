---
pr: pending
branch: claude/146-system-controls
---
Add system controls (UMB-P09, issue 146, first slice). New routes under /v1/system: an owner-only redacted diagnostic bundle (versions, node health, recent actions and audit event names, with home paths, IP addresses, e-mail addresses, tailnet names and secret-looking values removed, tested against the public-repo hygiene patterns), the controls status, and requests for restart, shutdown and factory reset. Each control is a feature action in the ledger that waits for an owner approval; agents may ask for a restart or shutdown but never approve, only an owner may ask for a factory reset, which needs a typed phrase and is approved only with the owner's passkey. A new Troubleshoot page in the dashboard reaches all of it through the SDK. The gateway has no path to the host's power controls yet, so an approved control ends failed with that reason and never claims success; the host executor is the next step.
