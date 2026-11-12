#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Convert an assembled raw image into the VM formats the vm board ships (brief 30 B2 table:
# qcow2, vhdx, vmdk, vdi, ova; HAOS ships all five) and DigitalOcean accepts (raw/qcow2, gzip).
# qemu-img formats: https://www.qemu.org/docs/master/system/images.html
#   convert.sh <image-dir>
set -eu
D=$1
IMG=$(ls "$D"/onemind-*.img | head -n1); BASE=${IMG%.img}
board=$(basename "$D" | sed 's/^image-//')
case "$board" in
  vm-do) FORMATS="qcow2" ;;
  vm)    FORMATS="qcow2 vhdx vmdk vdi" ;;
  *)     FORMATS="" ;;
esac
for f in $FORMATS; do
  opts=""; [ "$f" = vmdk ] && opts="-o subformat=streamOptimized"
  qemu-img convert -p -O "$f" $opts "$IMG" "$BASE.$f"
done
if [ "$board" = vm ]; then
  # Minimal OVF 1.0 package around the streamOptimized VMDK. UNVERIFIED on VirtualBox/VMware
  # import (handbook/findings.md F-09); the vmdk/vdi files are the supported path until then.
  n=$(basename "$BASE"); cap=$(qemu-img info --output=json "$IMG" | python3 -c 'import json,sys;print(json.load(sys.stdin)["virtual-size"])')
  sed -e "s/@NAME@/$n/g" -e "s/@CAPACITY@/$cap/g" "$(dirname "$0")/ova.ovf.in" > "$D/$n.ovf"
  ( cd "$D" && tar -cf "$n.ova" "$n.ovf" "$n.vmdk" && rm -f "$n.ovf" )
fi
if [ -n "$FORMATS" ]; then ( cd "$D" && for f in $FORMATS ova; do ls *."$f" 2>/dev/null; done | xargs -r sha256sum >> SHA256SUMS ); fi
xz -T0 -3 -k -f "$IMG"
( cd "$D" && sha256sum "$(basename "$IMG").xz" >> SHA256SUMS )
ls -la "$D"
