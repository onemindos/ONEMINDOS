#!/bin/bash
# LAB-rauc-1152 Pi 5 founder test: build a RAUC + tryboot A/B test disk.
# SPDX-License-Identifier: Apache-2.0
#
# Run as root on a Raspberry Pi 5 booted from a "workbench" SD card with
# Raspberry Pi OS Lite (64-bit, trixie). The TARGET is a second disk (USB SSD,
# NVMe, or an SD card in a USB reader) that is WIPED. The script copies the
# workbench OS into the layout from the Raspberry Pi docs (autoboot.adoc
# "Example update flow for A/B booting"), adds RAUC 1.15.2 (built from the
# pinned tag by build-rauc-pi.sh), k3s and the OneMind health gate, and writes
# 8 test bundles to the target's data partition.
#
#   sudo TARGET=/dev/sda CONFIRM=/dev/sda bash prepare-disk.sh
#
# Optional: SRC_ROOT / SRC_BOOT (default / and /boot/firmware) to copy from a
# mounted image instead of the running system (used for the desk pre-flight),
# DL (k3s download dir), KEYS (lab signing keys, default /root/onemind-lab-keys:
# they stay on the workbench card, never on the target).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); G=$HERE/../guest
TARGET=${TARGET:?set TARGET, e.g. /dev/sda}; [ "${CONFIRM:-}" = "$TARGET" ] || { echo "set CONFIRM=$TARGET to wipe it"; exit 1; }
SRC_ROOT=${SRC_ROOT:-/}; SRC_BOOT=${SRC_BOOT:-/boot/firmware}
DL=${DL:-/root/onemind-dl}; KEYS=${KEYS:-/root/onemind-lab-keys}; RAUC_DEST=${RAUC_DEST:-/root/rauc-1.15.2-dest}
K3S_VER=v1.37.2+k3s1
K3S_SHA=a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b
AIRGAP_SHA=ca384f1a77aa83024bd82ad26fa4774971adb038e656a3b5b9af926be445a442
DISKID=4f4d4c31                       # MBR label-id; root=PARTUUID=$DISKID-05 / -06
COMPAT=onemind-lab-pi5
STATE="/etc/rancher/node /var/lib/rancher /var/lib/kubelet /var/lib/cni /var/log/pods /var/log/containers"
log(){ echo "[prepare $(date -u +%T)] $*"; }
pdev(){ case "$TARGET" in *[0-9]) echo "${TARGET}p$1" ;; *) echo "$TARGET$1" ;; esac; }

# ------------------------------------------------------------------ checks
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
[ -b "$TARGET" ] || { echo "$TARGET is not a block device"; exit 1; }
rootdev=$(findmnt -n -o SOURCE / | sed 's/[0-9]*$//; s/p$//')
[ "$rootdev" != "$TARGET" ] || { echo "$TARGET holds the running system"; exit 1; }
size=$(blockdev --getsize64 "$TARGET"); [ "$size" -ge 60000000000 ] || { echo "target < 60 GB"; exit 1; }
[ -x "$RAUC_DEST/usr/bin/rauc" ] || { echo "run build-rauc-pi.sh first"; exit 1; }
RAUC=$RAUC_DEST/usr/bin/rauc; "$RAUC" --version | grep -qxE 'rauc v?1\.15\.2'
for t in sfdisk mkfs.vfat mke2fs mksquashfs rsync openssl; do command -v $t >/dev/null || { echo "missing $t"; exit 1; }; done
log "k3s $K3S_VER (arm64): download if missing, verify pinned sha256"
mkdir -p "$DL"; u="https://github.com/k3s-io/k3s/releases/download/${K3S_VER/+/%2B}"
[ -f "$DL/k3s-arm64" ] || curl -fsSL -o "$DL/k3s-arm64" "$u/k3s-arm64"
[ -f "$DL/k3s-airgap-images-arm64.tar.zst" ] || curl -fsSL -o "$DL/k3s-airgap-images-arm64.tar.zst" "$u/k3s-airgap-images-arm64.tar.zst"
printf '%s  %s\n%s  %s\n' $K3S_SHA "$DL/k3s-arm64" $AIRGAP_SHA "$DL/k3s-airgap-images-arm64.tar.zst" | sha256sum -c -

