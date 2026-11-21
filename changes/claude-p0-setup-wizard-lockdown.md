---
pr: pending
branch: claude/p0-setup-wizard-lockdown
---
Security: the first-boot setup wizard no longer lets anyone on the network claim a new box. The page on the box itself needs nothing, but a phone or computer on the LAN must type an 8-digit one-time code shown on the box screen and console (five wrong tries change the code). Once an owner exists the wizard refuses every LAN request and exits. onemind-setup.service is now sandboxed: read-only system, no new privileges, a syscall filter, only three capabilities, no kernel or namespace access. Still open: running the web part as a non-root user.
