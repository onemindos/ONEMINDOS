#!/bin/bash
# LAB-mender build: Debian 13 amd64 Mender A/B disk image (standalone client,
# grub-mender-grubenv) with k3s and the fresh-signal health gate, plus 7 Mender
# artifacts. Derived from ../../rauc-k3s-gate/scripts/build.sh; the update
# engine is the only intended difference.
# Run as root INSIDE a disposable Debian 13 Lima VM (amd64 is bootstrapped
# through qemu-user binfmt). Never run on the host.
#   sudo OUT=/var/lab/mender-out DL=<verified k3s files> GE=<grub-mender-grubenv@d7c3ec2> ./build.sh
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd); G=$S/guest
W=${W:-/var/lab/mender}          # VM-local work dir
OUT=${OUT:?set OUT}; DL=${DL:?set DL}; GE=${GE:?set GE (grub-mender-grubenv source)}
SUITE=trixie; MIRROR=http://deb.debian.org/debian
MREPO=https://downloads.mender.io/repos/device-components
MKEY_URL=https://downloads.mender.io/repos/debian/gpg
MKEY_FP=E6C857345575F9218396566224072B80A1B29B00   # mender-convert 5.3.0 configs/mender_convert_config L237
MENDER_UPDATE_VER=5.2.0-1+debian+trixie; MENDER_FLASH_VER=1.1.0-1+debian+trixie
COMPAT=onemind-lab-x86_64
IMG_MB=1700
PU_A=6e0a8b0e-0000-4a00-8000-00000000000a
PU_B=6e0a8b0e-0000-4a00-8000-00000000000b
PU_ESP=6e0a8b0e-0000-4a00-8000-0000000000e5
PU_DATA=6e0a8b0e-0000-4a00-8000-0000000000da
log(){ echo "[build $(date -u +%T)] $*"; }
rm -rf "$W"; mkdir -p "$W"/{keys,art,stage} "$OUT"

log "verify k3s artifacts against the release sha256sum file"
( cd "$DL" && grep -E " (k3s|k3s-airgap-images-amd64.tar.zst)\$" sha256sum-amd64.txt | sha256sum -c - )

log "Mender APT key: fetch and check fingerprint (as mender-convert deb.sh L157-L165 does)"
mkdir -p /etc/apt/keyrings
curl -fsSL -o "$W/mender.asc" "$MKEY_URL"
gpg --quiet --show-keys --with-fingerprint --with-colons "$W/mender.asc" | grep -qE "fpr:+$MKEY_FP:" \
  || { echo "ERROR: Mender APT key fingerprint mismatch"; exit 1; }
install -m 644 "$W/mender.asc" /etc/apt/keyrings/mender-lab.asc
echo "Mender key fingerprint $MKEY_FP OK"

# ---------------------------------------------------------- 1. lab signing keys
# Throwaway ECDSA P-256 keys in the VM work dir only; never copied out except the public key.
log "lab artifact keys"; cd "$W/keys"
for k in lab wrong; do
  openssl ecparam -genkey -name prime256v1 -noout -out $k.key.pem 2>/dev/null
  openssl ec -in $k.key.pem -pubout -out $k.pub.pem 2>/dev/null
done

# ---------------------------------------------------------- 2. amd64 rootfs
log "mmdebstrap amd64 $SUITE (+ Mender device-components repo)"
mmdebstrap --mode=root --arch=amd64 --variant=minbase \
  --include=systemd-sysv,udev,dbus,login,linux-image-amd64,initramfs-tools,grub-common,grub-efi-amd64-bin,e2fsprogs,util-linux,procps,kmod,squashfs-tools,iptables,ca-certificates,curl,socat,iproute2,mender-update=$MENDER_UPDATE_VER,mender-flash=$MENDER_FLASH_VER \
  --setup-hook='mkdir -p "$1/etc/apt/keyrings" && cp /etc/apt/keyrings/mender-lab.asc "$1/etc/apt/keyrings/mender-lab.asc"' \
  $SUITE "$W/rootfs" "deb $MIRROR $SUITE main" \
  "deb http://deb.debian.org/debian-security $SUITE-security main" \
  "deb [signed-by=/etc/apt/keyrings/mender-lab.asc] $MREPO debian/$SUITE/stable main" 2>&1 | tail -3