# --------------------------------------------------------------- lab keys
if [ ! -f "$KEYS/lab-signer.key.pem" ]; then
  log "lab PKI in $KEYS (throwaway, stays on the workbench)"; mkdir -p "$KEYS"; chmod 700 "$KEYS"
  for ca in lab wrong; do
    openssl req -x509 -newkey rsa:3072 -nodes -days 60 -sha256 -keyout "$KEYS/$ca-ca.key.pem" -out "$KEYS/$ca-ca.cert.pem" -subj "/O=OneMind LAB/CN=$ca-ca" 2>/dev/null
    openssl req -newkey rsa:3072 -nodes -sha256 -keyout "$KEYS/$ca-signer.key.pem" -out "$KEYS/$ca-signer.csr" -subj "/O=OneMind LAB/CN=$ca-signer" 2>/dev/null
    openssl x509 -req -in "$KEYS/$ca-signer.csr" -CA "$KEYS/$ca-ca.cert.pem" -CAkey "$KEYS/$ca-ca.key.pem" -CAcreateserial -days 60 -sha256 \
      -out "$KEYS/$ca-signer.cert.pem" -extfile <(printf 'keyUsage=critical,digitalSignature\n') 2>/dev/null
  done
fi

# --------------------------------------------------------------- partition
log "partition $TARGET (MBR, label-id 0x$DISKID)"
for p in $(lsblk -nlo NAME "$TARGET" | tail -n +2); do umount "/dev/$p" 2>/dev/null || true; done
wipefs -aq "$TARGET"
sfdisk -q "$TARGET" <<EOF
label: dos
label-id: 0x$DISKID
size=64MiB, type=c
size=512MiB, type=c
size=512MiB, type=c
type=5
size=8GiB, type=83
size=8GiB, type=83
type=83
EOF
partprobe "$TARGET" 2>/dev/null || true; udevadm settle
mkfs.vfat -F 32 -n AUTOBOOT "$(pdev 1)" >/dev/null
mke2fs -q -F -t ext4 -L data "$(pdev 7)"
M=$(mktemp -d); mkdir -p "$M/data" "$M/ab"; mount "$(pdev 7)" "$M/data"; mount "$(pdev 1)" "$M/ab"
trap 'umount -R "$M/data/build/root/proc" "$M/data/build/root/sys" "$M/data/build/root/dev" 2>/dev/null; umount "$M/ab" "$M/data" 2>/dev/null' EXIT
W=$M/data/build; T=$W/root; mkdir -p "$W/boot" "$T"

# ------------------------------------------------------------- root tree
log "copy root tree from $SRC_ROOT"
rsync -aHAX --numeric-ids --one-file-system --info=stats1 \
  --exclude=/boot/firmware/'*' --exclude=/data --exclude=/mnt/'*' --exclude=/tmp/'*' --exclude=/var/tmp/'*' \
  --exclude=/root/onemind-lab-keys --exclude=/root/onemind-dl --exclude=/root/rauc-1.15.2-dest --exclude=/root/raucbuild \
  --exclude=/var/cache/apt/archives/'*.deb' --exclude=/proc/'*' --exclude=/sys/'*' --exclude=/dev/'*' --exclude=/run/'*' \
  "$SRC_ROOT"/ "$T"/
log "runtime packages into the tree (chroot apt)"
cp -L /etc/resolv.conf "$W/resolv.conf"; mv "$T/etc/resolv.conf" "$W/resolv.conf.orig" 2>/dev/null || true; cp "$W/resolv.conf" "$T/etc/resolv.conf"
mount -t proc proc "$T/proc"; mount -t sysfs sys "$T/sys"; mount --rbind /dev "$T/dev"
chroot "$T" env DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null
chroot "$T" env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
  socat curl dbus libglib2.0-0t64 libssl3t64 libjson-glib-1.0-0 libcurl4t64 libfdisk1 libnl-genl-3-200 iptables >/dev/null
chroot "$T" sh -c 'dpkg-query -W rauc rauc-service 2>/dev/null' && { echo "ERROR: Debian rauc in tree"; exit 1; } || true
umount -R "$T/proc" "$T/sys" "$T/dev"
rm -f "$T/etc/resolv.conf"; [ -e "$W/resolv.conf.orig" ] || [ -L "$W/resolv.conf.orig" ] && mv "$W/resolv.conf.orig" "$T/etc/resolv.conf" || true

log "RAUC 1.15.2, k3s, gate"
tar -C "$RAUC_DEST" -cf - . | tar -C "$T" -xf -
chroot "$T" /usr/bin/rauc --version
cat > "$T/etc/fstab" <<'EOF'
proc            /proc          proc   defaults            0 0
LABEL=AUTOBOOT  /mnt/autoboot  vfat   defaults,umask=0077 0 2
LABEL=data      /data          ext4   defaults            0 2
EOF
for d in $STATE; do n=$(echo "${d#/}" | tr / -); mkdir -p "$T$d" "$M/data/state/$n"
  echo "/data/state/$n  $d  none  bind,x-systemd.requires-mounts-for=/data  0 0" >> "$T/etc/fstab"; done
