#!/bin/bash
# AK-7 part 1 (source box): an online backup taken by the running server, peak RSS sampled meanwhile.
set -euo pipefail; T=AK-7; . /root/aklab/lib.sh
B=/var/lib/private/kanidmd/backups
stamp "AK-7 part 1: online backup on the running source box"
run "systemctl is-active kanidmd; grep -A4 online_backup /etc/kanidmd/server.toml"
START=$(( $(date -u +%s) + 1 )); P=$(kpid); peak=0; f=""
while :; do
  r=$(awk '/^VmRSS/{print $2}' /proc/$P/status); [ "$r" -gt "$peak" ] && peak=$r
  if [ -z "$f" ]; then f=$(find $B -name 'backup-*' -newermt "@$START" | head -1); [ -n "$f" ] && FOUND=$(date -u +%s); fi
  [ -n "$f" ] && [ $(( $(date -u +%s) - FOUND )) -ge 5 ] && break
  [ $(( $(date -u +%s) - START )) -gt 150 ] && break
  sleep 0.2
done
note "backup file written while running: ${f:-NONE} (waited $(( ${FOUND:-0} - START )) s); kanidmd PID unchanged: $([ "$(kpid)" = "$P" ] && echo yes || echo no)"
run "systemctl is-active kanidmd; curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo"
run "ls -l --time-style=+%FT%TZ $B; journalctl -u kanidmd --no-pager -o cat | grep -iE 'backup' | tail -4"
run "cp '$f' /root/aklab/restore-input.json.gz; sha256sum /root/aklab/restore-input.json.gz; stat -c '%s bytes' /root/aklab/restore-input.json.gz"
T=AK-9; note "peak kanidmd RSS while the online backup ran (0.2 s samples): ${peak} kB"; run "rss"
