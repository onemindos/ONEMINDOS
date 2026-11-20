#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs on the Proxmox host as root (CI-14): the job VMs' own network, `vmbr1`. A bridge with no
# physical port, NATed to the internet through the host's LAN bridge, with every private range
# (the home LAN, the mesh's 100.64.0.0/10) and the host itself blocked, so CI code can download
# what it needs but cannot reach the iDRAC, Proxmox, lab VMs or anything else at home. Idempotent.
#   net.sh            write /etc/network/interfaces.d/onemind-ci and bring vmbr1 up
set -eu
BR=${CI_BRIDGE:-vmbr1}
NET=${CI_NET:-10.10.0}            # /24; the host is .1, job VMs .11 and up
UP=${CI_UPLINK:-vmbr0}
f=/etc/network/interfaces.d/onemind-ci
rules() {   # $1 = -A (add) or -D (delete); the same list both ways
  echo "iptables -t nat $1 POSTROUTING -s $NET.0/24 -o $UP -j MASQUERADE"
  for d in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16; do
    echo "iptables $1 FORWARD -i $BR -d $d -j DROP"
  done
  echo "iptables $1 INPUT -i $BR -j DROP"
}
{
  echo "# OneMind CI job network (scripts/ci-runner-kvm/net.sh). Internet only; no LAN, no host."
  echo "auto $BR"
  echo "iface $BR inet static"
  echo "	address $NET.1/24"
  echo "	bridge-ports none"
  echo "	bridge-stp off"
  echo "	bridge-fd 0"
  echo "	post-up sysctl -qw net.ipv4.ip_forward=1"
  rules -A | sed 's/^/	post-up /'
  rules -D | sed 's/^/	post-down /'
} > "$f.new"
if ! cmp -s "$f.new" "$f" 2>/dev/null; then
  ifdown "$BR" 2>/dev/null || true
  mv "$f.new" "$f"
  ifup "$BR"
else
  rm -f "$f.new"
fi
ip -br addr show "$BR"
