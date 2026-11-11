#!/bin/bash
# LAB-minimal-image-dc20: M1 size, M2 SBOM, M3 CVEs for one disk image. Same commands for
# both legs. Run as root INSIDE the Lima VM:  sudo bash measure.sh <label> <disk.img> [cdx.json]
# Needs /opt/syft/syft, /opt/grype/grype and a grype DB already fetched (GRYPE_DB_AUTO_UPDATE=false).
set -euo pipefail
LABEL=$1; IMG=$2; CDX=${3:-}
M=/var/lab/dc20/out/measure/$LABEL; MNT=/mnt/dc20-$LABEL; EMNT=/mnt/dc20-$LABEL-esp
export GRYPE_DB_AUTO_UPDATE=false GRYPE_CHECK_FOR_APP_UPDATE=false SYFT_CHECK_FOR_APP_UPDATE=false
mkdir -p "$M" "$MNT" "$EMNT"
LOOP=$(losetup -P -r -f --show "$IMG"); trap 'umount -q $MNT $EMNT; losetup -d $LOOP' EXIT
lsblk -b -o NAME,SIZE,FSTYPE,PARTTYPENAME,PARTLABEL "$LOOP" > "$M/partitions.txt"
# blkid, not lsblk: udev does not probe loop partitions in this VM.
fstype(){ blkid -o value -s TYPE "$1" 2>/dev/null; }
ROOT=; ESP=
for p in ${LOOP}p*; do case $(fstype $p) in ext4) ROOT=${p#/dev/};; vfat) [ -z "$ESP" ] && ESP=${p#/dev/};; esac; done
mount -o ro /dev/$ROOT "$MNT"; mount -o ro /dev/$ESP "$EMNT"
{
echo "image_apparent_bytes $(stat -c %s "$IMG")"
echo "image_allocated_bytes $(du -B1 "$IMG" | cut -f1)"
echo "esp_content_bytes $(du -sb "$EMNT" | cut -f1)"
echo "rootfs_content_bytes $(du -sb "$MNT" | cut -f1)"
echo "rootfs_content_bytes_no_k3s $(( $(du -sb "$MNT" | cut -f1) - $(stat -c %s "$MNT/usr/local/bin/k3s" 2>/dev/null || echo 0) ))"
echo "rootfs_tar_zstd19_bytes $(tar -C "$MNT" -cf - . | zstd -19 -T0 -q -c | wc -c)"
echo "rootfs_tar_zstd19_bytes_no_k3s $(tar -C "$MNT" --exclude=./usr/local/bin/k3s -cf - . | zstd -19 -T0 -q -c | wc -c)"
echo "rootfs_files $(find "$MNT" -xdev -type f | wc -l)"
} > "$M/size.txt"
# M2: syft on the mounted root filesystem (what any customer scanner would see)
/opt/syft/syft scan "dir:$MNT" -q -o syft-json="$M/syft-rootfs.json" -o cyclonedx-json="$M/syft-rootfs.cdx.json"
/opt/syft/syft scan "dir:$MNT" -q --exclude ./usr/local/bin/k3s -o syft-json="$M/syft-rootfs-nok3s.json"
# M3: grype on each SBOM
for s in syft-rootfs syft-rootfs-nok3s; do
  /opt/grype/grype "sbom:$M/$s.json" -q -o json > "$M/grype-$s.json"
  /opt/grype/grype "sbom:$M/$s.json" -q --only-fixed -o json > "$M/grype-$s-onlyfixed.json"
done
if [ -n "$CDX" ]; then
  cp "$CDX" "$M/buildroot.cdx.json"
  # Target-only SBOM: drop build-host tools (scope "excluded", bom-ref host-*).
  python3 -I -c 'import json,sys;d=json.load(open(sys.argv[1]));d["components"]=[c for c in d["components"] if c.get("scope")!="excluded"];json.dump(d,open(sys.argv[2],"w"))' "$CDX" "$M/buildroot-target.cdx.json"
  for s in buildroot buildroot-target; do
    /opt/grype/grype "sbom:$M/$s.cdx.json" -q -o json > "$M/grype-$s-cdx.json"
    /opt/grype/grype "sbom:$M/$s.cdx.json" -q --only-fixed -o json > "$M/grype-$s-cdx-onlyfixed.json"
  done
fi
cat "$M/size.txt"
