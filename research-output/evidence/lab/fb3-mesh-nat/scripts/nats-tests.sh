#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# T3 (part 1): negative auth checks + 100 events per node before the outage.
set -uo pipefail; . "$(dirname "$0")/lib.sh"; S=$(cd "$(dirname "$0")" && pwd)
HUB=$(tsip cloud); L=$R/nats-t; mkdir -p $L; HL=$R/cloud-natshub.log
nsx cloud ss -ltn | grep -E ':7422 ' > $L/ss-7422.txt
LISTEN_OK=$(grep -c "$HUB:7422" $L/ss-7422.txt); LISTEN_OTHER=$(grep -vc "$HUB:7422" $L/ss-7422.txt)
PUBLIC=$(nsx home-a timeout 5 ncat -z -w3 $HUB_PUB 7422 && echo open || echo closed)
leafz_has(){ nsx cloud curl -s 127.0.0.1:8222/leafz | jq -r '.leafs[].name' | grep -c "^$1$"; true; }
neg(){ # name url tlsblock env-prefix ; connected = the hub's /leafz listed it at any of 4 samples
  local off=$(wc -l < $HL) seen=0
  printf 'server_name: neg-%s\nlisten: 127.0.0.1:4299\nleafnodes { remotes: [ { url: "%s" %s } ] }\n' "$1" "$2" "$3" > $L/neg-$1.conf
  ( nsx home-a env $4 timeout 12 $B/nats-server -c $L/neg-$1.conf > $L/neg-$1-leaf.log 2>&1 ) &
  for t in 3 5 8 10; do sleep 2.5; [ "$(leafz_has neg-$1)" -gt 0 ] && seen=1; done; wait
  tail -n +$((off+1)) $HL | grep -iE "leafnode|tls|auth" | sed -E 's/^\[[0-9]+\] [0-9/]+ [0-9:.]+ //' > $L/neg-$1-hub.log
  echo $seen; }
PA=$(cat $R/nats/pw-home-a)
# 1) raw plaintext CONNECT with valid credentials (a leaf that does not speak TLS)
off=$(wc -l < $HL); PLAIN=$(nsx home-a python3 -I $S/plain-connect.py $HUB 7422 leaf-home-a "$PA" 2>&1); sleep 1
tail -n +$((off+1)) $HL | grep -iE "tls|leafnode" | sed -E 's/^\[[0-9]+\] [0-9/]+ [0-9:.]+ //' > $L/neg-plain-hub.log
PLAIN_REASON=$(head -2 $L/neg-plain-hub.log | tr '\n' ' '); PLAIN_ACCEPTED=$(echo "$PLAIN" | grep -c "PONG"; true)
# 2) a leaf that does not trust the box CA (no tls block, no lab CA in its trust store)
NOCA_CONNECTED=$(neg noca "nats-leaf://leaf-home-a:$PA@$HUB:7422" "" "-u SSL_CERT_FILE")
NOCA_REASON=$(grep -ihE "tls|x509|certificate" $L/neg-noca-leaf.log | head -1 | sed -E 's/^\[[0-9]+\] [0-9/]+ [0-9:.]+ //')
# 3) correct TLS + CA, wrong password
WRONG_CONNECTED=$(neg wrongpw "tls://leaf-home-a:wrong-password-generated-for-test@$HUB:7422" ", tls: { ca_file: \"$R/ca/ca.crt\" }" "")
WRONG_REASON=$(grep -iE "authentication|authorization" $L/neg-wrongpw-hub.log | head -1)
# observation: a leaf with no tls block but that trusts the CA upgrades to TLS by itself
AUTO_TLS=$(neg autotls "nats-leaf://leaf-home-a:$PA@$HUB:7422" "" "")
log "T3-neg listener_on_mesh_ip=$LISTEN_OK other_listeners=$LISTEN_OTHER public_ip_7422=$PUBLIC plaintext: accepted=$PLAIN_ACCEPTED [$PLAIN] hub:[$PLAIN_REASON] | no-CA leaf connected=$NOCA_CONNECTED [$NOCA_REASON] | wrong-password connected=$WRONG_CONNECTED [$WRONG_REASON] | obs: no-tls-block leaf trusting CA auto-upgraded and connected=$AUTO_TLS"
jq -n --argjson l $LISTEN_OK --argjson o $LISTEN_OTHER --arg p "$PUBLIC" --argjson pa $PLAIN_ACCEPTED --arg pr "$PLAIN $PLAIN_REASON" --argjson nc $NOCA_CONNECTED --arg nr "$NOCA_REASON" --argjson wc $WRONG_CONNECTED --arg wr "$WRONG_REASON" --argjson at $AUTO_TLS \
  '{leaf_listener_on_mesh_ip:$l,other_7422_listeners:$o,public_ip_7422:$p,plaintext_connect_accepted:$pa,plaintext_reason:$pr,no_ca_leaf_connected:$nc,no_ca_reason:$nr,wrong_password_leaf_connected:$wc,wrong_password_reason:$wr,obs_leaf_without_tls_block_auto_upgraded_and_connected:$at}' > $R/res/t3-neg.json
for n in home-a home-b; do ( for i in $(seq 1 100); do nsx $n $B/nats -s nats://127.0.0.1:4222 pub --jetstream onemind.node.$n.event.lab.tick "$n:$i" >/dev/null 2>&1 && echo "ack $i" || echo "NOACK $i"; done > $L/pre-$n.log ) & done; wait
for t in $(seq 1 60); do c=$(nsx cloud $B/nats -s $NATS_HUB stream info NODE_EVENTS --json 2>/dev/null | jq -r .state.messages); [ "$c" = 200 ] && break; sleep 1; done
log "T3-pre acks a=$(grep -c ^ack $L/pre-home-a.log) b=$(grep -c ^ack $L/pre-home-b.log) hub NODE_EVENTS=$c after ${t}s"
echo "$c" > $L/pre-hubcount
