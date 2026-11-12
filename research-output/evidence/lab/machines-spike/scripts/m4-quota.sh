#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike M4 (+ E2): a namespace quota lets one machine run and refuses a second one.
#   m4-quota.sh <a|b>     Root, lab VM only. Uses namespace machines-alice and deletes it afterwards.
set -uo pipefail; source "$(dirname "$0")/common.sh"
OPT=$1 NS=machines-alice; R=$OUT/m4-$OPT; mkdir -p "$R"; exec > >(tee "$R/m4.log") 2>&1
kubectl apply -f "$S/quota.yaml"; kubectl -n $NS get resourcequota machines -o yaml > "$R/quota.yaml"
"$S/$OPT/apply.sh" m1 $NS
"$S/m1-boot.sh" $OPT $NS m1 > /dev/null; mv "$OUT/m1-$OPT-m1" "$R/m1-boot"
pa=$(jq -r .pass "$R/m1-boot/m1.json"); echo "(a) first machine runs: $pa"
P1=$(podname $OPT $NS m1); CG=$(podcg $NS "$P1")
MAX=$(cat "$CG/memory.max" 2>/dev/null || echo missing); echo "(c) pod memory.max=$MAX"
kubectl -n $NS get pod "$P1" -o json | jq '{containers:[.spec.containers[]|{name,resources}], init:[(.spec.initContainers//[])[]|{name,resources}]}' > "$R/e2-pod-resources.json"
kubectl -n $NS get resourcequota machines -o json | jq .status > "$R/quota-after-m1.json"
q0=$(nqemu); echo "qemu processes before the second machine: $q0"
"$S/$OPT/apply.sh" m2 $NS; t0=$(ts); seen=""; qmax=$q0
while :; do
  el=$(python3 -c "print(round($(ts)-$t0))")
  q=$(nqemu); [ "$q" -gt "$qmax" ] && qmax=$q
  case $OPT in
    a) txt=$( { kubectl -n $NS get vm m2 -o json | jq -c .status; kubectl -n $NS get vmi m2 -o json 2>/dev/null | jq -c .status.conditions;
               kubectl -n $NS get events -o json | jq -c '.items[]|select(.involvedObject.name=="m2")|{kind:.involvedObject.kind,reason,message}'; } 2>/dev/null);;
    b) txt=$( { kubectl -n $NS get deploy m2 -o json | jq -c .status.conditions;
               kubectl -n $NS get events -o json | jq -c '.items[]|select(.involvedObject.name|startswith("m2"))|{kind:.involvedObject.kind,name:.involvedObject.name,reason,message}'; } 2>/dev/null);;
  esac
  if [ -z "$seen" ] && echo "$txt" | grep -qi 'exceeded quota'; then seen=$el; echo "quota refusal visible on the machine's objects at ${el}s"; echo "$txt" > "$R/refusal-evidence.txt"; fi
  [ "$el" -ge 120 ] && break; sleep 5
done
echo "$txt" > "$R/m2-objects-at-120s.txt"
[ -n "$seen" ] || echo "$txt" > "$R/refusal-evidence.txt"
kubectl -n $NS get pods -o wide | sed -E 's/([0-9]+\.){3}[0-9]+/<ip>/g' > "$R/pods.txt"
kubectl -n $NS get events --sort-by=.lastTimestamp | sed -E 's/([0-9]+\.){3}[0-9]+/<ip>/g' > "$R/events.txt"
pb=false; [ -n "$seen" ] && [ "$seen" -le 60 ] && [ "$qmax" -le "$q0" ] && pb=true
pc=false; [ "$MAX" != max ] && [ "$MAX" != missing ] && [ "$MAX" -le $((2*1024*1024*1024)) ] && pc=true
jq -n --arg o $OPT --argjson a "$pa" --argjson b $pb --argjson c $pc --arg seen "$seen" --arg max "$MAX" --argjson q0 "$q0" --argjson qmax "$qmax" \
  '{option:$o, a_first_runs:$a, b_second_refused:$b, c_memory_max:$c, pass:($a and $b and $c), refusal_visible_s:($seen|tonumber? // null),
    pod_memory_max:$max, qemu_before:$q0, qemu_max_after:$qmax}' | tee "$R/m4.json"
kubectl delete ns $NS --wait --timeout=10m
