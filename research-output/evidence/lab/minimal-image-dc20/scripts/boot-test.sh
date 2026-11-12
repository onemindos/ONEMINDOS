#!/bin/bash
# LAB-minimal-image-dc20 F1: boot a COPY of a disk image in QEMU x86_64 (TCG, OVMF),
# run the test-only k3s unit, collect the serial log. Root, inside the Lima VM:
#   sudo bash boot-test.sh <label> <disk.img> [kernel-config-file kernel-release]
set -euo pipefail
LABEL=$1; SRC=$2; KCFG=${3:-}; KREL=${4:-}
T=/var/lab/dc20/f1/$LABEL; OUT=/var/lab/dc20/out/f1; F=/var/lab/dc20/f1-payload
mkdir -p "$T" "$OUT"; cp --sparse=always "$SRC" "$T/disk.img"; truncate -s +3G "$T/disk.img"
LOOP=$(losetup -P -f --show "$T/disk.img")
sgdisk -e "$LOOP" >/dev/null
ROOTN=; for p in ${LOOP}p*; do [ "$(blkid -o value -s TYPE $p)" = ext4 ] && ROOTN=${p#/dev/}; done; PN=${ROOTN##*p}
growpart "$LOOP" "$PN" || true; losetup -d "$LOOP"; LOOP=$(losetup -P -f --show "$T/disk.img"); sleep 1
e2fsck -fy /dev/$ROOTN >/dev/null || true; resize2fs /dev/$ROOTN >/dev/null
M=/mnt/f1-$LABEL; mkdir -p $M; mount /dev/$ROOTN $M
install -D -m 0755 $F/dc20-f1.sh $M/usr/local/sbin/dc20-f1.sh
install -D -m 0644 $F/dc20-f1.service $M/etc/systemd/system/dc20-f1.service
mkdir -p $M/etc/systemd/system/multi-user.target.wants
ln -sf /etc/systemd/system/dc20-f1.service $M/etc/systemd/system/multi-user.target.wants/dc20-f1.service
# Test copy only: mask the interactive first-boot wizard (mkosi Debian images run
# systemd-firstboot and wait for console input when locale/timezone/root are unset).
ln -sf /dev/null $M/etc/systemd/system/systemd-firstboot.service
if [ -n "$KCFG" ]; then install -D -m 0644 "$KCFG" "$M/boot/config-$KREL"; fi
df -h $M | tail -1; umount $M; losetup -d "$LOOP"
cp /usr/share/OVMF/OVMF_VARS_4M.fd "$T/vars.fd"
s=$(date +%s)
timeout 2400 qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file="$T/vars.fd" \
  -drive file="$T/disk.img",format=raw,if=virtio \
  -nic user,model=virtio-net-pci -display none -serial file:"$OUT/serial-$LABEL.log" -no-reboot || echo "qemu exit $?"
echo "wall $(( $(date +%s) - s ))s" | tee -a "$OUT/serial-$LABEL.log"
grep -a "DC20-F1" "$OUT/serial-$LABEL.log" || echo "no DC20-F1 markers"
# Read the full result files back from the disk copy.
LOOP=$(losetup -P -f --show "$T/disk.img"); mount -o ro /dev/$(basename $(ls ${LOOP}p* | tail -1)) $M
for f in dc20-f1.out dc20-check-config.txt k3s-f1.log; do cp "$M/var/log/$f" "$OUT/$LABEL-$f" 2>/dev/null || echo "missing $f"; done
umount $M; losetup -d "$LOOP"
cat "$OUT/$LABEL-dc20-f1.out" 2>/dev/null