R=$W/rootfs
chroot $R dpkg-query -W -f='${Package} ${Version}\n' mender-update mender-auth mender-flash

log "customise rootfs"
echo onemind-lab > $R/etc/hostname
echo 0123456789abcdef0123456789abcdef > $R/etc/machine-id   # lab-only fixed machine-id (as RAUC spike)
cat > $R/etc/fstab <<'EOF'
PARTLABEL=esp   /boot/efi  vfat  umask=0077  0 1
PARTLABEL=data  /data      ext4  defaults    0 2
EOF
# Read-only slot root; k3s state bind-mounted from /data (same list as LAB-rauc-k3s-gate).
STATE="/etc/rancher/node /var/lib/rancher /var/lib/kubelet /var/lib/cni /var/log/pods /var/log/containers"
for d in $STATE; do
  n=$(echo "${d#/}" | tr / -); mkdir -p "$R$d"
  echo "/data/state/$n  $d  none  bind,x-systemd.requires-mounts-for=/data  0 0" >> $R/etc/fstab
done
mkdir -p $R/boot/efi $R/data $R/usr/lib/onemind/manifests $R/etc/mender/scripts
# Mender: client database on the data partition (mender-convert-modify L200-L202 layout).
rm -rf $R/var/lib/mender; ln -s /data/mender $R/var/lib/mender
install -m 644 "$G/mender.conf" $R/etc/mender/mender.conf
install -m 644 "$W/keys/lab.pub.pem" $R/etc/mender/lab-artifact-verify.pub.pem
# The gate is NOT installed in /etc/mender/scripts: Mender runs Artifact* state scripts
# only from the artifact itself (mender@0f4eb08 src/artifact/v3/scripts/executor.cpp
# L116-L139); see README section 9, item 2. It is embedded in every artifact below.
# Standalone mode: no daemon, no server authentication.
for u in mender-updated.service mender-authd.service; do chroot $R systemctl mask $u >/dev/null 2>&1 || true; done
# grub-mender-grubenv userspace tools (grub-mender-grubenv-print/-set) at d7c3ec2.
make -s -C "$GE" DESTDIR=$R install-tools
KVER=$(ls $R/lib/modules | head -1)
ln -sf vmlinuz-$KVER $R/boot/vmlinuz; ln -sf initrd.img-$KVER $R/boot/initrd.img
echo i6300esb >> $R/etc/initramfs-tools/modules
chroot $R update-initramfs -u -k "$KVER" >/dev/null 2>&1
mkdir -p $R/etc/systemd/system.conf.d
printf '[Manager]\nRuntimeWatchdogSec=30s\n' > $R/etc/systemd/system.conf.d/watchdog.conf
mkdir -p $R/etc/systemd/network
printf '[Match]\nName=en* eth*\n[Network]\nDHCP=ipv4\n' > $R/etc/systemd/network/50-dhcp.network
mkdir -p $R/etc/systemd/system/serial-getty@ttyS0.service.d
cat > $R/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --keep-baud 115200 %I linux
EOF
install -m 755 "$DL/k3s" $R/usr/local/bin/k3s
install -m 644 "$DL/k3s-airgap-images-amd64.tar.zst" $R/usr/lib/onemind/k3s-airgap-images.tar.zst
install -m 755 "$G/onemind-k3s-check" "$G/onemind-health-gate" "$G/onemind-api-respond" $R/usr/lib/onemind/
install -m 644 "$G"/manifests/*.yaml $R/usr/lib/onemind/manifests/
install -m 644 "$G/k3s.service" "$G/onemind-health-gate.service" "$G/onemind-api.service" $R/etc/systemd/system/
: > $R/etc/default/k3s
chroot $R systemctl enable systemd-networkd.service systemd-networkd-wait-online.service \
  k3s.service onemind-api.service onemind-health-gate.service >/dev/null 2>&1
chroot $R passwd -l root >/dev/null
chroot $R systemctl mask systemd-logind.service >/dev/null 2>&1   # as LAB-rauc-k3s-gate §9.5
rm -f $R/etc/apt/sources.list.d/*mender* 2>/dev/null || true
chroot $R dpkg-query -W -f='${Package} ${Version}\n' > "$OUT/image-packages.txt"

# ------------------------------------- 3. GRUB EFI + Mender boot script + env
log "grub-mkstandalone (x86_64-efi) + grub-mender-grubenv standalone boot files"
printf 'insmod part_gpt\ninsmod fat\ninsmod ext2\ninsmod loadenv\ninsmod test\ninsmod linux\ninsmod regexp\nset root=(hd0,gpt1)\nconfigfile /EFI/BOOT/grub.cfg\n' > $R/tmp/embed.cfg
chroot $R grub-mkstandalone -O x86_64-efi -o /tmp/BOOTX64.EFI "boot/grub/grub.cfg=/tmp/embed.cfg"
cp $R/tmp/BOOTX64.EFI "$W/stage/"; rm -f $R/tmp/BOOTX64.EFI $R/tmp/embed.cfg
rm -rf "$W/ge"; cp -a "$GE" "$W/ge"
cat > "$W/ge/mender_grubenv_defines" <<EOF
mender_rootfsa_part=2
mender_rootfsb_part=3
mender_kernel_root_base=/dev/vda
mender_rootfsa_uuid=$PU_A
mender_rootfsb_uuid=$PU_B
kernel_imagetype=vmlinuz
initrd_imagetype=initrd.img
EOF
cp "$G/11_bootargs_grub.cfg" "$G/07_onemind_lab_echo_grub.cfg" "$W/ge/"   # bootargs: as mender-convert grub.sh L55-L60; 07: lab echo only
( cd "$W/ge" && make -s && make -s DESTDIR="$W/stage/esp" BOOT_DIR=/ install-standalone-boot-files ) >/dev/null
find "$W/stage/esp" -type f | sort

# ------------------------------------------------- 4. rootfs image variants
mkimg(){ # $1=name $2=version $3=k3s extra args $4=gate env
  echo "ONEMIND_VERSION=$2" > $R/etc/onemind-release
  echo "artifact_name=onemind-v$2" > $R/etc/mender/artifact_info
  echo "K3S_EXTRA_ARGS=$3" > $R/etc/default/k3s
  printf '%s\n' "$4" > $R/etc/default/onemind-health-gate
  rm -f "$W/stage/$1.ext4"
  mke2fs -q -t ext4 -L rootfs -d $R "$W/stage/$1.ext4" ${IMG_MB}M
}
log "ext4 images (rootfs $(du -sm $R | cut -f1) MiB)"
mkimg v1 1 "" ""
mkimg good 2 "" ""
mkimg bad-k3s 3 "--onemind-lab-unknown-flag" ""
mkimg bad-noagent 4 "--disable-agent" ""
mv $R/sbin/init $R/sbin/init.real
printf '#!/bin/sh\necho "BAD-BOOT: broken init exiting"\nexit 1\n' > $R/sbin/init; chmod 755 $R/sbin/init
mkimg bad-boot 5 "" ""
install -m 755 "$G/bad-hang-init" $R/sbin/init
mkimg bad-hang 6 "" ""
rm -f $R/sbin/init; mv $R/sbin/init.real $R/sbin/init
mkimg naive-noagent 7 "--disable-agent" "ONEMIND_GATE_FRESHNESS=0"
echo "K3S_EXTRA_ARGS=" > $R/etc/default/k3s; : > $R/etc/default/onemind-health-gate

# ------------------------------------------------------------- 5. artifacts
mkart(){ # $1=image $2=version $3=key $4=out
  rm -f "$W/art/$4.mender"
  mender-artifact --compression zstd_fast write rootfs-image --no-progress \
    --compatible-types "$COMPAT" -n "onemind-v$2" --software-version "$2" \
    -s "$G/ArtifactCommit_Enter_00_onemind-gate" \
    -f "$W/stage/$1.ext4" -k "$W/keys/$3.key.pem" -o "$W/art/$4.mender"
}
log "mender artifacts"
mkart good 2 lab good
mkart bad-k3s 3 lab bad-k3s
mkart bad-noagent 4 lab bad-noagent
mkart bad-boot 5 lab bad-boot
mkart bad-hang 6 lab bad-hang
mkart naive-noagent 7 lab naive-noagent
mkart good 2 wrong wrong-key
for a in good bad-k3s bad-noagent bad-boot bad-hang naive-noagent; do
  mender-artifact read -k "$W/keys/lab.pub.pem" "$W/art/$a.mender" 2>&1 | grep -E "^\s*(Name|Signature):|rootfs-image.version|ArtifactCommit_Enter" | tr -s ' ' | sed "s/^/[$a] /"
done
if mender-artifact read -k "$W/keys/lab.pub.pem" "$W/art/wrong-key.mender" 2>&1 | grep -q "signed and verified correctly"; then
  echo "ERROR: wrong-key artifact verified"; exit 1
else echo "[wrong-key] $(mender-artifact read -k "$W/keys/lab.pub.pem" "$W/art/wrong-key.mender" 2>&1 | grep -i -m1 signature | tr -s ' ')"; fi

# ------------------------------------------------------------ 6. disk image
log "disk image"
D=$OUT/disk.img; rm -f "$D"; truncate -s 14G "$D"
sgdisk -Z "$D" >/dev/null
sgdisk -n1:2048:+128M -t1:EF00 -c1:esp -u1:$PU_ESP \
       -n2:0:+2G -t2:8300 -c2:rootfs-A -u2:$PU_A \
       -n3:0:+2G -t3:8300 -c3:rootfs-B -u3:$PU_B \
       -n4:0:0 -t4:8300 -c4:data -u4:$PU_DATA "$D" >/dev/null
start(){ sgdisk -i "$1" "$D" | awk '/First sector/{print $3}'; }
size(){ sgdisk -i "$1" "$D" | awk '/Partition size/{print $3}'; }
rm -f "$W/stage/esp.img"; mkfs.fat -F32 -n ESP -C "$W/stage/esp.img" $(( $(size 1) / 2 )) >/dev/null
mmd -i "$W/stage/esp.img" ::/EFI ::/EFI/BOOT
mcopy -i "$W/stage/esp.img" "$W/stage/BOOTX64.EFI" ::/EFI/BOOT/
mcopy -s -i "$W/stage/esp.img" "$W/stage/esp/EFI/BOOT/grub.cfg" ::/EFI/BOOT/
mcopy -s -i "$W/stage/esp.img" "$W/stage/esp/grub-mender-grubenv" ::/
mdir -/ -i "$W/stage/esp.img" ::/ | grep -vE "^$|Volume|Directory|files|bytes free" | head -20
dd if="$W/stage/esp.img" of="$D" bs=512 seek=$(start 1) conv=notrunc,sparse status=none
dd if="$W/stage/v1.ext4" of="$D" bs=4M oflag=seek_bytes seek=$(( $(start 2) * 512 )) conv=notrunc,sparse status=none
mkdir -p "$W/datafs/artifacts" "$W/datafs/mender" "$W/datafs/onemind"
for d in $STATE; do mkdir -p "$W/datafs/state/$(echo "${d#/}" | tr / -)"; done
cp "$W"/art/*.mender "$W/datafs/artifacts/"
echo "device_type=$COMPAT" > "$W/datafs/mender/device_type"   # as mender-convert-modify writes to /data/mender
rm -f "$W/stage/data.ext4"
mke2fs -q -t ext4 -L data -d "$W/datafs" "$W/stage/data.ext4" $(( $(size 4) / 2 ))k
dd if="$W/stage/data.ext4" of="$D" bs=4M oflag=seek_bytes seek=$(( $(start 4) * 512 )) conv=notrunc,sparse status=none
sgdisk -p "$D" | tail -6

# ---------------------------------------------------------- 7. provenance
cp "$W"/art/*.mender "$OUT/"
cp "$W/stage/esp/EFI/BOOT/grub.cfg" "$OUT/grub.cfg"; cp "$W/keys/lab.pub.pem" "$OUT/lab-artifact-verify.pub.pem"
cp "$W/mender.asc" "$OUT/mender-apt-key.asc"
( cd "$OUT" && sha256sum disk.img *.mender grub.cfg lab-artifact-verify.pub.pem mender-apt-key.asc ) > "$OUT/SHA256SUMS"
ls -la "$OUT"/*.mender | awk '{print $5, $9}'
log "kernel $KVER; done"; cat "$OUT/SHA256SUMS"
