---
pr: 1114
branch: claude/s3-video-console
---
OS image: hardware video decode and the console keyboard (Step 3). The x86 boards (x86_64-efi and x86_64-efi-nvidia, not the cloud, ARM or VM boards) add the VA-API drivers intel-media-va-driver and mesa-va-drivers from Debian main plus vainfo. The base image adds console-setup and keyboard-configuration; because the root is read-only their Debian units are masked and onemind-console-keyboard.service loads the layout kept in /data/onemind/console/keyboard (seeded as US), so it survives reboots and A/B updates. New first-boot checks F29 (packages, drivers and vainfo start-up; QEMU has no GPU), F30 (layout kept after reboot) and F31 (kept after the A/B update) are pre-registered in CRITERIA-FIRSTBOOT.md section 12.
