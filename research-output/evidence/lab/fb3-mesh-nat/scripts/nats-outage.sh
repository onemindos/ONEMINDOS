#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# T3 (part 2): cut the hub's only link for OUTAGE_S seconds; each home publishes 500 events
# (seq 101..600) evenly spread, each acked by its LOCAL leaf; restore; verify within 300 s.
set -uo pipefail; . "$(dirname "$0")/lib.sh"
OUTAGE_S=${OUTAGE_S:-1800}; N=500; L=$R/nats-t; mkdir -p $L
INTERVAL=$(python3 -c "print(($OUTAGE_S-30)/$N)")
log "T3 cutting hub link for ${OUTAGE_S}s, interval ${INTERVAL}s"
nsx cloud ip link set eth0 down; CUT=$(date +%s.%N)
for n in home-a home-b; do ( for i in $(seq 101 600); do
    tgt=$(python3 -c "print($CUT+5+($i-101)*$INTERVAL)"); now=$(date +%s.%N); d=$(python3 -c "print(max(0,$tgt-$now))"); sleep $d
    if out=$(nsx $n $B/nats -s nats://127.0.0.1:4222 pub --jetstream onemind.node.$n.event.lab.tick "$n:$i" 2>&1); then echo "$(ts) ack $i"; else echo "$(ts) NOACK $i $out"; fi
  done > $L/outage-$n.log ) & done
# evidence the link is really down mid-outage
sleep 60; nsx home-a ping -c2 -W2 $HUB_PUB > $L/outage-ping-hub-public.txt 2>&1; tsc home-a status > $L/outage-ts-status-a.txt 2>&1
nsx home-a curl -s 127.0.0.1:8222/leafz > /dev/null 2>&1; nsx cloud curl -s 127.0.0.1:8222/leafz | jq '.leafs|length' > $L/outage-hub-leafcount.txt
wait
now=$(date +%s.%N); rem=$(python3 -c "print(max(0,$CUT+$OUTAGE_S-$now))"); sleep $rem
nsx cloud ip link set eth0 up; RESTORE=$(date +%s); log "T3 link restored after $(python3 -c "print(round($RESTORE-$CUT))")s"
nsx cloud tc qdisc replace dev eth0 root netem delay 20ms
c=0; for t in $(seq 1 150); do c=$(nsx cloud $B/nats -s $NATS_HUB stream info NODE_EVENTS --json 2>/dev/null | jq -r .state.messages); [ "$c" = 1200 ] && break; sleep 2; done
SYNC_S=$(( $(date +%s)-RESTORE )); log "T3 hub NODE_EVENTS=$c after ${SYNC_S}s"
nsx cloud $B/nats -s $NATS_HUB stream info NODE_EVENTS --json > $L/node_events_info.json
: > $L/hub-dump.tsv; last=$(jq -r .state.last_seq $L/node_events_info.json)
for s in $(seq 1 $last); do nsx cloud $B/nats -s $NATS_HUB stream get NODE_EVENTS $s --json 2>/dev/null | jq -r '[.seq,.subject,(.data|@base64d)]|@tsv' >> $L/hub-dump.tsv; done
python3 - "$L" "$c" "$SYNC_S" <<'PY'
import json, sys, collections
L, count, sync = sys.argv[1], sys.argv[2], int(sys.argv[3])
seqs = collections.defaultdict(list)
for line in open(f"{L}/hub-dump.tsv"):
    seq, subj, data = line.rstrip("\n").split("\t")
    node, i = data.split(":"); seqs[node].append(int(i))
acks = {n: sum(1 for l in open(f"{L}/outage-{n}.log") if " ack " in l) for n in ("home-a", "home-b")}
noack = {n: sum(1 for l in open(f"{L}/outage-{n}.log") if "NOACK" in l) for n in ("home-a", "home-b")}
per = {}
ok = count == "1200" and sync <= 300
for n in ("home-a", "home-b"):
    v = seqs.get(n, [])
    exact = v == list(range(1, 601))
    per[n] = {"received": len(v), "unique": len(set(v)), "exactly_1_to_600_in_order": exact,
              "local_acks_during_outage": acks[n], "unacked_during_outage": noack[n]}
    ok = ok and exact and acks[n] == 500 and noack[n] == 0
out = {"hub_messages": int(count) if count.isdigit() else count, "seconds_to_sync_after_restore": sync, "per_node": per}
json.dump(out, open(f"{L}/t3-verify.json", "w"), indent=1)
print(("PASS" if ok else "FAIL") + " " + json.dumps(out))
PY
