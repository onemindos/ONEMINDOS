#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Package an assembled cloud-<cloud> disk (onemind-cloud-<cloud>-<v>.img) in the format that cloud
# imports (docs/leap/core/CLOUD-IMAGES.md §1), next to it, and append the sha256 of each to SHA256SUMS:
#   aws      .raw + .raw.xz   EC2 import-snapshot takes RAW (also VMDK/VHD)
#   gcp      .tar.gz          GCE: one member named disk.raw, size a whole number of GiB, oldgnu tar
#   azure    .vhd + .vhd.xz   fixed VHD, virtual size a whole number of MiB (force_size keeps it exact)
#   hetzner  .raw + .raw.xz   written to the server's disk from rescue mode, then snapshotted
#   proxmox  .qcow2           compressed; imported with `qm disk import` / import-from
# The .img is removed afterwards (each format above carries the same bytes).
#   package.sh <cloud> <image-dir>
set -eu
CLOUD=$1; D=$2
IMG=$(ls "$D"/onemind-cloud-"$CLOUD"-*.img | head -n1); BASE=${IMG%.img}; N=$(basename "$BASE")
size=$(stat -c %s "$IMG")
case "$CLOUD" in
  aws|hetzner)
    mv "$IMG" "$BASE.raw"
    xz -T0 -3 -k -f "$BASE.raw"
    outs="$N.raw $N.raw.xz" ;;
  gcp)
    [ $((size % 1073741824)) -eq 0 ] || { echo "ERROR: GCE needs a whole number of GiB ($size)" >&2; exit 1; }
    t=$(mktemp -d "$D/gcp.XXXXXX")
    mv "$IMG" "$t/disk.raw"
    tar --format=oldgnu -S -C "$t" -czf "$BASE.tar.gz" disk.raw
    rm -rf "$t"
    outs="$N.tar.gz" ;;
  azure)
    [ $((size % 1048576)) -eq 0 ] || { echo "ERROR: Azure needs a whole number of MiB ($size)" >&2; exit 1; }
    qemu-img convert -f raw -O vpc -o subformat=fixed,force_size=on "$IMG" "$BASE.vhd"
    rm -f "$IMG"
    xz -T0 -3 -k -f "$BASE.vhd"
    outs="$N.vhd $N.vhd.xz" ;;
  proxmox)
    qemu-img convert -f raw -O qcow2 -c "$IMG" "$BASE.qcow2"
    rm -f "$IMG"
    outs="$N.qcow2" ;;
  *) echo "unknown cloud $CLOUD" >&2; exit 2 ;;
esac
# The assembler listed the .img; list what ships instead.
sed -i "/  $(basename "$IMG")\$/d" "$D/SHA256SUMS"
# shellcheck disable=SC2086 # $outs is a list of file names without spaces
( cd "$D" && sha256sum $outs >> SHA256SUMS )
ls -la "$D"
