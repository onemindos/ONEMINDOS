#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LT-X86-05540: read-only probes for the Dell Latitude 5540 client test. It changes nothing on the
# laptop and never actuates the hub (GET /healthz only). Output goes through ../common/redact.sh.
#   sh client-probe.sh snapshot LABEL      write snap-LABEL.txt (radios, audio, camera, displays, battery, sleep count, hub)
#   sh client-probe.sh compare A B         show what changed between two snapshots (snap-A.txt, snap-B.txt)
#   sh client-probe.sh wan-watch           poll the hub, log UP/DOWN transitions with seconds since start
# Environment: HUB=http://<hub-ip>:8080 (required for hub lines and wan-watch), OUT=dir (default .),
# COUNT=polls for wan-watch (default 120), INTERVAL=seconds between polls (default 5).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-.}
have() { command -v "$1" >/dev/null 2>&1; }
section() { printf '== %s\n' "$1"; }
redact() { sh "$HERE/../common/redact.sh"; }

hub_state() {
  [ -n "${HUB:-}" ] || { echo "hub: HUB not set"; return 0; }
  have curl || { echo "hub: curl missing"; return 0; }
  if curl -fsS -m 3 -o /dev/null "$HUB/healthz" 2>/dev/null; then echo "hub: UP"; else echo "hub: DOWN"; fi
}

snapshot_body() {
  section "radios"
  if have rfkill; then rfkill list 2>&1 | grep -E '^[0-9]+:|blocked' || echo "rfkill: nothing"; else echo "rfkill: missing"; fi
  if have nmcli; then nmcli -t -f WIFI,WWAN radio 2>&1; nmcli -t -f DEVICE,TYPE,STATE device 2>&1 | grep -E 'wifi|ethernet' || true; fi
  if have bluetoothctl; then bluetoothctl show 2>&1 | grep -E 'Powered|Discoverable' || echo "bluetooth: no controller"; fi
  section "audio"
  if have wpctl; then wpctl status 2>&1 | grep -E 'Sinks:|Sources:|\*' | head -12; elif have pactl; then pactl list short sinks 2>&1; pactl list short sources 2>&1; else echo "audio: no wpctl or pactl"; fi
  section "camera"
  ls /dev/video* 2>/dev/null || echo "camera: no /dev/video*"
  if have v4l2-ctl; then v4l2-ctl --list-devices 2>&1 | head -8; fi
  section "displays"
  for s in /sys/class/drm/card*-*/status; do
    [ -e "$s" ] || continue
    n=$(basename "$(dirname "$s")"); printf '%s %s\n' "$n" "$(cat "$s")"
  done
  section "power"
  for p in /sys/class/power_supply/*; do
    [ -e "$p/type" ] || continue
    printf '%s type=%s status=%s capacity=%s online=%s\n' "$(basename "$p")" "$(cat "$p/type")" \
      "$(cat "$p/status" 2>/dev/null || echo -)" "$(cat "$p/capacity" 2>/dev/null || echo -)" "$(cat "$p/online" 2>/dev/null || echo -)"
  done
  section "sleep"
  echo "mem_sleep: $(cat /sys/power/mem_sleep 2>/dev/null || echo unknown)"
  echo "suspend_success: $(cat /sys/power/suspend_stats/success 2>/dev/null || echo unknown)"
  echo "suspend_fail: $(cat /sys/power/suspend_stats/fail 2>/dev/null || echo unknown)"
  echo "uptime_s: $(cut -d. -f1 /proc/uptime 2>/dev/null || echo unknown)"
  section "hub"
  hub_state
}

case "${1:-}" in
  snapshot)
    label=${2:?usage: client-probe.sh snapshot LABEL}
    case "$label" in (*[!A-Za-z0-9._-]*) echo "label: letters, digits, . _ - only" >&2; exit 2;; esac
    f="$OUT/snap-$label.txt"
    snapshot_body 2>&1 | redact > "$f"
    echo "wrote $f"
    ;;
  compare)
    a="$OUT/snap-${2:?usage: client-probe.sh compare A B}.txt"; b="$OUT/snap-${3:?usage: client-probe.sh compare A B}.txt"
    [ -f "$a" ] && [ -f "$b" ] || { echo "missing snapshot file" >&2; exit 2; }
    # uptime always differs; hide it so a real change stands out
    ta=$(mktemp); tb=$(mktemp)
    grep -v '^uptime_s' "$a" > "$ta"; grep -v '^uptime_s' "$b" > "$tb"
    if cmp -s "$ta" "$tb"; then echo "NO CHANGE"; else diff -u "$ta" "$tb" || true; fi
    rm -f "$ta" "$tb"
    ;;
  wan-watch)
    [ -n "${HUB:-}" ] || { echo "set HUB=http://<hub-ip>:8080" >&2; exit 2; }
    count=${COUNT:-120}; interval=${INTERVAL:-5}; prev=""; i=0
    while [ "$i" -lt "$count" ]; do
      cur=$(hub_state | sed 's/^hub: //')
      if [ "$cur" != "$prev" ]; then printf 't+%ss hub %s\n' "$((i * interval))" "$cur"; prev=$cur; fi
      i=$((i + 1)); [ "$i" -lt "$count" ] && sleep "$interval"
    done | redact
    ;;
  *) sed -n '3,9p' "$0" >&2; exit 2;;
esac
