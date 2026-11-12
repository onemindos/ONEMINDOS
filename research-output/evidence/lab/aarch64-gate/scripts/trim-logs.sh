#!/bin/bash
# Trim a raw serial log to the lines that carry evidence, and mask VM-internal
# addresses (QEMU user-net 10.0.2.x / fec0:: and any RFC1918) as <vm-private-ip>.
#   trim-logs.sh <serial.log> > serial-trimmed.log
grep -a -E '#####|GRUB-RAUC|HEALTH-GATE|BAD-BOOT|BAD-HANG|Kernel panic|watchdog|pre-install: trial|Marking target|Copying image|writing data|LastError|signature|not allowed|rauc v?1\.15|ARCH=|bundle-formats|--- state|^ONEMIND_VERSION|^ORDER=|^[AB]_(OK|TRY)=|Booted from|boot status|pending|^(apps|kube-system|onemind-system) ' "$1" \
 | grep -a -v -E 'echo __R|grep -E' \
 | sed -E -e 's/10\.0\.2\.[0-9]+/<vm-private-ip>/g' -e 's/fec0:[0-9a-f:]+/<vm-private-ip>/g' \
         -e 's/(192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]+\.[0-9]+/<vm-private-ip>/g' \
 | cut -c1-260
