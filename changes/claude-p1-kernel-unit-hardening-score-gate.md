---
pr: pending
branch: claude/p1-kernel-unit-hardening-score-gate
---
Kernel and service hardening for the image with a CI score gate: a KSPP sysctl baseline, explicit AppArmor and kernel self-protection switches on the boot command line, k3s protect-kernel-defaults paired with the sysctls it needs, sandboxes for tailscaled, the local API stand-in and the root first-boot oneshots, and a unit test that fails when any OneMind systemd unit scores above its recorded exposure ceiling (systemd-analyze security).