mkdir -p "$T/mnt/autoboot" "$T/data" "$T/etc/rauc" "$T/usr/lib/onemind/manifests" "$M/data/rauc" "$M/data/onemind" "$M/data/bundles"
cp "$KEYS/lab-ca.cert.pem" "$T/etc/rauc/keyring.pem"
cat > "$T/etc/rauc/system.conf" <<EOF
[system]
compatible=$COMPAT
bootloader=custom
data-directory=/data/rauc
bundle-formats=verity

[keyring]
path=/etc/rauc/keyring.pem

[handlers]
bootloader-custom-backend=/usr/lib/onemind/rpi-tryboot-ab.sh
pre-install=/usr/lib/onemind/rauc-pre-install

[slot.boot.0]
device=/dev/disk/by-partuuid/$DISKID-02
type=vfat
bootname=A

[slot.rootfs.0]
device=/dev/disk/by-partuuid/$DISKID-05
type=ext4
parent=boot.0

[slot.boot.1]
device=/dev/disk/by-partuuid/$DISKID-03
type=vfat
bootname=B

[slot.rootfs.1]
device=/dev/disk/by-partuuid/$DISKID-06
type=ext4
parent=boot.1
EOF
install -m 755 "$DL/k3s-arm64" "$T/usr/local/bin/k3s"
install -m 644 "$DL/k3s-airgap-images-arm64.tar.zst" "$T/usr/lib/onemind/k3s-airgap-images.tar.zst"
install -m 755 "$HERE/onemind-status" "$T/usr/lib/onemind/"
install -m 755 "$G/onemind-k3s-check" "$G/rauc-pre-install" "$G/onemind-api-respond" "$HERE/onemind-health-gate" "$HERE/rpi-tryboot-ab.sh" "$T/usr/lib/onemind/"
ln -sf /usr/lib/onemind/onemind-status "$T/usr/local/bin/onemind-status"
install -m 644 "$G"/manifests/*.yaml "$T/usr/lib/onemind/manifests/"
install -m 644 "$G/k3s.service" "$G/onemind-api.service" "$HERE/onemind-health-gate.service" "$T/etc/systemd/system/"
mkdir -p "$T/etc/systemd/system.conf.d"; printf '[Manager]\nRuntimeWatchdogSec=10s\n' > "$T/etc/systemd/system.conf.d/watchdog.conf"
for u in k3s.service onemind-api.service onemind-health-gate.service; do ln -sf "/etc/systemd/system/$u" "$T/etc/systemd/system/multi-user.target.wants/$u"; done
for u in apt-daily.timer apt-daily-upgrade.timer; do ln -sf /dev/null "$T/etc/systemd/system/$u"; done   # no surprise upgrades mid-test

# ------------------------------------------------------------- boot tree
log "boot tree from $SRC_BOOT (same files for both slots; cmdline chosen by boot_partition)"
cp -r "$SRC_BOOT"/. "$W/boot/"
base=$(head -n1 "$SRC_BOOT/cmdline.txt" | sed -E 's/(^| )(root|init|rauc\.slot|panic)=[^ ]*//g; s/(^| )(ro|rw|resize|splash)( |$)/ /g; s/(^| )(ro|rw|resize|splash)( |$)/ /g')
for s in A:05:a B:06:b; do IFS=: read -r S N F <<<"$s"
  echo "$base root=PARTUUID=$DISKID-$N rw rauc.slot=$S panic=10 cgroup_memory=1 cgroup_enable=memory" | tr -s ' ' > "$W/boot/cmdline_$F.txt"; done
cat >> "$W/boot/config.txt" <<'EOF'

# --- OneMind LAB-rauc-1152 (tryboot A/B) ---
[all]
usb_max_current_enable=1
[boot_partition=2]
cmdline=cmdline_a.txt
[boot_partition=3]
cmdline=cmdline_b.txt
[all]
EOF
rm -f "$W/boot/cmdline.txt"
rm -f "$W/boot.vfat"; mkfs.vfat -F 32 -n BOOT -C "$W/boot.vfat" $((512 * 1024)) >/dev/null
mkdir -p "$M/bv"; mount -o loop "$W/boot.vfat" "$M/bv"; cp -r "$W/boot"/. "$M/bv/"; umount "$M/bv"

