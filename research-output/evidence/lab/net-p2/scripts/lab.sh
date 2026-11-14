#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Lab NET-P2 (README.md): hub + node on two fresh Lima VMs, the owner-approved join, and checks
# NP-1 ... NP-9. Runs on the Mac host; it only drives limactl (creates and deletes its two VMs),
# builds onemindd/onemind with the host's Go, and writes masked results under ../run-N/.
# Nothing is installed on the host. KEEP=1 keeps the VMs for debugging.
#
#   research-output/evidence/lab/net-p2/scripts/lab.sh run-1
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
RUN=${1:-run-1}
OUT="$HERE/$RUN"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/netp2-lab.XXXXXX")
HUB=omos-netp2-hub NODE=omos-netp2-node BOX=box1
mkdir -p "$OUT"
: > "$OUT/results.tsv"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$OUT/lab.log"; }
vm() { limactl shell "$1" -- sudo bash -c "$2" </dev/null; }
# Masking for the committed copy: the virtual LAN, join codes, the owner token.
mask() { sed -E -e 's/192\.168\.104\./192.0.2./g' -e 's/code=[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}/code=XXXX-XXXX-XXXX/g' \
              -e 's/"join_code": "[^"]*"/"join_code": "<redacted>"/g' -e 's/[0-9a-f]{64}/<sha256-or-token>/g'; }
result() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" | tee -a "$OUT/results.tsv"; }
check() { local id=$1 desc=$2; shift 2; if "$@" >>"$OUT/lab.log" 2>&1; then result "$id" PASS "$desc"; else result "$id" FAIL "$desc"; fi; }

