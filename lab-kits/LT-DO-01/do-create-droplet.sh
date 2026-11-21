#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LT-DO-01 step 4: create the droplet from your uploaded custom image, tagged so the firewall from
# do-firewall.sh applies at creation, with the hub user-data (onemind: role: hub).
#   DIGITALOCEAN_ACCESS_TOKEN=... sh do-create-droplet.sh <image-id> <ssh-key-fingerprint-or-id> [region] [size]
# Refuses to run if the firewall does not exist yet. Add DRY_RUN=1 to only print.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=do-lib.sh
. "$HERE/do-lib.sh"

IMAGE=${1:?usage: do-create-droplet.sh <image-id> <ssh-key-fingerprint-or-id> [region] [size]}
SSHKEY=${2:?missing ssh key fingerprint or id}
REGION=${3:-nyc3}
SIZE=${4:-s-1vcpu-2gb-amd}     # >= 25 GB disk; check the size list in the control panel if rejected
USERDATA=${USERDATA:-$HERE/../../os/cloud/user-data.hub.yaml}

[ -f "$USERDATA" ] || die "user-data file not found: $USERDATA"
grep -Eq '^[[:space:]]+role:[[:space:]]*hub([[:space:]]|$)' "$USERDATA" || die "$USERDATA has no 'role: hub' (the box would never become a hub)"
head -1 "$USERDATA" | grep -q '^#cloud-config' || die "$USERDATA must start with #cloud-config"

[ "${DRY_RUN:-0}" = 1 ] || need_doctl
need_token
if [ "${DRY_RUN:-0}" != 1 ]; then
  doctl compute firewall list --format Name --no-header | grep -qx "$FW_NAME" \
    || die "firewall $FW_NAME not found: run do-firewall.sh first (a droplet must never boot unfirewalled)"
fi

run doctl compute droplet create onemind-lt-do-01 --image "$IMAGE" --region "$REGION" --size "$SIZE" \
  --ssh-keys "$SSHKEY" --user-data-file "$USERDATA" --tag-name "$TAG" --wait
echo "Droplet created with tag $TAG. Verify: doctl compute firewall get <firewall-id>  (status must be succeeded)."