# ---------------------------------------------------------- rootfs images
MB=$(( $(du -sm "$T" | cut -f1) + 1024 )); [ $MB -le 8000 ] || { echo "root tree too big for 8 GiB slots"; exit 1; }
mkimg(){ # $1 name $2 version $3 k3s args $4 gate env
  echo "ONEMIND_VERSION=$2" > "$T/etc/onemind-release"; echo "K3S_EXTRA_ARGS=$3" > "$T/etc/default/k3s"
  printf '%s\n' "$4" > "$T/etc/default/onemind-health-gate"
  rm -f "$W/$1.ext4"; mke2fs -q -t ext4 -L rootfs -d "$T" "$W/$1.ext4" ${MB}M
}
log "rootfs images (${MB} MiB each)"
mkimg v1 1 "" ""; mkimg good 2 "" ""
mkimg bad-k3s 3 "--onemind-lab-unknown-flag" ""; mkimg bad-noagent 4 "--disable-agent" ""
mv "$T/sbin/init" "$T/sbin/init.real"
printf '#!/bin/sh\necho "BAD-BOOT: broken init exiting" > /dev/console\nexit 1\n' > "$T/sbin/init"; chmod 755 "$T/sbin/init"
mkimg bad-boot 5 "" ""
install -m 755 "$HERE/bad-hang-init" "$T/sbin/init"; mkimg bad-hang 6 "" ""
rm -f "$T/sbin/init"; mv "$T/sbin/init.real" "$T/sbin/init"
mkimg naive-noagent 7 "--disable-agent" "ONEMIND_GATE_FRESHNESS=0"
echo "ONEMIND_VERSION=1" > "$T/etc/onemind-release"; echo "K3S_EXTRA_ARGS=" > "$T/etc/default/k3s"; : > "$T/etc/default/onemind-health-gate"

# ---------------------------------------------------------------- bundles
mkbundle(){ # $1 image $2 version $3 key $4 out [$5 format]
  local d="$W/b.d"; rm -rf "$d"; mkdir -p "$d"; cp "$W/$1.ext4" "$d/rootfs.ext4"; cp "$W/boot.vfat" "$d/boot.vfat"
  printf '[update]\ncompatible=%s\nversion=%s\n\n[bundle]\nformat=%s\n\n[image.boot]\nfilename=boot.vfat\n\n[image.rootfs]\nfilename=rootfs.ext4\n' \
    "$COMPAT" "$2" "${5:-verity}" > "$d/manifest.raucm"
  rm -f "$M/data/bundles/$4.raucb"
  "$RAUC" bundle --cert="$KEYS/$3-signer.cert.pem" --key="$KEYS/$3-signer.key.pem" "$d" "$M/data/bundles/$4.raucb" >/dev/null; rm -rf "$d"
}
log "bundles"
mkbundle good 2 lab good; mkbundle bad-k3s 3 lab bad-k3s; mkbundle bad-noagent 4 lab bad-noagent
mkbundle bad-boot 5 lab bad-boot; mkbundle bad-hang 6 lab bad-hang; mkbundle naive-noagent 7 lab naive-noagent
mkbundle good 2 wrong wrong-key; mkbundle good 2 lab plain-good plain
for b in good bad-k3s bad-noagent bad-boot bad-hang naive-noagent plain-good; do
  "$RAUC" info --keyring="$KEYS/lab-ca.cert.pem" "$M/data/bundles/$b.raucb" 2>&1 | grep -E "^Version|Verified|Bundle Format" | sed "s/^/[$b] /"; done
"$RAUC" info --keyring="$KEYS/lab-ca.cert.pem" "$M/data/bundles/wrong-key.raucb" >/dev/null 2>&1 && { echo "ERROR: wrong-key verified"; exit 1; }
echo "[wrong-key] rejected (expected)"

# --------------------------------------------------- initial state: A = v1
log "write slot A (boot p2, root p5) and autoboot.txt"
dd if="$W/boot.vfat" of="$(pdev 2)" bs=4M conv=fsync status=none
dd if="$W/v1.ext4" of="$(pdev 5)" bs=4M conv=fsync status=none
printf '[all]\ntryboot_a_b=1\nboot_partition=2\n[tryboot]\nboot_partition=3\n' > "$M/ab/autoboot.txt"
: > "$M/ab/slot-A.good"
( cd "$M/data/bundles" && sha256sum ./*.raucb ) > "$M/data/bundles/SHA256SUMS"
rm -rf "$W"; sync
sfdisk -l "$TARGET" | tail -8; cat "$M/ab/autoboot.txt"
umount "$M/ab" "$M/data"; rmdir "$M/ab" "$M/data" "$M/bv" "$M" 2>/dev/null || true; trap - EXIT
log "done. Power off, remove the workbench SD card, boot from $TARGET."