cleanup() {
  [ "${KEEP:-0}" = 1 ] && { log "KEEP=1: VMs left running"; return; }
  limactl delete -f "$HUB" "$NODE" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# ---- VMs ----------------------------------------------------------------------------------------
for n in hub node; do
  cpus=2 mem=3GiB; [ $n = hub ] && cpus=4 mem=6GiB
  cat > "$WORK/$n.yaml" <<EOF
base: template://debian-13
vmType: vz
arch: aarch64
cpus: $cpus
memory: $mem
disk: 20GiB
mounts: []
networks:
  - lima: user-v2
containerd: {system: false, user: false}
EOF
  limactl delete -f "omos-netp2-$n" >/dev/null 2>&1 || true
  log "creating omos-netp2-$n"
  limactl start --name="omos-netp2-$n" --tty=false "$WORK/$n.yaml" >"$WORK/$n-start.log" 2>&1
done
HUB_LAN=$(vm $HUB "ip -4 -o addr show eth0 | awk '{print \$4}' | cut -d/ -f1")
log "hub LAN address (masked in results): $(echo "$HUB_LAN" | mask)"

# ---- source -------------------------------------------------------------------------------------
log "building onemindd/onemind for linux/arm64 and copying the tree"
(cd "$REPO" && CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -trimpath -ldflags "-s -w -X github.com/onemindos/onemindos/internal/version.Version=0.1.0+netp2lab" -o "$WORK/onemindd" ./cmd/onemindd \
  && CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -trimpath -ldflags "-s -w" -o "$WORK/onemind-linux-arm64" ./cmd/onemind)
(cd "$REPO" && git ls-files -co --exclude-standard | grep -v -E '^(research|research-output|site|mobile|brand|lab-kits|context)/' \
  | COPYFILE_DISABLE=1 tar --no-xattrs -czf "$WORK/src.tgz" -T -)
for v in $HUB $NODE; do
  limactl copy "$WORK/src.tgz" "$v:/tmp/src.tgz"; limactl copy "$WORK/onemindd" "$v:/tmp/onemindd"
  limactl copy "$WORK/onemind-linux-arm64" "$v:/tmp/onemind-linux-arm64"
  vm "$v" 'rm -rf /opt/src && mkdir -p /opt/src && tar -xzf /tmp/src.tgz -C /opt/src 2>/dev/null && install -m0755 /tmp/onemindd /tmp/onemind-linux-arm64 /opt/src/'
done
vm $HUB 'git -C /opt/src rev-parse HEAD 2>/dev/null || true' >/dev/null
(cd "$REPO" && git rev-parse HEAD) > "$OUT/commit.txt"

# ---- NP-1 hub install ---------------------------------------------------------------------------
log "NP-1: hub install"
set +e
vm $HUB "cd /opt/src && bash deploy/install.sh --role hub --box-name $BOX --lan-addr $HUB_LAN --onemindd-bin /opt/src/onemindd --dashboard-dist /opt/src/core/tests/fixtures/dist" >"$WORK/hub-install.log" 2>&1
rc=$?
set -e
mask <"$WORK/hub-install.log" >"$OUT/hub-install.log"
TOKEN=$(awk '/OWNER TOKEN/{getline; getline; print $1}' "$WORK/hub-install.log")
[ $rc = 0 ] && [ -n "$TOKEN" ] || { result NP-1 FAIL "install.sh --role hub exit $rc"; exit 1; }
vm $HUB "umask 077; printf %s '$TOKEN' > /root/owner-token"
API="curl -fsS -H \"Authorization: Bearer \$(cat /root/owner-token)\" http://127.0.0.1:8080"
vm $HUB "k3s kubectl get nodes -o wide; ip -o link | grep -o 'flannel[^:]*'; ip -d link | grep -c vxlan || true; ss -ltnup | grep -E ':(4222|7422|443|80|8443|8444|6443|3478) '; k3s kubectl get svc -A" | mask >"$OUT/np1-hub.txt"
HUB_MESH=$(vm $HUB "tailscale ip -4")
np1() {
  grep -q " $HUB_MESH " <(vm $HUB "k3s kubectl get nodes -o wide --no-headers") &&
  vm $HUB "ip link show flannel-wg >/dev/null && ! ip -d link | grep -q vxlan" &&
  [ "$(vm $HUB "ss -ltnH 'sport = :4222' | awk '{print \$4}'")" = "127.0.0.1:4222" ] &&
  [ "$(vm $HUB "ss -ltnH 'sport = :7422' | awk '{print \$4}'")" = "$HUB_MESH:7422" ] &&
  vm $NODE "echo | openssl s_client -connect $HUB_LAN:443 -servername $BOX.local 2>/dev/null | grep -q 'issuer=O=OneMind box'" &&
  [ "$(vm $NODE "curl -s -o /dev/null -w '%{http_code}' --resolve $BOX.local:80:$HUB_LAN http://$BOX.local/")" = 308 ] &&
  ! vm $HUB "k3s kubectl -n kube-system get svc traefik" >/dev/null 2>&1
}
check NP-1 "hub: mesh IP $HUB_MESH for k3s, flannel-wg, NATS loopback + mesh leaf listener, box-CA HTTPS, 308 redirect, no Traefik" np1

# ---- NP-2 owner-approved join -------------------------------------------------------------------
log "NP-2: ticket, node request, approval"
vm $HUB "ONEMIND_TOKEN=\$(cat /root/owner-token) onemind fabric ticket --json" >"$WORK/ticket.json"
PAYLOAD=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["qr_payload"])' "$WORK/ticket.json")
CODE=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["one_time"]["join_code"])' "$WORK/ticket.json")
mask <"$WORK/ticket.json" >"$OUT/ticket.json"
(vm $NODE "cd /opt/src && bash deploy/install.sh --role node --join '$PAYLOAD' --hub-addr $HUB_LAN --onemindd-bin /opt/src/onemindd" >"$WORK/node-install.log" 2>&1; echo "exit=$?" >>"$WORK/node-install.log") &
NODE_PID=$!
for _ in $(seq 1 120); do grep -q "Waiting for the owner" "$WORK/node-install.log" 2>/dev/null && break; grep -q '^exit=' "$WORK/node-install.log" 2>/dev/null && break; sleep 5; done
NODE_CODE=$(sed -n 's/^Code *\([0-9A-Z]*-[0-9A-Z]*\).*/\1/p' "$WORK/node-install.log" | head -1)
vm $HUB "$API/v1/fabric" >"$WORK/fabric-pending.json"
read -r HUB_CODE ACTION < <(python3 -I -c 'import json,sys; j=json.load(open(sys.argv[1]))["joining"][0]; print(j["match_code"], j["action_id"])' "$WORK/fabric-pending.json")
PRE_STATE=$(vm $NODE "test -e /etc/onemind/fabric.json && echo has-state || echo no-state")
vm $HUB "ONEMIND_TOKEN=\$(cat /root/owner-token) onemind fabric approve $ACTION" >"$OUT/approve.txt" 2>&1
wait $NODE_PID || true
mask <"$WORK/node-install.log" >"$OUT/node-install.log"
REUSE=$(vm $HUB "curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' http://127.0.0.1:8080/v1/fabric/join-requests -d '{\"join_code\":\"$CODE\",\"node\":{\"node_id\":\"abcdef123456\",\"hostname\":\"x\",\"arch\":\"arm64\"},\"csr_pem\":\"$(printf 'x%.0s' $(seq 1 120))\",\"nats_pubkey\":\"U$(printf 'A%.0s' $(seq 1 55))\"}'")
np2() { [ -n "$NODE_CODE" ] && [ "$NODE_CODE" = "$HUB_CODE" ] && [ "$PRE_STATE" = no-state ] && grep -q '^exit=0' "$WORK/node-install.log" && [ "$REUSE" = 401 ]; }
check NP-2 "match code node=$NODE_CODE hub=$HUB_CODE; no state before approval ($PRE_STATE); node install ok; code reuse -> $REUSE" np2
NODE_ID=$(vm $NODE "python3 -I -c 'import json; print(json.load(open(\"/etc/onemind/fabric.json\"))[\"node_id\"])'")

