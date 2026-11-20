#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs on the Proxmox host as root (CI-14): the job VMs' own network, `vmbr1`. A bridge with no
# physical port, NATed to the internet through the host's LAN bridge. Blocked: every private range
# (the home LAN, the mesh's 100.64.0.0/10), link-local, the host itself, spoofed source addresses,
# and all IPv6 (the bridge has no IPv6 address and drops IPv6 both ways). So CI code can download
# what it needs but cannot reach the iDRAC, Proxmox, lab VMs or anything else at home. Idempotent:
# rules are added only if missing, so `ifreload` does not stack copies. Allow-list first: a job VM may
# only leave through the uplink (anything else, such as a VPN or another bridge added later, is dropped);
# the private ranges are dropped on top of that. CI_BLOCK_EXTRA (space-separated CIDRs in
# /etc/onemind-ci-kvm.env) adds more, e.g. the router's own public address against hairpin NAT.
#   net.sh            write /etc/network/interfaces.d/onemind-ci and bring vmbr1 up
#   net.sh --check    exit 1 unless every rule is in place (cycle runs it before every clone)
set -eu
BR=${CI_BRIDGE:-vmbr1}
NET=${CI_NET:-10.10.0}            # /24; the host is .1, job VMs .11 and up
UP=${CI_UPLINK:-vmbr0}
f=/etc/network/interfaces.d/onemind-ci
# Refuse to take over a bridge someone else defined (the Proxmox UI offers vmbr1 for the next bridge).
if grep -qsE "^(auto|iface)[[:space:]]+$BR([[:space:]]|$)" /etc/network/interfaces ||
   { ip link show "$BR" >/dev/null 2>&1 && ! grep -qs "OneMind CI job network" "$f"; }; then
  echo "$BR already exists and is not ours; set CI_BRIDGE to a free name in /etc/onemind-ci-kvm.env" >&2; exit 1
fi
rules() {   # one rule per line, without the -A/-D verb
  echo "iptables -t nat POSTROUTING -s $NET.0/24 -o $UP -j MASQUERADE"
  echo "iptables FORWARD -i $BR ! -s $NET.0/24 -j DROP"
  echo "iptables FORWARD -i $BR ! -o $UP -j DROP"
  # shellcheck disable=SC2086
  for d in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16 ${CI_BLOCK_EXTRA:-}; do
    echo "iptables FORWARD -i $BR -d $d -j DROP"
  done
  echo "iptables INPUT -i $BR -j DROP"
  echo "ip6tables FORWARD -i $BR -j DROP"
  echo "ip6tables FORWARD -o $BR -j DROP"
  echo "ip6tables INPUT -i $BR -j DROP"
}
add() { rules | while read -r cmd rest; do
  case $rest in -t\ nat\ *) t="-t nat"; r=${rest#-t nat }; ;; *) t=""; r=$rest;; esac
  chain=${r%% *}; spec=${r#* }
  # shellcheck disable=SC2086
  echo "$cmd $t -C $chain $spec 2>/dev/null || $cmd $t -I $chain 1 $spec"
done; }
del() { rules | while read -r cmd rest; do
  case $rest in -t\ nat\ *) t="-t nat"; r=${rest#-t nat }; ;; *) t=""; r=$rest;; esac
  chain=${r%% *}; spec=${r#* }
  echo "$cmd $t -D $chain $spec 2>/dev/null || true"
done; }
if [ "${1:-}" = --check ]; then
  rules | while read -r cmd rest; do
    case $rest in -t\ nat\ *) t="-t nat"; r=${rest#-t nat }; ;; *) t=""; r=$rest;; esac
    chain=${r%% *}; spec=${r#* }
    # shellcheck disable=SC2086
    $cmd $t -C $chain $spec 2>/dev/null || { echo "missing firewall rule: $cmd $rest" >&2; exit 1; }
  done
  exit 0
fi
{
  echo "# OneMind CI job network (scripts/ci-runner-kvm/net.sh). Internet only (IPv4); no LAN, no host, no IPv6."
  echo "auto $BR"
  echo "iface $BR inet static"
  echo "	address $NET.1/24"
  echo "	bridge-ports none"
  echo "	bridge-stp off"
  echo "	bridge-fd 0"
  echo "	post-up sysctl -qw net.ipv4.ip_forward=1"
  echo "	post-up sysctl -qw net.ipv6.conf.$BR.disable_ipv6=1"
  add | sed 's/^/	post-up /'
  del | sed 's/^/	post-down /'
} > "$f.new"
if ! cmp -s "$f.new" "$f" 2>/dev/null; then
  ifdown "$BR" 2>/dev/null || true
  mv "$f.new" "$f"
  ifup "$BR"
else
  rm -f "$f.new"
  ifup "$BR" 2>/dev/null || true
fi
ip -br addr show "$BR"
