#!/usr/bin/env bash
# W8-1 NATS leaf store-and-forward spike. Runs inside the disposable VM only.
set -u
D=$(cd "$(dirname "$0")" && pwd)
H=nats://127.0.0.1:4222; LF=nats://127.0.0.1:4223
pkill nats-server 2>/dev/null; sleep 1; rm -rf /tmp/w8; mkdir -p /tmp/w8
ts(){ date -u +%H:%M:%S; }
nats-server -c "$D/hub.conf" >/tmp/w8/hub.log 2>&1 & HUB=$!
nats-server -c "$D/leaf.conf" >/tmp/w8/leaf.log 2>&1 &
sleep 3
echo "$(ts) step1 create streams"
nats -s $LF stream add TEL --subjects 'tel.>' --storage file --replicas 1 --retention limits --discard old --max-msgs=-1 --max-bytes=-1 --max-age=0 --max-msg-size=-1 --dupe-window 2m --no-allow-rollup --no-deny-delete --no-deny-purge --defaults >/dev/null && echo "leaf TEL created"
nats -s $H stream add --config "$D/tel_hub.json" >/dev/null && echo "hub TEL_HUB created"
echo "$(ts) step2 publish 1..100 at leaf"
for i in $(seq 1 100); do nats -s $LF pub --jetstream tel.greenhouse1.air.temp "$i" >/dev/null 2>&1; done
sleep 3
echo "hub TEL_HUB msgs: $(nats -s $H stream info TEL_HUB --json | jq .state.messages)"
echo "$(ts) step3 stop hub"; kill $HUB; wait $HUB 2>/dev/null; sleep 2
echo "$(ts) step4 publish 101..600 at leaf with hub down"
for i in $(seq 101 600); do nats -s $LF pub --jetstream tel.greenhouse1.air.temp "$i" >/dev/null 2>&1 || echo "pub $i failed"; done
echo "leaf TEL msgs: $(nats -s $LF stream info TEL --json | jq .state.messages)"
echo "$(ts) step5 publish 50 core-NATS msgs on evt.test.outage at leaf (no stream)"
for i in $(seq 1 50); do nats -s $LF pub evt.test.outage "$i" >/dev/null 2>&1; done
echo "$(ts) step6 restart hub"
nats-server -c "$D/hub.conf" >>/tmp/w8/hub.log 2>&1 &
( timeout 20 nats -s $H sub 'evt.test.outage' --raw > /tmp/w8/core_after.txt 2>/dev/null ) &
T0=$(date +%s)
for t in $(seq 1 60); do
  sleep 1
  n=$(nats -s $H stream info TEL_HUB --json 2>/dev/null | jq -r .state.messages 2>/dev/null)
  [ "$n" = "600" ] && break
done
echo "$(ts) step7 hub TEL_HUB msgs: $n after $(( $(date +%s)-T0 ))s"
nats -s $H stream info TEL_HUB --json | jq '{messages:.state.messages,first:.state.first_seq,last:.state.last_seq,sources:[.sources[]|{name,lag,active}]}'
# verify payloads 1..600, no gaps, no dupes
: > /tmp/w8/payloads.txt
for s in $(seq 1 600); do nats -s $H stream get TEL_HUB $s --json 2>/dev/null | jq -r .data | base64 -d >> /tmp/w8/payloads.txt; echo >> /tmp/w8/payloads.txt; done
TOT=$(grep -c . /tmp/w8/payloads.txt); UNIQ=$(sort -n /tmp/w8/payloads.txt | grep . | uniq | wc -l)
EXPECT=$(seq 1 600 | sort -n | md5sum | cut -d' ' -f1); GOT=$(grep . /tmp/w8/payloads.txt | sort -n | uniq | md5sum | cut -d' ' -f1)
echo "payload lines=$TOT unique=$UNIQ set_matches_1..600=$([ "$EXPECT" = "$GOT" ] && echo yes || echo no)"
wait
echo "core-NATS msgs seen at hub after restart: $(grep -c . /tmp/w8/core_after.txt)"
grep -iE "leafnode connection|JetStream domain|error" /tmp/w8/leaf.log | tail -5
