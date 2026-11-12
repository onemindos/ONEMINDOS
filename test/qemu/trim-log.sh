#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Trim a raw serial log to the lines that carry evidence and mask VM-internal addresses
# (QEMU user-net 10.0.2.x / fec0:: and any RFC1918) as <vm-private-ip> (brief 30 rule 9).
# Port of evidence/lab/rauc-1152/scripts/trim-logs.sh.   trim-log.sh <serial.log> > trimmed.log
grep -a -E '#####|GRUB-RAUC|HEALTH-GATE|BAD-BOOT|BAD-HANG|Kernel panic|watchdog|pre-install: trial|Marking target|Copying image|writing data|LastError|signature|not allowed|rauc v?1\.15|bundle-formats|--- state|ONEMIND_VERSION|^ORDER=|^[AB]_(OK|TRY)=|Booted from|boot status|pending|status: |cloud-init|FAILED|^(apps|kube-system|onemind-system) ' "$1" \
 | grep -a -v -E 'echo __R|grep -E' \
 | sed -E -e 's/10\.0\.2\.[0-9]+/<vm-private-ip>/g' -e 's/fec0:[0-9a-f:]+/<vm-private-ip>/g' \
         -e 's/(192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]+\.[0-9]+/<vm-private-ip>/g' \
         -e 's/10\.4[23]\.[0-9]+\.[0-9]+/<pod-ip>/g' \
 | cut -c1-260
