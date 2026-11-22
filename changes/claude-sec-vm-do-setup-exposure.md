---
pr: pending
branch: claude/sec-vm-do-setup-exposure
---
Security fix: the DigitalOcean (vm-do) image served the first-boot setup wizard on its public address. The wizard needs no login and returns the owner token, so anyone who reached a droplet without a role first could own it. vm-do now ships the same two drop-ins as the generic cloud board: the wizard is denied on every address except the instance itself, and first boot waits for cloud-init's network stage. A unit test now fails if any board with cloud: true lacks them. Still open: first boot does not read DigitalOcean's config-2 ConfigDrive label directly.
