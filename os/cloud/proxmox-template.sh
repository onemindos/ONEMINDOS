#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Make a Proxmox VE template from onemind-cloud-proxmox-<v>.qcow2 (docs/leap/core/CLOUD-IMAGES.md §3.5).
# Run ON the Proxmox host as root (qm). UEFI (OVMF) without pre-enrolled Secure Boot keys, q35,
# virtio-scsi, a cloud-init drive (NoCloud), serial console (`qm terminal <id>` shows the owner token).
# Needs: Proxmox VE 8 or later (`import-from`), a storage for disks and, for the role, a snippets storage.
#   proxmox-template.sh <image.qcow2> <vmid> [storage] [bridge]
set -eu
. "$(dirname "$0")/lib.sh"
need qm sha256sum
[ $# -ge 2 ] || { sed -n 's/^#   //p' "$0"; exit 2; }
IMG=$(readlink -f "$1"); ID=$2; ST=${3:-local-lvm}; BR=${4:-vmbr0}
verify "$IMG"
N=$(basename "$IMG" .qcow2); V=${N#onemind-cloud-proxmox-}
qm create "$ID" --name "onemind-$(slug "$V")" --ostype l26 --machine q35 --bios ovmf \
  --efidisk0 "$ST:1,efitype=4m,pre-enrolled-keys=0" --cpu host --cores 2 --memory 4096 \
  --scsihw virtio-scsi-single --scsi0 "$ST:0,import-from=$IMG,discard=on" --boot order=scsi0 \
  --net0 "virtio,bridge=$BR" --serial0 socket --vga serial0 --ide2 "$ST:cloudinit" --citype nocloud \
  --ciuser admin --agent 0 --description "OneMind OS $V (cloud-proxmox)"
qm template "$ID"
cat <<HINT
Template $ID. A hub from it (the role comes from a user-data snippet; it replaces Proxmox's generated
user-data, so it carries your SSH key too: see docs/leap/core/CLOUD-IMAGES.md §3.5):
  cp hub.yaml /var/lib/vz/snippets/onemind-hub.yaml       # a storage with content type "snippets"
  qm clone $ID 200 --name onemind-hub --full
  qm set 200 --cicustom user=local:snippets/onemind-hub.yaml --ipconfig0 ip=dhcp
  qm resize 200 scsi0 +24G && qm start 200
Owner token: qm terminal 200   (or ssh admin@<ip> sudo cat /run/onemind/owner-token until the first reboot)
HINT
