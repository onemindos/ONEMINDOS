---
pr: 1272
branch: claude/ui-access-grants
---
Settings > Permissions gains Data access and Hardware access. Data access lists the live data-commons grants (who may read, add to or count one kind of data, and until when) and says how many have ended; an owner can revoke one after a confirm, anyone else sees only their own. Hardware access (owner only) lists the apps given a device, the GPU, the host network or real-time scheduling, with the reason, and revokes one after a confirm. The CLI gains `onemind grants data list` and `revoke` and `onemind grants host list` and `revoke`, with --all, --app and --json. All of it calls the existing /v1/data/grants and /v1/host-grants routes; grants are still asked for and approved only through the approval queue, and revoking stays the owner-only call the gateway audits. Dashboard screens that call the gateway through the SDK now say "the box did not answer" when it does not, instead of showing a raw error. UI parity report row M3.
