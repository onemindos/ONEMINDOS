#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LoRa link check (#853): ThinkNode-M2 flashed MeshCore Companion (USB) on the hub. Passive only: it checks the
# kernel driver, finds the radio's serial port and runs link_check.py, which sends APP_START, DEVICE_QUERY and
# GET_STATS and nothing else. It never transmits and never sets frequency or power. See README.md.
#
#   test/lora/link-check/link-check.sh                 # full run (about 11 minutes: 10 min idle)
#   test/lora/link-check/link-check.sh --preflight-only
#   PORT=/dev/ttyUSB1 IDLE_SECONDS=600 OUT=./results test/lora/link-check/link-check.sh
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SYSFS=${LINKCHECK_SYSFS:-/sys}
OUT=${OUT:-./link-check-results/$(date -u +%Y%m%dT%H%M%SZ)}
IDLE_SECONDS=${IDLE_SECONDS:-600}
VID=1a86
PID=7522
PREFLIGHT_ONLY=0

case "${1:-}" in
  --preflight-only) PREFLIGHT_ONLY=1 ;;
  -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
  "") ;;
  *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
esac

mkdir -p "$OUT"
LOG="$OUT/preflight.txt"
: > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }
rc=0

say "== OneMind LoRa link check (#853), $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "kernel: $(uname -r)"
if [ -r /etc/os-release ]; then say "os: $(sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '"')"; fi
if command -v systemd-detect-virt >/dev/null 2>&1; then
  say "virtualisation: $(systemd-detect-virt 2>/dev/null || true) (if not 'none', record the USB passthrough in RESULTS.md)"
fi
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet ModemManager 2>/dev/null; then
  say "WARNING: ModemManager is running and may probe the serial port; stop it for this check"
fi

# 1. The ch341 driver is in this kernel and claims the CH340K's USB id.
if modinfo ch341 >/dev/null 2>&1; then
  if modinfo -F alias ch341 2>/dev/null | grep -qi "usb:v${VID}p${PID}d"; then
    say "ch341 module: works (present, claims ${VID}:${PID})"
  else
    say "ch341 module: partial (present, but no alias for ${VID}:${PID})"; rc=1
  fi
else
  say "ch341 module: fails (modinfo ch341 found no module)"; rc=1
fi

# 2. The radio is plugged in and its serial port is bound to ch341.
# The ch341 module registers two drivers: the USB interface (1-1:1.0) binds to
# "ch341" on the usb bus, and the ttyUSBn port under it binds to "ch341-uart" on
# the usb-serial bus (linux drivers/usb/serial/ch341.c). Both must hold.
drvname() { basename "$(readlink -f "$1/driver" 2>/dev/null || echo none)"; }
found=""
for t in "$SYSFS"/class/tty/ttyUSB*; do
  [ -e "$t/device" ] || continue
  name=$(basename "$t")
  dev=$(readlink -f "$t/device")
  intf=$(dirname "$dev")              # ttyUSBn -> USB interface
  usb=$(dirname "$intf")              # interface -> USB device
  port_drv=$(drvname "$dev")
  intf_drv=$(drvname "$intf")
  vid=$(cat "$usb/idVendor" 2>/dev/null || true)
  pid=$(cat "$usb/idProduct" 2>/dev/null || true)
  if [ "$vid:$pid" = "$VID:$PID" ]; then
    if [ "$intf_drv" = ch341 ] && [ "$port_drv" = ch341-uart ]; then
      say "$name bound to ch341: works (${vid}:${pid}, interface ch341, port ch341-uart)"; found=${found:-$name}
    else
      say "$name bound to ch341: fails (${vid}:${pid} interface bound to $intf_drv, port bound to $port_drv)"; rc=1
    fi
  fi
done
[ -n "$found" ] || { say "radio serial port: fails (no ttyUSB with ${VID}:${PID}; is the M2 plugged in?)"; rc=1; }

if [ "$PREFLIGHT_ONLY" = 1 ]; then
  say "preflight: $([ $rc -eq 0 ] && echo ok || echo FAILED) (log: $LOG)"
  exit $rc
fi
[ $rc -eq 0 ] || { say "preflight FAILED: fix the lines above before the radio check"; exit $rc; }

# 3. The passive radio check (link_check.py: allowlisted reads only).
PORT=${PORT:-/dev/$found}
command -v python3 >/dev/null 2>&1 || { say "python3 is needed for the radio check"; exit 1; }
say "radio check on $PORT, idle ${IDLE_SECONDS}s; results in $OUT"
set +e
python3 -I "$HERE/link_check.py" run --port "$PORT" --out "$OUT" --idle-seconds "$IDLE_SECONDS" | tee -a "$LOG"
rc=${PIPESTATUS[0]}
set -e
python3 -I "$HERE/link_check.py" decode "$OUT/captured-frames.json" | tee -a "$LOG" || rc=1
say "done: copy the numbers from $OUT/report.json into RESULTS.md (exit $rc)"
exit "$rc"
