#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Assemble the OneMind USB installer stick image (README.md). Runs as root in the tools container
# (os/rootfs/Containerfile target "tools"), like os/assemble/:
#   build.sh <installer-rootfs.tar> <image-dir> <out-dir>
# <image-dir> is a `make image BOARD=<target_board>` output: the disk .img and its SHA256SUMS.
# Output in <out-dir>: onemind-installer-<arch>-<version>.img (GPT: ESP with GRUB + kernel,
# read-only ext4 root with the compressed image) and SHA256SUMS. No keys are made or used here:
# the payload is the already-signed image, checked against its SHA256SUMS before it is packed.
set -euo pipefail
ROOTFS=$1; IMGDIR=$2; OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
val() { sed -n "s/^$1: *\([^ #]*\).*/\1/p" "$HERE/board.yaml"; }
NAME=$(val name); ARCH=$(val arch); TARGET=$(val target_board); GRUBT=$(val grub_target)
EFI=$(val efi_binary); VOLID=$(val esp_volume_id); CONSOLE=$(sed -n 's/^console: *"\(.*\)"/\1/p' "$HERE/board.yaml")
log() { echo "[installer $(date -u +%T)] $*"; }
W=$(mktemp -d /tmp/installer.XXXXXX); trap 'rm -rf "$W"' EXIT
mkdir -p "$OUT"

