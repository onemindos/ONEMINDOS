---
pr: 1115
branch: claude/s2b-box-care
---
OS image: box care for a 24/7 machine (Step 2b). Adds fwupd (firmware updates through LVFS, the automatic refresh timer is masked so only the owner starts a refresh), lm-sensors, rasdaemon, udisks2 (USB drives are detected but never auto-mounted) and, on x86 only, thermald and the signed fwupd UEFI binary. Enables a weekly fstrim limited to /data. The fwupd, rasdaemon and udisks2 state lives on /data through four new bind mounts, so it survives reboots and A/B updates. New first-boot checks F24, F24b and F24c (pre-registered in CRITERIA-FIRSTBOOT.md section 18) and static tests in test/unit/test_image_boxcare.py.