# ---- NP-3 mesh ----------------------------------------------------------------------------------
NODE_MESH=$(vm $NODE "tailscale ip -4")
vm $HUB "headscale -c /etc/onemind/headscale/config.yaml nodes list -o json" >"$WORK/hs-nodes.json"
mask <"$WORK/hs-nodes.json" | python3 -I -c 'import json,sys; [print(n.get("given_name") or n.get("name"), sorted(n.get("tags") or n.get("forced_tags") or []), n.get("ip_addresses")) for n in json.load(sys.stdin)]' >"$OUT/np3-headscale.txt" 2>&1 || true
np3() {
  python3 -I - "$WORK/hs-nodes.json" "$NODE_ID" <<'EOF'
import json, sys
nodes, nid = json.load(open(sys.argv[1])), sys.argv[2]
n = next(n for n in nodes if (n.get("given_name") or n.get("name")) == f"node-{nid}")
tags = set(n.get("tags") or []) | set(n.get("forced_tags") or [])
assert tags == {"tag:onemind-worker", "tag:onemind-k3s"}, tags
EOF
}
check NP-3 "node-$NODE_ID on the mesh ($NODE_MESH), tags worker + k3s" np3

# ---- NP-4 NATS leaf ------------------------------------------------------------------------------
vm $HUB "curl -s http://127.0.0.1:8222/leafz" | mask >"$OUT/np4-leafz.json"
vm $HUB "cat > /tmp/sub.py <<'EOF'
import socket, sys, time
s = socket.create_connection(('127.0.0.1', 4222)); s.settimeout(1)
s.sendall(b'CONNECT {\"verbose\":false}\r\nSUB onemind.node.*.event.> 1\r\nSUB onemind.audit 2\r\nPING\r\n')
end, buf = time.time() + float(sys.argv[1]), b''
while time.time() < end:
    try: buf += s.recv(65536)
    except socket.timeout: pass
