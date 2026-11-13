#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Turn onemind-cloud-azure-<v>.vhd (or .vhd.xz; a fixed VHD) into an Azure managed image, Hyper-V
# generation 2 (UEFI) (docs/leap/core/CLOUD-IMAGES.md §3.3): upload as a page blob, `az image create`.
# Needs: az logged in to YOUR subscription, a resource group and a storage account in it, and the
# "Storage Blob Data Contributor" role on that account (--auth-mode login). Nothing here runs in CI.
#   azure-import.sh <image.vhd|image.vhd.xz> <resource-group> <storage-account>
set -eu
. "$(dirname "$0")/lib.sh"
need az xz sha256sum
[ $# -ge 3 ] || { sed -n 's/^#   //p' "$0"; exit 2; }
VHD=$(unxz_keep "$1"); RG=$2; SA=$3
verify "$VHD"
N=$(basename "$VHD" .vhd); V=${N#onemind-cloud-azure-}; NAME=onemind-$(slug "$V")
echo "== upload page blob onemind/$N.vhd to $SA"
az storage container create --account-name "$SA" --name onemind --auth-mode login --output none
az storage blob upload --account-name "$SA" --container-name onemind --name "$N.vhd" --file "$VHD" \
  --type page --auth-mode login --overwrite
URL=$(az storage blob url --account-name "$SA" --container-name onemind --name "$N.vhd" --auth-mode login --output tsv)
echo "== image create $NAME"
az image create --resource-group "$RG" --name "$NAME" --os-type Linux --hyper-v-generation V2 --source "$URL" --output none
cat <<HINT
Image $NAME in $RG. The blob can be deleted once VMs are made from the image.
Launch a hub. The image has no Azure Linux agent (cloud-init reports "ready"), the root is read-only
(so the admin user must be the image's "admin" and the login SSH-key only), and GRUB is unsigned:
  az vm create -g $RG -n onemind-hub --image $NAME --size Standard_B2s --security-type Standard \\
    --admin-username admin --authentication-type ssh --ssh-key-values ~/.ssh/id_ed25519.pub \\
    --enable-agent false --custom-data hub.yaml --os-disk-size-gb 40
  az vm boot-diagnostics enable -g $RG -n onemind-hub    # if not on already; the serial log needs it
Owner token: az vm boot-diagnostics get-boot-log -g $RG -n onemind-hub | grep 'ONEMIND OWNER TOKEN'
         or: ssh admin@<ip> sudo cat /run/onemind/owner-token   (until the first reboot)
HINT
