# SPDX-License-Identifier: Apache-2.0
# LAB-fb3-mesh-nat shared settings. Addresses are RFC 5737 documentation ranges, used
# only inside the disposable VM's network namespaces (no route to any real network).
B=/opt/fb3/bin; R=/opt/fb3/run; OUT=${OUT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/out}
mkdir -p "$R" "$OUT"
HUB_PUB=203.0.113.10; NATA_WAN=203.0.113.21; NATB_WAN=203.0.113.22
LANA=192.0.2;   LANB=198.51.100
HUBNAME=hub.lab.example; HS_URL=https://$HUBNAME:8443
export SSL_CERT_FILE=$R/ca/ca.crt
ts(){ date -u +%Y-%m-%dT%H:%M:%SZ; }
log(){ echo "$(ts) $*"; }
nsx(){ local n=$1; shift; ip netns exec "$n" "$@"; }
hs(){ nsx cloud $B/headscale -c $R/hs/config.yaml "$@"; }
tsc(){ local n=$1; shift; nsx "$n" $B/tailscale --socket=$R/$n/ts.sock "$@"; }
tsip(){ tsc "$1" ip -4 2>/dev/null | head -1; }
bg(){ local n=$1 name=$2; shift 2; nsx "$n" setsid "$@" >"$R/$n-$name.log" 2>&1 < /dev/null & echo $! > "$R/$n-$name.pid"; }
res(){ # id verdict detail(json object)
  mkdir -p $R/res; jq -n --arg id "$1" --arg v "$2" --argjson d "${3:-{\}}" '{id:$id,verdict:$v,detail:$d}' > $R/res/$1.json; log "RESULT $1 $2"; }
NATS_HUB=nats://127.0.0.1:4222
