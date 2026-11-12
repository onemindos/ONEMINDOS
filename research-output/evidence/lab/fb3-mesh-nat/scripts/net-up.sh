#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Topology: ns inet = bridge "internet"; cloud = hub (public address, no firewall);
# nat-a / nat-b = home routers (nftables masquerade, drop every new inbound, counted);
# home-a / home-b = home nodes on their own LAN behind those routers.
set -euo pipefail; . "$(dirname "$0")/lib.sh"
for n in home-a home-b nat-a nat-b cloud inet; do ip netns del $n 2>/dev/null || true; done
for n in inet cloud nat-a nat-b home-a home-b; do ip netns add $n; nsx $n ip link set lo up; done
nsx inet ip link add br0 type bridge; nsx inet ip link set br0 up
wan(){ # ns ifname addr delay
  ip link add "t-$1" type veth peer name "i-$1"; ip link set "i-$1" netns inet
  ip link set "t-$1" netns "$1" name "$2"
  nsx inet ip link set "i-$1" master br0 up
  nsx "$1" ip addr add "$3/24" dev "$2"; nsx "$1" ip link set "$2" up
  nsx "$1" tc qdisc add dev "$2" root netem delay "$4"; nsx inet tc qdisc add dev "i-$1" root netem delay "$4"; }
wan cloud eth0 $HUB_PUB 20ms
wan nat-a wan $NATA_WAN 10ms
wan nat-b wan $NATB_WAN 10ms
lan(){ # router home prefix
  ip link add "l-$1" type veth peer name "e-$2"
  ip link set "l-$1" netns "$1" name lan; ip link set "e-$2" netns "$2" name eth0
  nsx "$1" ip addr add "$3.1/24" dev lan; nsx "$1" ip link set lan up
  nsx "$2" ip addr add "$3.10/24" dev eth0; nsx "$2" ip link set eth0 up
  nsx "$2" ip route add default via "$3.1"
  nsx "$1" sysctl -qw net.ipv4.ip_forward=1
  nsx "$1" nft -f - <<NFT
table inet fw {
  counter wan_new_in {}
  counter wan_new_fwd {}
  counter lan_udp_blocked {}
  chain udpblock { }
  chain input { type filter hook input priority 0; policy drop;
    iif lo accept; ct state established,related accept; iifname "lan" accept;
    iifname "wan" ct state new counter name "wan_new_in" drop
  }
  chain forward { type filter hook forward priority 0; policy drop;
    iifname "lan" oifname "wan" meta l4proto udp jump udpblock;
    ct state established,related accept;
    iifname "lan" oifname "wan" accept;
    iifname "wan" counter name "wan_new_fwd" drop
  }
}
table ip nat {
  chain postrouting { type nat hook postrouting priority 100; policy accept;
    oifname "wan" masquerade
  }
}
NFT
}
lan nat-a home-a $LANA
lan nat-b home-b $LANB
# per-namespace hosts file: the hub's name resolves to its public address
for n in cloud home-a home-b; do mkdir -p /etc/netns/$n; printf '127.0.0.1 localhost\n%s %s\n' $HUB_PUB $HUBNAME > /etc/netns/$n/hosts; : > /etc/netns/$n/resolv.conf; done
log "net-up done"; nsx home-a ping -c1 -W2 $HUB_PUB >/dev/null && log "home-a -> hub public OK (outbound through NAT)"
nsx home-b ping -c1 -W2 $HUB_PUB >/dev/null && log "home-b -> hub public OK"
nsx cloud ping -c1 -W2 $LANA.10 >/dev/null 2>&1 && log "UNEXPECTED cloud reaches home-a LAN" || log "cloud cannot route to home LANs (expected)"
