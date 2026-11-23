---
pr: 995
branch: claude/sso-kanidm-lab
---
Kanidm lab run 1 for UMB-ACCT-1 (issue 403): Kanidm v1.12.0 as a systemd host service on fresh Debian 13 VMs. Host service, offline first boot with a passkey, household groups, OIDC with group scope and claim maps, one-use reset links, guest expiry, backup and restore with the same passkey, and revocation all pass. TOTP replay fails (Kanidm accepts the same code twice within its time window), so the verdict goes to the founder; the identity provider is not switched. Footprint about 70 MB RAM; the unstripped binaries are the only large number.