log "payload: the $TARGET image, checked against its SHA256SUMS"
IMG=
for f in "$IMGDIR"/onemind-"$TARGET"-*.img; do [ -f "$f" ] && { IMG=$(basename "$f"); break; }; done
[ -n "$IMG" ] || { echo "no onemind-$TARGET-*.img in $IMGDIR" >&2; exit 1; }
VERSION=${IMG#onemind-"$TARGET"-}; VERSION=${VERSION%.img}
( cd "$IMGDIR" && grep "  $IMG\$" SHA256SUMS | sha256sum -c - )
IMG_SHA=$(grep "  $IMG\$" "$IMGDIR/SHA256SUMS" | cut -c1-64)
IMG_SIZE=$(stat -c %s "$IMGDIR/$IMG")

log "tree"
T=$W/tree; mkdir -p "$T"
tar --numeric-owner -xpf "$ROOTFS" -C "$T"
# Files a container build cannot set (bind mounts during RUN): empty machine-id (systemd makes a
# transient one on the read-only root) and no resolv.conf (the stick needs no DNS).
: > "$T/etc/machine-id"; rm -f "$T/etc/resolv.conf"
P=$T/usr/share/onemind-installer/payload; mkdir -p "$P"
zstd -q -T0 -6 "$IMGDIR/$IMG" -o "$P/$IMG.zst"
ZSHA=$(sha256sum "$P/$IMG.zst" | cut -c1-64)
python3 -I - "$P/payload.json" "$TARGET" "$VERSION" "$IMG" "$IMG_SIZE" "$IMG_SHA" "$IMG.zst" "$ZSHA" <<'PY'
import json, sys
out, board, version, image, size, sha, f, fsha = sys.argv[1:]
json.dump({"schema": "onemind.installer-payload/v1", "board": board, "version": version, "image": image,
           "image_size": int(size), "image_sha256": sha, "compression": "zstd", "file": f, "file_sha256": fsha},
          open(out, "w"), indent=1)
PY
cat "$P/payload.json"
printf 'installer=%s target=%s version=%s\n' "$NAME" "$TARGET" "$VERSION" > "$T/usr/share/onemind-installer/build-info.txt"

log "partition UUIDs (fixed per label, like os/assemble/assemble.py)"
pu() { python3 -I -c 'import sys,uuid; print(uuid.uuid5(uuid.UUID("6e0a8b0e-0000-4a00-8000-000000000000"), sys.argv[1]))' "$1"; }
PU_ESP=$(pu onemind-installer-esp); PU_ROOT=$(pu onemind-installer-root)
FSUUID="${VOLID:0:4}-${VOLID:4:4}"

log "GRUB ($GRUBT) from the tree's own GRUB packages"
mkdir -p "$T/tmp/g" "$W/esp/EFI/BOOT"
printf 'insmod part_gpt\ninsmod fat\nsearch --no-floppy --fs-uuid --set=root %s\nconfigfile ($root)/EFI/BOOT/grub.cfg\n' "$FSUUID" > "$T/tmp/g/embed.cfg"
chroot "$T" grub-mkstandalone -O "$GRUBT" -o "/tmp/g/$EFI" "boot/grub/grub.cfg=/tmp/g/embed.cfg"
cp "$T/tmp/g/$EFI" "$W/esp/EFI/BOOT/$EFI"; rm -rf "$T/tmp/g"
cat > "$W/esp/EFI/BOOT/grub.cfg" <<EOF
# SPDX-License-Identifier: Apache-2.0
# OneMind USB installer: boot the live system (read-only root on the stick).
serial --unit=0 --speed=115200
terminal_input console serial
terminal_output console serial
set timeout=3
set default=0
menuentry "Install OneMind $VERSION ($TARGET)" {
  linux (\$root)/vmlinuz root=PARTUUID=$PU_ROOT ro rootwait $CONSOLE systemd.show_status=error
  initrd (\$root)/initrd.img
}
EOF
cp -L "$T/boot/vmlinuz" "$W/esp/vmlinuz"; cp -L "$T/boot/initrd.img" "$W/esp/initrd.img"
cat > "$W/esp/README.txt" <<EOF
OneMind USB installer ($NAME) for OneMind $VERSION ($TARGET).
Boot a computer from this stick, pick the disk to install to, confirm, and it reboots into OneMind.
The disk you pick is erased. Image sha256: $IMG_SHA
EOF

log "filesystems"
ESP_MIB=$(( ( $(du -s -B1M --apparent-size "$W/esp" | cut -f1) + 64 + 31 ) / 32 * 32 ))
mkfs.fat -F 32 -n ONEMIND-USB -i "$VOLID" -C "$W/esp.img" $((ESP_MIB * 1024)) >/dev/null
mcopy -s -i "$W/esp.img" "$W/esp/"* ::/
ROOT_MIB=$(( ( $(du -s -B1M --apparent-size "$T" | cut -f1) * 11 / 10 + 128 + 63 ) / 64 * 64 ))
mke2fs -q -t ext4 -L ONEMIND-INSTALL -E root_owner=0:0 -d "$T" "$W/root.img" "${ROOT_MIB}M"

log "stick image (GPT: ESP ${ESP_MIB} MiB, root ${ROOT_MIB} MiB)"
DISK=$OUT/onemind-installer-$ARCH-$VERSION.img
rm -f "$DISK" "$OUT/SHA256SUMS"
truncate -s $(( (ESP_MIB + ROOT_MIB + 2) << 20 )) "$DISK"
sgdisk -Z "$DISK" >/dev/null
sgdisk -n 1:2048:+"${ESP_MIB}M" -t 1:EF00 -c 1:onemind-installer-esp -u 1:"$PU_ESP" \
       -n 2:0:+"${ROOT_MIB}M" -t 2:8300 -c 2:onemind-installer-root -u 2:"$PU_ROOT" "$DISK" >/dev/null
first() { sgdisk -i "$1" "$DISK" | sed -n 's/^First sector: \([0-9]*\).*/\1/p'; }
dd if="$W/esp.img" of="$DISK" bs=4M seek=$(( $(first 1) * 512 )) oflag=seek_bytes conv=notrunc,sparse status=none
dd if="$W/root.img" of="$DISK" bs=4M seek=$(( $(first 2) * 512 )) oflag=seek_bytes conv=notrunc,sparse status=none
sgdisk -p "$DISK"
( cd "$OUT" && sha256sum "$(basename "$DISK")" > SHA256SUMS && cat SHA256SUMS )
log "done: $DISK (write it to a USB stick with any image writer; it carries $IMG)"
