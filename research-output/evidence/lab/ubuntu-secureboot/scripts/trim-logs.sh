#!/bin/bash
# Trim a full serial log to the lines the verdicts use, and mask host paths.
#   bash trim-logs.sh <full-serial.log> > <trimmed.log>
set -euo pipefail
grep -a -E '^#####|SB-REPORT|secureboot:|Secure boot|lockdown|DATA:|BONUS-PCR11|HEALTH-GATE|EFI-ENTRIES|BdsDxe|Access Denied|Security Violation|^Boot(Current|Next|Order)|Booted from|Activated:|boot status|LastError|not allowed|PROBE-|probe:|Failed to get bootname|bootentry not known|^rauc v?1\.|ONEMIND_VERSION|onemind\.version=|--- state:|reboot: Power down' "$1" \
  | grep -a -v '^root@onemind-lab' \
  | sed -E 's#/Users/[^/ ]+#~#g; s/\x1b\[[0-9;?]*[A-Za-z]//g'
