#!/bin/bash
# Trim a raw serial log to the lines that carry evidence, and mask VM-internal
# addresses (QEMU user-net 10.0.2.x / fec0:: and any RFC1918) as <vm-private-ip>.
#   trim-logs.sh <serial.log> > serial-trimmed.log
grep -a -E '#####|MENDER-GRUB|Rolling back|Booting new update|HEALTH-GATE|MENDER-CLI|BAD-BOOT|BAD-HANG|Kernel panic|watchdog|WRITE-PROGRESS|Installing|Installed|Committ|Rolled back|No update|Reboot required|requested a reboot|ignature|verif|--- state|^ONEMIND_VERSION|^mender_boot_part=|^upgrade_available=|^bootcount=|^artifact=|^/dev/vda|^(apps|kube-system|onemind-system) ' "$1" \
 | grep -a -v -E 'echo __R|grep -E|grep -v' \
 | sed -E -e 's/10\.0\.2\.[0-9]+/<vm-private-ip>/g' -e 's/fec0:[0-9a-f:]+/<vm-private-ip>/g' \
         -e 's/(192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]+\.[0-9]+/<vm-private-ip>/g' \
 | cut -c1-260
