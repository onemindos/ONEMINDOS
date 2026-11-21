#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LT-MACH-2 on a real x86 hub, through the real gateway path (#281, docs/umbrel2/machines.md §4.12).
# Run it ON the hub (the Beelink) as the owner, with `onemind` logged in and KubeVirt + CDI installed
# (the extension, MACH-2; until it ships, install the pinned upstream manifests the spike used).
#   IMAGE_URL=https://.../debian-13-genericcloud-amd64.qcow2 bash lt-mach-2-hub.sh [outdir]
# It writes plain-text results to outdir (default ./lt-mach-2-results). Nothing is deleted except the
# test machine it creates. Every change is an approval: you tap `onemind actions approve` when asked.
set -euo pipefail

IMAGE_URL="${IMAGE_URL:?set IMAGE_URL to an https cloud image (amd64 qcow2)}"
OUT="${1:-./lt-mach-2-results}"
NAME="${MACHINE_NAME:-ltmach2}"
mkdir -p "$OUT"
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$OUT/log.txt"; }
mem_used_mb() { awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{print int((t-a)/1024)}' /proc/meminfo; }

approve() { # request id -> wait for the owner's approval (this script never approves for you)
  local id="$1"
  log "Waiting for approval: run  onemind actions approve $id  in another terminal"
  until [ "$(onemind --json actions info "$id" | python3 -c 'import json,sys;print(json.load(sys.stdin)["state"])')" != awaiting_approval ]; do sleep 3; done
  log "action $id is $(onemind --json actions info "$id" | python3 -c 'import json,sys;print(json.load(sys.stdin)["state"])')"
}
request() { onemind --json --quiet machines "$@" >/dev/null; onemind --json actions list --pending --limit 1 | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["id"])'; }

log "M0 preflight: /dev/kvm $([ -e /dev/kvm ] && echo present || echo MISSING), RAM used $(mem_used_mb) MB"
onemind --json machines capabilities | tee "$OUT/capabilities.json" >/dev/null
echo "idle_mb_before=$(mem_used_mb)" >"$OUT/memory.txt"

log "M1 boot: request create + start"
approve "$(request create "$NAME" --ram-mb 2048 --cpus 2 --disk-gb 20 --image-url "$IMAGE_URL")"
echo "idle_mb_created_stopped=$(mem_used_mb)" >>"$OUT/memory.txt"
approve "$(request start "$NAME")"
for _ in $(seq 1 60); do
  kubectl get vmi "$NAME" -n machines -o jsonpath='{.status.phase}' 2>/dev/null | grep -q Running && break; sleep 5
done
kubectl get vmi "$NAME" -n machines -o wide | tee "$OUT/m1-vmi.txt"
sleep 60  # let the guest settle before the idle measurement
echo "idle_mb_one_vm=$(mem_used_mb)" >>"$OUT/memory.txt"
kubectl top pods -A --no-headers 2>/dev/null | grep -E 'kubevirt|cdi|virt-launcher' | tee "$OUT/m5-top.txt" || true

log "M2 console: ticket (owner only)"
onemind --json machines console "$NAME" | tee "$OUT/m2-console-ticket.json" >/dev/null

log "M4 quota: a machine bigger than the box allows must be refused at request"
if onemind machines create "${NAME}-big" --ram-mb 262144 --cpus 2 --disk-gb 20 --image-url "$IMAGE_URL" 2>"$OUT/m4-refused.txt"; then
  log "M4 FAIL: the oversized machine was accepted"; else log "M4 PASS: refused: $(tr '\n' ' ' <"$OUT/m4-refused.txt")"; fi

log "Cleanup: request stop + delete of $NAME"
approve "$(request stop "$NAME")"
approve "$(request delete "$NAME" --confirm "$NAME")"
log "done. Send $OUT back; M3 (freeze) needs the guest agent and is run with the spike's m3-freeze.sh."
