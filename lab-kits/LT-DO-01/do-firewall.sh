#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LT-DO-01 step 3a: create the Cloud Firewall BEFORE any droplet exists. It is bound to a TAG,
# so a droplet created with that tag is firewalled from its first second (see do-create-droplet.sh).
#   DIGITALOCEAN_ACCESS_TOKEN=... sh do-firewall.sh <your-public-ip>      (add DRY_RUN=1 to only print)
# Inbound: TCP 22 and TCP 8080 from <your-public-ip>/32 only. Nothing else. In particular these
# stay closed to the internet: 4222 (NATS), 6443 (k3s API), 10250 (kubelet), 8472/udp (VXLAN).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=do-lib.sh
. "$HERE/do-lib.sh"

MY_IP=${1:?usage: do-firewall.sh <your-public-ip>   (a single IPv4 address, not a range)}
# Single IPv4 only: refuses 0.0.0.0, CIDR ranges, hostnames, IPv6.
echo "$MY_IP" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || die "give one IPv4 address, not '$MY_IP'"
[ "$MY_IP" != "0.0.0.0" ] || die "0.0.0.0 would open the droplet to the whole internet"
for o in $(echo "$MY_IP" | tr . ' '); do [ "$o" -le 255 ] || die "not an IPv4 address: $MY_IP"; done

need_doctl_unless_dry() { [ "${DRY_RUN:-0}" = 1 ] || need_doctl; }
need_doctl_unless_dry
need_token

INBOUND="protocol:tcp,ports:22,address:$MY_IP/32 protocol:tcp,ports:8080,address:$MY_IP/32"
OUTBOUND="protocol:tcp,ports:all,address:0.0.0.0/0 protocol:udp,ports:all,address:0.0.0.0/0 protocol:icmp,address:0.0.0.0/0"

# Defence in depth: the rule list above must never mention a cluster port.
for p in 4222 6443 10250 8472; do
  case "$INBOUND" in *"ports:$p,"*) die "internal error: port $p must stay closed" ;; esac
done

run doctl compute tag create "$TAG"
run doctl compute firewall create --name "$FW_NAME" --tag-names "$TAG" \
  --inbound-rules "$INBOUND" --outbound-rules "$OUTBOUND"
echo "Firewall $FW_NAME is bound to tag $TAG. Next: sh do-create-droplet.sh ..."
