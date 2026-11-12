#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Make a Hetzner Cloud snapshot of onemind-cloud-hetzner-<v>.raw.xz (docs/leap/core/CLOUD-IMAGES.md §3.4).
# Hetzner Cloud takes no image uploads, so: create a temporary server, boot it into the rescue system,
# write the image over its disk, power it off, snapshot it, delete the temporary server.
# The image must be reachable over HTTPS from the server (a CI artifact link, your own bucket).
# Needs: hcloud logged in to YOUR project (HCLOUD_TOKEN or `hcloud context`), an SSH key uploaded to
# the project, and its private half in your ssh-agent. The temporary server is billed while it exists.
#   hetzner-snapshot.sh <https-url-of-.raw.xz> <sha256-of-the-.raw.xz> <hcloud-ssh-key-name> [location] [server-type]
set -eu
. "$(dirname "$0")/lib.sh"
need hcloud ssh
[ $# -ge 3 ] || { sed -n 's/^#   //p' "$0"; exit 2; }
URL=$1; SUM=$2; KEY=$3; LOC=${4:-fsn1}; TYPE=${5:-cx22}     # any x86 type: the snapshot works on larger ones
case "$SUM" in *[!0-9a-f]*|"") echo "sha256 must be 64 lowercase hex" >&2; exit 2 ;; esac
[ ${#SUM} -eq 64 ] || { echo "sha256 must be 64 lowercase hex" >&2; exit 2; }
N=$(basename "$URL" .raw.xz); V=${N#onemind-cloud-hetzner-}
TMP=onemind-imgbuild-$(date +%s)
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o BatchMode=yes"
cleanup() { echo "== deleting temporary server $TMP"; hcloud server delete "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
echo "== temporary server $TMP ($TYPE, $LOC)"
hcloud server create --name "$TMP" --type "$TYPE" --image debian-12 --location "$LOC" --ssh-key "$KEY" >/dev/null
hcloud server enable-rescue --type linux64 --ssh-key "$KEY" "$TMP" >/dev/null
hcloud server reboot "$TMP" >/dev/null
IP=$(hcloud server ip "$TMP")
echo "== waiting for the rescue system on $IP"
i=0; until $SSH "root@$IP" 'hostname | grep -qx rescue'; do          # the rescue system's hostname
  i=$((i + 1)); [ $i -lt 60 ] || { echo "rescue system not reachable" >&2; exit 1; }; sleep 5
done
echo "== writing the image to /dev/sda (download, check sha256, then write)"
$SSH "root@$IP" "set -e; curl -fsSL -o /root/i.raw.xz '$URL'; echo '$SUM  /root/i.raw.xz' | sha256sum -c -; \
  xz -dc /root/i.raw.xz | dd of=/dev/sda bs=4M conv=fsync status=none; sync; rm -f /root/i.raw.xz"
hcloud server poweroff "$TMP" >/dev/null
echo "== snapshot"
hcloud server create-image --type snapshot --description "onemind-cloud-hetzner $V" --label "onemind=$(slug "$V")" "$TMP"
SNAP=$(hcloud image list --type snapshot --selector "onemind=$(slug "$V")" -o noheader -o columns=id | tail -n1)
cat <<HINT
Snapshot $SNAP. Hetzner has no default firewall: attach one that allows 22 (and 8080 only from you).
  hcloud firewall create --name onemind-ssh
  hcloud firewall add-rule onemind-ssh --direction in --protocol tcp --port 22 --source-ips <your-ip>/32
  hcloud server create --name onemind-hub --type cx32 --image $SNAP --ssh-key $KEY \\
    --user-data-from-file hub.yaml --firewall onemind-ssh
Owner token (Hetzner's console is VGA, the token is printed on the serial console):
  ssh admin@<ip> sudo cat /run/onemind/owner-token     (until the first reboot)
HINT
