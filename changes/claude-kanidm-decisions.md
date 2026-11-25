---
pr: 1163
branch: claude/kanidm-decisions
---
Founder decision D-030 on Kanidm (from the UMB-ACCT-1 run 2 lab, PR 1141): the Kanidm pin moves to 1.12.1 (upstream HIGH unauthenticated DoS fix) in os/versions.lock.yaml with its tag commit and git-archive hash, and deploy/check-pins.py keeps the plan and deploy/ on that version. New os/identity/kanidm/provision.yaml is the provisioning plan CORE-SEC-10 will run: one canonical sign-in name onemind.local (the passkey RP ID), the four household role groups, and a passkeys-only group (credential-type-minimum passkey) that every newly invited person joins, while existing people keep TOTP as a fallback. kanidm-provision.py checks the plan and prints server.toml and the kanidm CLI steps; it does not install or run Kanidm yet. Phone resolution of onemind.local over the mesh is still UMB-ACCT-13.
