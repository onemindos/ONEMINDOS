#!/bin/bash
# Strip systemd's OSC 3008 shell-context markers (Ubuntu 26.04, systemd 259),
# then apply the Debian spike's trimming and masking unchanged. Also keeps the
# RAUC error lines that only this spike produced.
#   trim-logs-ubuntu.sh <serial.log> > serial-trimmed.log
here=$(cd "$(dirname "$0")" && pwd)
TRIM=${TRIM:-$here/../../rauc-k3s-gate/scripts/trim-logs.sh}
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
perl -pe 's/\e\][^\a\e]*(?:\a|\e\\)//g; s/\e?\]3008;[^\\\n]*\\//g' "$1" > "$tmp"
{ bash "$TRIM" "$tmp"; grep -a -n -E 'Failed mounting bundle|Unexpected dm-verity|Call to Reboot failed|K3S-FRESH' "$tmp" | cut -c1-260 | sed 's/^/[extra] /'; }
