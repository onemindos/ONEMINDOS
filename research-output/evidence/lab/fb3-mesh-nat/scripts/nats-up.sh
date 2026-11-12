#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# NATS hub (cloud) with its leaf port bound ONLY to the hub's mesh address, TLS required,
# one user per node with a random password generated now (never committed).
# Each home node: a local leaf (JetStream domain node-<id>, stream ONEMIND_NODE_OUTBOX).
set -euo pipefail; . "$(dirname "$0")/lib.sh"; S=$(dirname "$0")
pkill -f "$B/nats-server" 2>/dev/null || true; sleep 1
HUB_TS=$(tsip cloud); mkdir -p $R/nats; rm -rf $R/nats/*
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=nats-hub" -keyout $R/ca/natshub.key -out $R/ca/natshub.csr 2>/dev/null
openssl x509 -req -in $R/ca/natshub.csr -CA $R/ca/ca.crt -CAkey $R/ca/ca.key -CAcreateserial -days 2 -extfile <(printf "subjectAltName=IP:%s,DNS:%s\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth" $HUB_TS $HUBNAME) -out $R/ca/natshub.crt 2>/dev/null
PA=$(openssl rand -hex 16); PB=$(openssl rand -hex 16); echo "$PA" > $R/nats/pw-home-a; echo "$PB" > $R/nats/pw-home-b; chmod 600 $R/nats/pw-*
cat > $R/nats/hub.conf <<C
server_name: hub
listen: 127.0.0.1:4222
http: 127.0.0.1:8222
jetstream { store_dir: "$R/nats/hubstore", domain: hub }
leafnodes {
  listen: "$HUB_TS:7422"
  tls { cert_file: "$R/ca/natshub.crt", key_file: "$R/ca/natshub.key", timeout: 5 }
  authorization { users: [
    { user: "leaf-home-a", password: "$PA" }
    { user: "leaf-home-b", password: "$PB" }
  ] }
}
C
bg cloud natshub $B/nats-server -c $R/nats/hub.conf
leafconf(){ # node user pw tlsblock urlscheme
cat <<C
server_name: leaf-$1
listen: 127.0.0.1:${6:-4222}
jetstream { store_dir: "$R/nats/$1-store", domain: node-$1 }
leafnodes { remotes: [ { url: "$5://$2:$3@$HUB_TS:7422", $4 } ] }
C
}
for n in home-a home-b; do
  PW=$(cat $R/nats/pw-$n); leafconf $n leaf-$n "$PW" "tls: { ca_file: \"$R/ca/ca.crt\" }" tls > $R/nats/$n.conf
  bg $n natsleaf $B/nats-server -c $R/nats/$n.conf; done
sleep 4
nsx cloud ss -ltnp | grep 7422 | sed 's/users:.*//' > $R/nats/ss-7422.txt; log "hub leaf listener: $(cat $R/nats/ss-7422.txt | tr -s ' ')"
for n in home-a home-b; do
  nsx $n $B/nats -s nats://127.0.0.1:4222 stream add ONEMIND_NODE_OUTBOX --subjects "onemind.node.$n.event.>" --storage file --replicas 1 --retention limits --discard old --max-msgs=-1 --max-bytes=256MiB --max-age=7d --max-msg-size=-1 --dupe-window 2m --no-allow-rollup --no-deny-delete --no-deny-purge --defaults >/dev/null && log "$n ONEMIND_NODE_OUTBOX created"; done
cat > $R/nats/node_events.json <<J
{"name":"NODE_EVENTS","retention":"limits","storage":"file","num_replicas":1,"discard":"old",
 "sources":[{"name":"ONEMIND_NODE_OUTBOX","external":{"api":"\$JS.node-home-a.API","deliver":""}},
            {"name":"ONEMIND_NODE_OUTBOX","external":{"api":"\$JS.node-home-b.API","deliver":""}}]}
J
nsx cloud $B/nats -s $NATS_HUB stream add --config $R/nats/node_events.json >/dev/null && log "hub NODE_EVENTS created"
nsx cloud curl -s 127.0.0.1:8222/leafz | jq -c '[.leafs[]|{name,account,ip,port}]' | sed -E 's/"ip":"[^"]*"/"ip":"<mesh>"/g' > $R/nats/leafz.txt; log "leafz: $(cat $R/nats/leafz.txt)"