lines, out, i = buf.split(b'\r\n'), [], 0
while i < len(lines):
    if lines[i].startswith(b'MSG '):
        nxt = lines[i + 1] if i + 1 < len(lines) else b''
        out.append(lines[i].split()[1].decode() + ' ' + nxt[:48].decode(errors='replace'))
        i += 2
    else:
        i += 1
print('\n'.join(out))
EOF
nohup python3 /tmp/sub.py 15 >/tmp/sub.out 2>&1 &"
sleep 2
MARK="spoof-$RANDOM$RANDOM"   # the node's forged payload; the gateway's own onemind.audit lines are legitimate
vm $NODE "python3 - <<'EOF'
import socket, time
for _ in range(5):
    s = socket.create_connection(('127.0.0.1', 4222))
    s.sendall(b'CONNECT {\"verbose\":false}\r\nPUB onemind.node.$NODE_ID.event.lab 3\r\nown\r\nPUB onemind.node.000000000000.event.spoof ${#MARK}\r\n$MARK\r\nPUB onemind.audit ${#MARK}\r\n$MARK\r\nPING\r\n')
    s.recv(100); s.close(); time.sleep(1)
EOF"
sleep 12
vm $HUB "sort /tmp/sub.out | sed -E 's/^(onemind.audit) .*/\\1 <a gateway audit line>/' | uniq -c" >"$OUT/np4-hub-received.txt"
echo "forged payload marker: $MARK" >"$OUT/np4-forged-marker.txt"
vm $NODE "python3 - <<'EOF'
import json, socket, ssl
s = socket.create_connection(('$HUB_MESH', 7422), timeout=5)
info = json.loads(s.recv(4096).split(b' ', 1)[1])
ctx = ssl.create_default_context(cafile='/etc/onemind/identity/ca.pem'); ctx.check_hostname = False
try:
    t = ctx.wrap_socket(s, server_hostname='hub.onemind.internal'); t.sendall(b'CONNECT {}\r\n'); t.recv(100); t.recv(100)
    print('tls_required', info.get('tls_required'), 'no-cert leaf: NOT refused')
except (ssl.SSLError, OSError) as e:
    print('tls_required', info.get('tls_required'), 'no-cert leaf refused:', type(e).__name__)
EOF" >"$OUT/np4-nocert.txt" 2>&1 || true
np4() {
  grep -q "\"account\": *\"NODE_$NODE_ID\"" "$OUT/np4-leafz.json" &&
  grep -q "onemind.node.$NODE_ID.event.lab own" "$OUT/np4-hub-received.txt" &&
  ! grep -q "$MARK" "$OUT/np4-hub-received.txt" &&
  grep -q 'no-cert leaf refused' "$OUT/np4-nocert.txt"
}
check NP-4 "leaf in account NODE_$NODE_ID; own subject delivered, other node's and onemind.audit not; no-cert TLS refused" np4

