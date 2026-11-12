#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike M1: wait (from the recorded create time) for the guest agent and an SSH uname.
#   m1-boot.sh <a|b> <namespace> <machine> [deadline_s]   Root, lab VM only.
set -uo pipefail; source "$(dirname "$0")/common.sh"
OPT=$1 NS=$2 NAME=$3; DL=${4:-600}; [ "$(cat $W/accel)" = tcg ] && DL=$((DL*3))
R=$OUT/m1-$OPT-$NAME; mkdir -p "$R"; exec > >(tee "$R/m1.log") 2>&1
t0=$(cat $W/created-$OPT-$NAME); agent=""; uname=""
while :; do
  el=$(python3 -c "print(round($(ts)-$t0))")
  [ -z "$agent" ] && agent_ok $OPT $NS $NAME && { agent=$el; echo "agent connected at ${el}s"; }
  [ -z "$uname" ] && [ -n "$agent" ] && u=$(gssh $OPT $NS $NAME uname -m 2>/dev/null) && [ "$u" = aarch64 ] && { uname=$el; echo "ssh uname -m = $u at ${el}s"; }
  [ -n "$agent" ] && [ -n "$uname" ] && break
  [ "$el" -ge "$DL" ] && break
  sleep 5
done
P=$(podname $OPT $NS $NAME)
case $OPT in
  a) kubectl -n $NS logs "$P" -c guest-console-log > "$R/serial.log" 2>&1 || echo "no guest-console-log container" > "$R/serial.log"
     kubectl -n $NS get vmi $NAME -o json | jq '{phase:.status.phase, conditions:.status.conditions, guestOSInfo:.status.guestOSInfo, nodeName:.status.nodeName}' > "$R/vmi-status.json"
     kubectl -n $NS get dv $NAME-disk -o json | jq '.status' > "$R/dv-status.json" 2>/dev/null || true;;
  b) kubectl -n $NS exec "$P" -c qemu -- cat /run/vm/serial.log > "$R/serial.log" 2>&1
     kubectl -n $NS logs "$P" -c qemu > "$R/qemu-stdout.log" 2>&1
     kubectl -n $NS exec "$P" -c qemu -- qga.py guest-info | jq '{version:.return.version}' > "$R/qga-info.json" 2>&1;;
esac
gssh $OPT $NS $NAME 'cat /etc/os-release | head -3; uname -r; systemctl is-active qemu-guest-agent; findmnt -no FSTYPE /; free -m' > "$R/guest.txt" 2>&1 || true
pass=false; [ -n "$agent" ] && [ -n "$uname" ] && [ "${uname}" -le "$DL" ] && pass=true
jq -n --arg o $OPT --arg n $NAME --arg a "$agent" --arg u "$uname" --argjson dl $DL --argjson p $pass \
  '{option:$o, machine:$n, agent_connected_s:($a|tonumber? // null), ssh_uname_s:($u|tonumber? // null), deadline_s:$dl, pass:$p}' | tee "$R/m1.json"
