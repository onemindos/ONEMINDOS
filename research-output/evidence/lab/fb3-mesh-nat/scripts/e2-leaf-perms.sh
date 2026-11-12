#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# E2 (exploratory): does a per-user permission on the hub's leafnode user stop leaf A
# from publishing on node B's subjects? Hub config reloaded with a deny for leaf-home-a.
set -uo pipefail; . "$(dirname "$0")/lib.sh"; L=$R/e2; mkdir -p $L
cp $R/nats/hub.conf $L/hub.conf.orig
python3 - $R/nats/hub.conf <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
s=s.replace('{ user: "leaf-home-a",', '{ user: "leaf-home-a", permissions: { publish: { deny: ["onemind.node.home-b.>"] } },', 1)
open(p,"w").write(s)
PY
HP=$(pgrep -f "nats-server -c $R/nats/hub.conf"); off=$(wc -l < $R/cloud-natshub.log)
nsx cloud $B/nats-server --signal reload=$HP; sleep 3
tail -n +$((off+1)) $R/cloud-natshub.log | grep -iE "reload|error|perm|leaf" | sed -E 's/^\[[0-9]+\] [0-9/]+ [0-9:.]+ //' > $L/hub-reload.log
nsx cloud curl -s 127.0.0.1:8222/leafz | jq -c '[.leafs[]|{name}]' > $L/leafz-after.txt
( nsx cloud timeout 12 $B/nats -s $NATS_HUB sub 'e2.>' --raw > $L/hub-received.txt 2>/dev/null ) & sleep 3
for i in 1 2 3; do nsx home-a $B/nats -s nats://127.0.0.1:4222 pub onemind.node.home-b.event.e2 "a-as-b-$i" >/dev/null 2>&1; nsx home-a $B/nats -s nats://127.0.0.1:4222 pub onemind.node.home-a.event.e2 "a-as-a-$i" >/dev/null 2>&1; done
wait
# core-NATS subjects observed on the hub (stream capture is separate; subscribe directly):
( nsx cloud timeout 10 $B/nats -s $NATS_HUB sub 'onemind.node.*.event.e2' > $L/hub-sub.txt 2>&1 ) & sleep 3
for i in 1 2 3; do nsx home-a $B/nats -s nats://127.0.0.1:4222 pub onemind.node.home-b.event.e2 "a-as-b-$i" >/dev/null 2>&1; nsx home-a $B/nats -s nats://127.0.0.1:4222 pub onemind.node.home-a.event.e2 "a-as-a-$i" >/dev/null 2>&1; done
wait
AS_B=$(grep -c 'a-as-b' $L/hub-sub.txt); AS_A=$(grep -c 'a-as-a' $L/hub-sub.txt)
tail -n +$((off+1)) $R/cloud-natshub.log | grep -iE "permission|violation" | sed -E 's/^\[[0-9]+\] [0-9/]+ [0-9:.]+ //' | head -5 > $L/hub-violations.log
log "E2 reload: $(tr '\n' ' ' < $L/hub-reload.log | cut -c1-200) | hub got A-as-B=$AS_B/3 A-as-A=$AS_A/3 | violations: $(head -2 $L/hub-violations.log | tr '\n' ' ' | cut -c1-200)"
res E2 OBSERVED "$(jq -n --argjson b $AS_B --argjson a $AS_A --arg v "$(head -3 $L/hub-violations.log)" --arg r "$(cat $L/hub-reload.log)" '{hub_received_a_publishing_as_b:$b,hub_received_a_publishing_as_a:$a,of:3,hub_log_violations:$v,reload_log:$r}')"
cp $L/hub.conf.orig $R/nats/hub.conf; nsx cloud $B/nats-server --signal reload=$HP