# ---- NP-5 k3s worker ------------------------------------------------------------------------------
for _ in $(seq 1 60); do vm $HUB "k3s kubectl get nodes --no-headers | grep -v control-plane | grep -qw Ready" && break; sleep 5; done
for _ in $(seq 1 24); do [ "$(vm $HUB "$API/v1/actions/$ACTION" | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["state"])')" = succeeded ] && break; sleep 5; done
vm $HUB "k3s kubectl get nodes -o wide; k3s kubectl -n kube-system get secrets --no-headers | grep -c bootstrap-token || true" | mask >"$OUT/np5-k3s.txt"
WORKER=$(vm $HUB "k3s kubectl get nodes --no-headers | grep -v control-plane | awk '{print \$1}'")
HUBNODE=$(vm $HUB "k3s kubectl get nodes --no-headers | grep control-plane | awk '{print \$1}'")
vm $HUB "k3s kubectl run lab-srv --image=docker.io/library/busybox:1.37 --restart=Never --overrides='{\"spec\":{\"nodeName\":\"$HUBNODE\"}}' -- sh -c 'echo cross-node-ok > /tmp/i; httpd -f -p 8000 -h /tmp' >/dev/null
k3s kubectl wait --for=condition=Ready pod/lab-srv --timeout=180s >/dev/null" || true
SRV_IP=$(vm $HUB "k3s kubectl get pod lab-srv -o jsonpath='{.status.podIP}'")
vm $HUB "k3s kubectl run lab-cli --image=docker.io/library/busybox:1.37 --restart=Never --overrides='{\"spec\":{\"nodeName\":\"$WORKER\"}}' -- wget -qO- -T 10 http://$SRV_IP:8000/i >/dev/null
for i in \$(seq 1 60); do k3s kubectl get pod lab-cli -o jsonpath='{.status.phase}' | grep -qE 'Succeeded|Failed' && break; sleep 3; done
k3s kubectl logs lab-cli" >"$OUT/np5-cross-node.txt" 2>&1 || true
np5() {
  vm $HUB "k3s kubectl get nodes -o wide --no-headers" | grep -v control-plane | grep -q " Ready .* $NODE_MESH " &&
  [ "$(vm $HUB "$API/v1/actions/$ACTION" | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["state"])')" = succeeded ] &&
  [ "$(tail -1 "$OUT/np5-k3s.txt")" = 0 ] && grep -q cross-node-ok "$OUT/np5-cross-node.txt"
}
check NP-5 "worker Ready on mesh IP; node.join succeeded; bootstrap token removed; pod on worker -> pod on hub" np5

