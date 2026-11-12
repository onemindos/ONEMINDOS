#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Turn onemind-cloud-gcp-<v>.tar.gz (one member, disk.raw) into a Compute Engine image
# (docs/leap/core/CLOUD-IMAGES.md §3.2): upload to Cloud Storage, `gcloud compute images create`
# with UEFI_COMPATIBLE (the image boots GRUB from its ESP) and GVNIC (the gve driver is in Debian's kernel).
# Needs: gcloud logged in to YOUR project and a bucket. Nothing here runs in CI.
#   gcp-import.sh <image.tar.gz> <gs://bucket> [image-family]
set -eu
. "$(dirname "$0")/lib.sh"
need gcloud sha256sum
[ $# -ge 2 ] || { sed -n 's/^#   //p' "$0"; exit 2; }
TAR=$1; BUCKET=${2%/}; FAMILY=${3:-onemind}
verify "$TAR"
N=$(basename "$TAR" .tar.gz); V=${N#onemind-cloud-gcp-}; NAME=onemind-$(slug "$V")
echo "== upload $BUCKET/$N.tar.gz"
gcloud storage cp "$TAR" "$BUCKET/$N.tar.gz"
echo "== images create $NAME"
gcloud compute images create "$NAME" --source-uri "$BUCKET/$N.tar.gz" --family "$FAMILY" \
  --architecture X86_64 --guest-os-features UEFI_COMPATIBLE,GVNIC,VIRTIO_SCSI_MULTIQUEUE \
  --description "OneMind OS $V (cloud-gcp, UEFI)"
cat <<HINT
Image $NAME. The uploaded object can be deleted: gcloud storage rm $BUCKET/$N.tar.gz
Launch a hub (Shielded VM Secure Boot must stay off: GRUB is unsigned):
  gcloud compute instances create onemind-hub --image $NAME --machine-type e2-medium --boot-disk-size 40GB \\
    --metadata-from-file user-data=hub.yaml --metadata "ssh-keys=admin:\$(cat ~/.ssh/id_ed25519.pub)"
Owner token: gcloud compute instances get-serial-port-output onemind-hub | grep 'ONEMIND OWNER TOKEN'
         or: ssh admin@<ip> sudo cat /run/onemind/owner-token   (until the first reboot)
HINT
