#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Hub: Headscale (control) + derper (relay, verify-clients) + tailscaled (tag:hub).
# Homes: tailscaled enrolled with single-use tagged pre-auth keys (T1a).
set -euo pipefail; . "$(dirname "$0")/lib.sh"; S=$(dirname "$0")
pkill -f "$B/(headscale|derper|tailscaled|nats-server)" 2>/dev/null || true; pkill socat 2>/dev/null || true; sleep 1
rm -rf $R/ca $R/hs $R/derp $R/cloud $R/home-a $R/home-b $R/home-x; mkdir -p $R/ca $R/hs $R/derp $R/cloud $R/home-a $R/home-b $R/home-x
# throwaway lab CA, generated here, never leaves the VM
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 2 -subj "/CN=fb3 lab CA" -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" -keyout $R/ca/ca.key -out $R/ca/ca.crt 2>/dev/null
cert(){ # name san
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=$1" -keyout $R/ca/$1.key -out $R/ca/$1.csr 2>/dev/null
  openssl x509 -req -in $R/ca/$1.csr -CA $R/ca/ca.crt -CAkey $R/ca/ca.key -CAcreateserial -days 2 -extfile <(printf "subjectAltName=%s\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth" "$2") -out $R/ca/$1.crt 2>/dev/null; }
cert hub "DNS:$HUBNAME,IP:$HUB_PUB"
cp $R/ca/hub.crt $R/derp/$HUBNAME.crt; cp $R/ca/hub.key $R/derp/$HUBNAME.key
cat > $R/hs/derp.yaml <<Y
regions:
  900:
    regionid: 900
    regioncode: onemind-hub
    regionname: OneMind hub DERP (self-hosted)
    nodes:
      - name: 900a
        regionid: 900
        hostname: $HUBNAME
        ipv4: $HUB_PUB
        stunport: 3478
        derpport: 443
Y
python3 $S/gen-policy.py > $R/hs/policy.hujson
cat > $R/hs/config.yaml <<Y
server_url: $HS_URL
listen_addr: $HUB_PUB:8443
metrics_listen_addr: 127.0.0.1:9090
grpc_listen_addr: 127.0.0.1:50443
grpc_allow_insecure: false
noise: { private_key_path: $R/hs/noise_private.key }
prefixes: { v4: 100.64.0.0/10, v6: fd7a:115c:a1e0::/48, allocation: sequential }
derp:
  server: { enabled: false }
  urls: []
  paths: [ $R/hs/derp.yaml ]
  auto_update_enabled: false
disable_check_updates: true
database: { type: sqlite, sqlite: { path: $R/hs/db.sqlite, write_ahead_log: true } }
tls_cert_path: $R/ca/hub.crt
tls_key_path: $R/ca/hub.key
log: { level: info, format: text }
policy: { mode: file, path: $R/hs/policy.hujson }
dns: { magic_dns: false, override_local_dns: false, nameservers: { global: [] } }
unix_socket: $R/hs/headscale.sock
unix_socket_permission: "0770"
logtail: { enabled: false }
Y
hs configtest 2>&1 | tail -2 || true
bg cloud headscale $B/headscale -c $R/hs/config.yaml serve
for i in $(seq 1 30); do nsx cloud curl -fsS --cacert $R/ca/ca.crt $HS_URL/health >/dev/null 2>&1 && break; sleep 1; done
log "headscale health: $(nsx cloud curl -fsS --cacert $R/ca/ca.crt $HS_URL/health)"
hs policy check -f $R/hs/policy.hujson 2>&1 | tail -1
hs users create onemind >/dev/null; UID_=$(hs users list -o json | jq -r '.[]|select(.name=="onemind")|.id')
mint(){ # stand-in for the gateway: one single-use, tagged, 1-hour key per approved node
  hs preauthkeys create --user "$UID_" --tags "tag:$1" --expiration 1h -o json | jq -r .key; }
start_ts(){ # ns tun port
  bg "$1" tailscaled env SSL_CERT_FILE=$SSL_CERT_FILE $B/tailscaled --statedir=$R/$1 --socket=$R/$1/ts.sock --tun="$2" --port="$3" --no-logs-no-support
  for i in $(seq 1 20); do [ -S $R/$1/ts.sock ] && break; sleep 0.5; done; }
up(){ # ns hostname key
  tsc "$1" up --login-server=$HS_URL --authkey="$3" --hostname="$2" --accept-dns=false --netfilter-mode=off --timeout=60s; }
start_ts cloud ts0 41641
K_HUB=$(mint hub); up cloud hub "$K_HUB"; log "hub enrolled: $(tsip cloud)"
bg cloud derper $B/derper -hostname $HUBNAME -certmode manual -certdir $R/derp -a $HUB_PUB:443 -http-port -1 -stun -stun-port 3478 -verify-clients -socket $R/cloud/ts.sock
sleep 2
start_ts home-a ts0 41641; start_ts home-b ts0 41641
K_A=$(mint leaf); K_B=$(mint leaf); echo "$K_A" > $R/home-a/used.key
up home-a home-a "$K_A" && log "home-a enrolled: $(tsip home-a)"
up home-b home-b "$K_B" && log "home-b enrolled: $(tsip home-b)"
# T1a negative: a fourth machine tries home-a's already-used key
bg home-a tsx env SSL_CERT_FILE=$SSL_CERT_FILE $B/tailscaled --statedir=$R/home-x --socket=$R/home-x/ts.sock --tun=userspace-networking --port=0 --no-logs-no-support
for i in $(seq 1 20); do [ -S $R/home-x/ts.sock ] && break; sleep 0.5; done
if timeout 70 ip netns exec home-a $B/tailscale --socket=$R/home-x/ts.sock up --login-server=$HS_URL --authkey="$K_A" --hostname=intruder --accept-dns=false --timeout=60s > $R/t1a-reuse.log 2>&1; then
  log "T1a reuse: ENROLLED (unexpected)"; echo enrolled > $R/t1a-reuse.result
else log "T1a reuse: refused: $(tail -2 $R/t1a-reuse.log | tr '\n' ' ')"; echo refused > $R/t1a-reuse.result; fi
pkill -f "statedir=$R/home-x" || true
hs nodes list -o json > $R/nodes.json
log "nodes: $(jq -c '[.[]|{name:.given_name,online:.online,tags:(.tags // .forced_tags // .valid_tags)}]' $R/nodes.json)"
hs preauthkeys list -o json > $R/preauthkeys.json 2>/dev/null || hs preauthkeys list --user "$UID_" -o json > $R/preauthkeys.json
log "preauthkeys: $(jq -c '[.[]|{used:.used,reusable:.reusable,tags:.acl_tags}]' $R/preauthkeys.json)"
# test services: B allowed 9001 / denied 9002; hub denied 9002
for n in home-b home-a; do
  bg $n svc9001 socat TCP-LISTEN:9001,fork,reuseaddr SYSTEM:"echo allowed-9001-$n"
  bg $n svc9002 socat TCP-LISTEN:9002,fork,reuseaddr SYSTEM:"echo denied-9002-$n"; done
bg cloud svc9002 socat TCP-LISTEN:9002,fork,reuseaddr SYSTEM:"echo denied-9002-hub"
sleep 1; log "mesh-up done"
