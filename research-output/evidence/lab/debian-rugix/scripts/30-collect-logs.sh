#!/usr/bin/env bash
# Copy trimmed, redacted logs from the lab dir into the repo's logs/ folder.
# Redacts RFC1918 / CGNAT / IPv6 site-local addresses and the host's home path.
# Usage: LAB=<lab dir> ./30-collect-logs.sh <run-dir-name> <dest-name>
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); LAB=${LAB:?}; SRC="$LAB/$1"; DEST="$HERE/../logs/$2"; mkdir -p "$DEST"
redact() {
  sed -E -e 's/\x1b\[[0-9;=?]*[A-Za-z]//g' -e 's/\r//g' \
    -e 's/\b(10\.[0-9]{1,3}|192\.168|172\.(1[6-9]|2[0-9]|3[01])|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7]))\.[0-9]{1,3}(\.[0-9]{1,3})?\b/<private-ip>/g' \
    -e 's/fec0:[0-9a-f:]+/<site-local-ip6>/g' -e "s|$HOME|~|g"
}
# Events without the per-percent progress spam.
grep -av UpdateProgress "$SRC/events.log" | redact > "$DEST/events.log"
# Serial console: boot selection, kernel cmdline, gate decisions, reboots, Rugix init lines.
redact < "$SRC/serial.log" | grep -a -E "onemind-health-gate|Loading environment|Booting to spare|Environment is corrupt|Kernel command line|reboot: Restarting|Rugix|rugix|bootstrap|panic|watchdog|login:|EXT4-fs.*(error|recover)|fsck" > "$DEST/serial-filtered.log" || true
wc -l "$DEST"/*.log
