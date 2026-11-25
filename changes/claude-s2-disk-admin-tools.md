---
pr: pending
branch: claude/s2-disk-admin-tools
---
OS image: disk and admin tools. Adds smartmontools (smartctl for the storage health check, smartd masked), gdisk, btrfs-progs, bash-completion, less, nano, rsync, htop, jq, iputils-ping, pciutils, usbutils, dmidecode and ethtool to the Debian and Ubuntu base package lists, with a build-time check that each command exists. New first-boot check F13 (pre-registered in CRITERIA-FIRSTBOOT.md section 9) runs smartctl, sgdisk, btrfs and each admin tool on the booted image.