# ---- NP-6 app through the proxy ----------------------------------------------------------------
EXP=$(date -u -v+10M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+10 min' +%Y-%m-%dT%H:%M:%SZ)
AID=$(vm $HUB "$API/v1/actions -H 'Content-Type: application/json' -d '{\"type\":\"app.install\",\"params\":{\"app_id\":\"vaultwarden\"},\"idempotency_key\":\"lab-vw\",\"expires_at\":\"$EXP\"}'" | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["id"])')
vm $HUB "$API/v1/actions/$AID/approve -X POST" | python3 -I -c 'import json,sys; a=json.load(sys.stdin); print(a["state"], (a.get("result") or {}).get("message"))' >"$OUT/np6-install.txt"
vm $HUB "for i in \$(seq 1 60); do k3s kubectl -n app-vaultwarden get pods --no-headers 2>/dev/null | grep -q '1/1 *Running' && break; sleep 5; done"
R="--resolve vaultwarden.$BOX.local:443:$HUB_LAN --resolve $BOX.local:443:$HUB_LAN"
vm $NODE "CA=/etc/onemind/identity/ca.pem; T=\$(cat /dev/null)
echo nosignin \$(curl -s $R --cacert \$CA -o /dev/null -w '%{http_code}' https://vaultwarden.$BOX.local/)
echo bearer \$(curl -s $R --cacert \$CA -H 'Authorization: Bearer $TOKEN' -o /dev/null -w '%{http_code}' https://vaultwarden.$BOX.local/)
echo cookie-set \$(curl -s $R --cacert \$CA -c /tmp/jar -X POST -H 'Authorization: Bearer $TOKEN' -o /dev/null -w '%{http_code}' https://$BOX.local/v1/auth/app-session)
echo cookie \$(curl -s $R --cacert \$CA -b /tmp/jar -o /dev/null -w '%{http_code}' https://vaultwarden.$BOX.local/alive)
echo noca \$(curl -s $R -o /dev/null -w '%{http_code}' https://vaultwarden.$BOX.local/ || true)" >"$OUT/np6-app.txt" 2>&1
np6() { grep -qx 'nosignin 401' "$OUT/np6-app.txt" && grep -qx 'bearer 200' "$OUT/np6-app.txt" && grep -qx 'cookie 200' "$OUT/np6-app.txt" && grep -qx 'noca 000' "$OUT/np6-app.txt"; }
check NP-6 "https://vaultwarden.$BOX.local via the gateway proxy: 401 signed out, 200 bearer, 200 cookie, TLS fails without the box CA" np6

# ---- NP-7 mesh access rules ----------------------------------------------------------------------
vm $NODE "for p in 443 7422 6443 22 8444 4222; do timeout 4 bash -c \"exec 3<>/dev/tcp/$HUB_MESH/\$p\" 2>/dev/null && echo \"\$p open\" || echo \"\$p closed\"; done" >"$OUT/np7-ports.txt"
np7() { for p in 443 7422 6443; do grep -qx "$p open" "$OUT/np7-ports.txt" || return 1; done; for p in 22 8444 4222; do grep -qx "$p closed" "$OUT/np7-ports.txt" || return 1; done; }
check NP-7 "worker -> hub mesh: 443/7422/6443 open, 22/8444/4222 closed" np7

# ---- NP-8 leaf liveness ---------------------------------------------------------------------------
vm $NODE "iptables -I OUTPUT -d $HUB_MESH -p tcp --dport 7422 -j DROP; iptables -I INPUT -s $HUB_MESH -p tcp --sport 7422 -j DROP"
T0=$(date +%s); DOWN=""
for _ in $(seq 1 60); do
  n=$(vm $HUB "curl -s http://127.0.0.1:8222/leafz" | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["leafnodes"])')
  [ "$n" = 0 ] && { DOWN=$(( $(date +%s) - T0 )); break; }; sleep 3
done
vm $NODE "iptables -D OUTPUT -d $HUB_MESH -p tcp --dport 7422 -j DROP; iptables -D INPUT -s $HUB_MESH -p tcp --sport 7422 -j DROP"
echo "hub saw the leaf gone after ${DOWN:-never (>180)} s" >"$OUT/np8-liveness.txt"
check NP-8 "dead leaf link noticed by the hub after ${DOWN:-never} s (limit 90)" test -n "$DOWN" -a "${DOWN:-999}" -le 90

# ---- NP-9 names (informative) -----------------------------------------------------------------------
{ vm $HUB "for n in $BOX.local onemind.local vaultwarden.$BOX.local vaultwarden.onemind.local; do avahi-resolve -4 -n \$n || true; done"
  echo "--- from the node over the Lima switch:"; vm $NODE "getent hosts $BOX.local vaultwarden.$BOX.local || echo 'no mDNS answer (user-v2 forwards no multicast)'"; } 2>&1 | mask >"$OUT/np9-names.txt" || true
result NP-9 INFO "hub resolves its published names; cross-VM: $(tail -1 "$OUT/np9-names.txt" | mask)"

# ---- summary ----------------------------------------------------------------------------------------
vm $HUB "journalctl -u onemind-gateway -u onemind-nats -u onemind-headscale --no-pager | tail -200" | mask >"$OUT/hub-journal-tail.txt" || true
mask <"$OUT/lab.log" >"$OUT/lab.log.masked" && mv "$OUT/lab.log.masked" "$OUT/lab.log"
fails=$(awk -F'\t' '$2=="FAIL"' "$OUT/results.tsv" | wc -l | tr -d ' ')
verdict=PASS; [ "$fails" = 0 ] || verdict=FAIL
python3 -I - "$OUT/results.tsv" "$verdict" >"$OUT/results.json" <<'EOF'
import json, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1]) if l.strip()]
print(json.dumps({"lab": "net-p2", "verdict": sys.argv[2], "tests": [{"id": r[0], "result": r[1], "detail": r[2]} for r in rows]}, indent=2))
EOF
(cd "$OUT" && shasum -a 256 ./* | grep -v SHA256SUMS > SHA256SUMS)
log "verdict: $verdict"
