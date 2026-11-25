#!/bin/bash
# Two simulated client networks, each a network namespace with its own veth link to the server and its own
# name resolution. Documentation address ranges (RFC 5737) are used; they are lab-only.
#   nsl = a laptop on the home LAN : canonical name resolves to the server's LAN-side address
#   nsm = a phone away from home   : canonical name resolves to the server's mesh-side address
set -euo pipefail
CANON=${CANON:-idm.onemind.test}; ALIAS=idm.mesh.test; SUBALIAS=mesh.$CANON
mk(){ ns=$1; srv=$2; cli=$3; names=$4
  ip netns add $ns 2>/dev/null || true
  ip link add v-$ns type veth peer name c-$ns 2>/dev/null || true
  ip link set c-$ns netns $ns 2>/dev/null || true
  ip addr add $srv/24 dev v-$ns 2>/dev/null || true; ip link set v-$ns up
  ip -n $ns addr add $cli/24 dev c-$ns 2>/dev/null || true; ip -n $ns link set c-$ns up; ip -n $ns link set lo up
  mkdir -p /etc/netns/$ns; printf "127.0.0.1 localhost\n$srv $names\n" > /etc/netns/$ns/hosts
  printf "# no resolver on purpose: names come only from the hosts file above\n" > /etc/netns/$ns/resolv.conf
}
mk nsl 192.0.2.1 192.0.2.2 "$CANON"
mk nsm 198.51.100.1 198.51.100.2 "$CANON $ALIAS $SUBALIAS"
ip -br addr show | grep -E 'v-ns'; for n in nsl nsm; do echo "== $n"; ip -n $n -br addr; cat /etc/netns/$n/hosts; done
