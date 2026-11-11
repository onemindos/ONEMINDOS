#!/bin/bash
# LAB-ubuntu-2604-leg build: the LAB-rauc-k3s-gate image and 7 bundles, with an
# Ubuntu 26.04 ("resolute") amd64 root filesystem instead of Debian 13.
# Sections 1 and 3-7 are ../../rauc-k3s-gate/scripts/build.sh unchanged; only
# section 2 (bootstrap + RAUC) differs. The guest files (gate, handler, units,
# manifests, GRUB template) are read from the Debian spike's scripts/guest/ so
# they stay byte-identical (hypothesis HU1).
# Run as root INSIDE a disposable Debian 13 Lima VM (amd64 via qemu-user binfmt).
#   sudo OUT=<out> DL=<k3s files> G=<rauc-k3s-gate/scripts/guest> \
#        RAUC_MODE=src RAUC_SRC=<rauc v1.13 checkout> ./build-ubuntu.sh      # leg U1
#   sudo OUT=<out> DL=<k3s files> G=<...guest> RAUC_MODE=archive ./build-ubuntu.sh  # leg U2
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
G=${G:-$S/../../rauc-k3s-gate/scripts/guest}
W=${W:-/var/lab/u2604}           # VM-local work dir
OUT=${OUT:?set OUT}; DL=${DL:?set DL (k3s, sha256sum-amd64.txt, k3s-airgap-images-amd64.tar.zst)}
RAUC_MODE=${RAUC_MODE:?set RAUC_MODE=src|archive}
SUITE=resolute; MIRROR=http://archive.ubuntu.com/ubuntu
KEYRING=/usr/share/keyrings/ubuntu-archive-keyring.gpg
COMPAT=onemind-lab-x86_64
IMG_MB=1700                      # ext4 image written into each 2 GiB slot
PU_A=6e0a8b0e-0000-4a00-8000-00000000000a
PU_B=6e0a8b0e-0000-4a00-8000-00000000000b
PU_ESP=6e0a8b0e-0000-4a00-8000-0000000000e5
PU_DATA=6e0a8b0e-0000-4a00-8000-0000000000da
log(){ echo "[build $(date -u +%T)] $*"; }
rm -rf "$W"; mkdir -p "$W"/{keys,bundles,stage} "$OUT"

log "verify k3s artifacts against the release sha256sum file"
( cd "$DL" && grep -E " (k3s|k3s-airgap-images-amd64.tar.zst)\$" sha256sum-amd64.txt | sha256sum -c - )

# ---------------------------------------------------------------- 1. lab PKI
log "lab PKI"; cd "$W/keys"
for ca in lab wrong; do
  openssl req -x509 -newkey rsa:3072 -nodes -days 30 -sha256 \
    -keyout $ca-ca.key.pem -out $ca-ca.cert.pem -subj "/O=OneMind LAB/CN=$ca-ca" 2>/dev/null
  openssl req -newkey rsa:3072 -nodes -sha256 -keyout $ca-signer.key.pem \
    -out $ca-signer.csr -subj "/O=OneMind LAB/CN=$ca-signer" 2>/dev/null
  openssl x509 -req -in $ca-signer.csr -CA $ca-ca.cert.pem -CAkey $ca-ca.key.pem \
    -CAcreateserial -days 30 -sha256 -out $ca-signer.cert.pem \
    -extfile <(printf 'keyUsage=critical,digitalSignature\n') 2>/dev/null
done

# ------------------------------------------- 2. amd64 rootfs (UBUNTU 26.04)
# Same package set as the Debian build, with Ubuntu names: linux-image-virtual
# (smallest kernel meta-package for a VM) instead of linux-image-amd64;
# initramfs-tools named explicitly so the boot path matches Debian's.
PKGS=systemd-sysv,udev,dbus,login,linux-image-virtual,initramfs-tools,grub-common,grub-efi-amd64-bin,e2fsprogs,util-linux,procps,kmod,squashfs-tools,iptables,ca-certificates,curl,socat,iproute2
if [ "$RAUC_MODE" = archive ]; then PKGS=$PKGS,rauc,rauc-service; fi
log "mmdebstrap amd64 $SUITE (RAUC_MODE=$RAUC_MODE)"
mmdebstrap --mode=root --arch=amd64 --variant=minbase --keyring="$KEYRING" \
  --include="$PKGS" \
  $SUITE "$W/rootfs" "deb $MIRROR $SUITE main universe" \
  "deb $MIRROR $SUITE-updates main universe" \
  "deb http://security.ubuntu.com/ubuntu $SUITE-security main universe" 2>&1 | tail -3
R=$W/rootfs

if [ "$RAUC_MODE" = src ]; then
  # Leg U1: upstream RAUC v1.13 (the version Debian 13 ships), built in the
  # amd64 chroot. Runtime libraries are kept; build-only packages are purged.
  RAUC_SRC=${RAUC_SRC:?set RAUC_SRC to a v1.13 checkout}
  log "build RAUC from $(cat "$RAUC_SRC/.git/HEAD" 2>/dev/null || echo '?') in the chroot"
  BDEPS="meson ninja-build gcc pkg-config libglib2.0-dev libssl-dev libjson-glib-dev libdbus-1-dev libfdisk-dev libcurl4-openssl-dev libnl-genl-3-dev systemd-dev"
  chroot $R apt-get -q update >/dev/null
  chroot $R env DEBIAN_FRONTEND=noninteractive apt-get -q -y --no-install-recommends install $BDEPS >/dev/null
  rm -rf $R/tmp/rauc-src; mkdir -p $R/tmp/rauc-src; cp -a "$RAUC_SRC"/. $R/tmp/rauc-src/
  chroot $R sh -c 'cd /tmp/rauc-src && meson setup build --prefix=/usr -Dtests=false -Dhtmldocs=false -Dgpt=enabled >/tmp/meson.log 2>&1 && ninja -C build >>/tmp/meson.log 2>&1 && ninja -C build install >>/tmp/meson.log 2>&1' \
    || { tail -40 $R/tmp/meson.log; exit 1; }
  # Keep the packages that own the libraries rauc links against.
  LIBPKGS=$(chroot $R sh -c 'ldd /usr/bin/rauc | awk "/=>/{print \$3}" | xargs -r readlink -f | xargs -r dpkg -S 2>/dev/null | cut -d: -f1 | sort -u' | tr '\n' ' ')
  echo "rauc runtime packages: $LIBPKGS"
  chroot $R apt-mark manual $LIBPKGS >/dev/null
  chroot $R env DEBIAN_FRONTEND=noninteractive apt-get -q -y purge $BDEPS >/dev/null 2>&1 || true
  chroot $R env DEBIAN_FRONTEND=noninteractive apt-get -q -y autoremove --purge >/dev/null
  chroot $R apt-get clean; rm -rf $R/tmp/rauc-src $R/var/lib/apt/lists/*
  chroot $R systemctl enable rauc.service >/dev/null 2>&1 || true
fi
chroot $R rauc --version
chroot $R ldd /usr/bin/rauc | grep -c "not found" && { echo "ERROR: rauc has missing libraries"; exit 1; } || true

log "Ubuntu-specific observations"
{ echo "--- os-release"; grep -E '^(PRETTY_NAME|VERSION_ID|VERSION_CODENAME)=' $R/etc/os-release
  echo "--- kernel"; ls $R/lib/modules
  echo "--- i6300esb module"; find $R/lib/modules -name 'i6300esb*' | sed "s|$R||"
  echo "--- coreutils provider"; chroot $R dpkg-query -W -f='${Package} ${Version}\n' 'coreutils*' 'rust-coreutils*' 2>/dev/null || true
  chroot $R sh -c 'readlink -f /usr/bin/date; date --version | head -1'
  echo "--- initramfs generators installed"; chroot $R dpkg-query -W -f='${Package} ${Version} ${Status}\n' initramfs-tools dracut dracut-core 2>/dev/null || true
  echo "--- kernel package initramfs dependency"; chroot $R sh -c 'apt-cache show linux-image-$(ls /lib/modules | head -1) 2>/dev/null | grep -E "^(Depends|Recommends)" | head -2' || true
  echo "--- snapd / apparmor installed?"; chroot $R dpkg-query -W -f='${Package} ${Version}\n' snapd apparmor 2>/dev/null || echo "(not installed)"
  echo "--- sudo provider"; chroot $R dpkg-query -W -f='${Package} ${Version}\n' 'sudo*' 2>/dev/null || echo "(no sudo)"
} | tee "$OUT/ubuntu-observations.txt"

log "customise rootfs"
echo onemind-lab > $R/etc/hostname
echo 0123456789abcdef0123456789abcdef > $R/etc/machine-id
cat > $R/etc/fstab <<'EOF'
PARTLABEL=esp   /boot/efi  vfat  umask=0077  0 1
PARTLABEL=data  /data      ext4  defaults    0 2
EOF
STATE="/etc/rancher/node /var/lib/rancher /var/lib/kubelet /var/lib/cni /var/log/pods /var/log/containers"
for d in $STATE; do
  n=$(echo "${d#/}" | tr / -); mkdir -p "$R$d"
  echo "/data/state/$n  $d  none  bind,x-systemd.requires-mounts-for=/data  0 0" >> $R/etc/fstab
done
mkdir -p $R/boot/efi $R/data $R/etc/rauc $R/usr/lib/onemind/manifests
cp "$W/keys/lab-ca.cert.pem" $R/etc/rauc/keyring.pem
cat > $R/etc/rauc/system.conf <<EOF
[system]
compatible=$COMPAT
bootloader=grub
grubenv=/boot/efi/EFI/BOOT/grubenv
data-directory=/data/rauc

[keyring]
path=/etc/rauc/keyring.pem

[handlers]
pre-install=/usr/lib/onemind/rauc-pre-install

[slot.rootfs.0]
device=/dev/disk/by-partlabel/rootfs-A
type=ext4
bootname=A

[slot.rootfs.1]
device=/dev/disk/by-partlabel/rootfs-B
type=ext4
bootname=B
EOF
KVER=$(ls $R/lib/modules | head -1)
ln -sf vmlinuz-$KVER $R/boot/vmlinuz; ln -sf initrd.img-$KVER $R/boot/initrd.img
echo i6300esb >> $R/etc/initramfs-tools/modules
chroot $R update-initramfs -u -k "$KVER" >/dev/null 2>&1
lsinitramfs $R/boot/initrd.img-$KVER 2>/dev/null | grep -c i6300esb | sed 's/^/i6300esb in initramfs: /' | tee -a "$OUT/ubuntu-observations.txt"
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
install -m 755 "$G/onemind-k3s-check" "$G/onemind-health-gate" "$G/rauc-pre-install" "$G/onemind-api-respond" $R/usr/lib/onemind/
install -m 644 "$G"/manifests/*.yaml $R/usr/lib/onemind/manifests/
install -m 644 "$G/k3s.service" "$G/onemind-health-gate.service" "$G/onemind-api.service" $R/etc/systemd/system/
: > $R/etc/default/k3s
chroot $R systemctl enable systemd-networkd.service systemd-networkd-wait-online.service \
  k3s.service onemind-api.service onemind-health-gate.service >/dev/null 2>&1
chroot $R passwd -l root >/dev/null
chroot $R systemctl mask systemd-logind.service >/dev/null 2>&1   # same as the Debian build
chroot $R dpkg-query -W -f='${Package} ${Version}\n' > "$OUT/image-packages.txt"

# ---------------------------------------------------- 3. GRUB EFI + grub.cfg
log "grub-mkstandalone (x86_64-efi)"
printf 'insmod part_gpt\ninsmod fat\ninsmod ext2\ninsmod loadenv\ninsmod test\ninsmod linux\nset root=(hd0,gpt1)\nconfigfile /EFI/BOOT/grub.cfg\n' > $R/tmp/embed.cfg
chroot $R grub-mkstandalone -O x86_64-efi -o /tmp/BOOTX64.EFI "boot/grub/grub.cfg=/tmp/embed.cfg"
cp $R/tmp/BOOTX64.EFI "$W/stage/"; rm -f $R/tmp/BOOTX64.EFI $R/tmp/embed.cfg
sed -e "s/@PU_A@/$PU_A/g" -e "s/@PU_B@/$PU_B/g" "$G/grub.cfg.in" > "$W/stage/grub.cfg"
grub-editenv "$W/stage/grubenv" create
grub-editenv "$W/stage/grubenv" set ORDER="A B" A_OK=1 A_TRY=0 B_OK=0 B_TRY=0

# ------------------------------------------------- 4. rootfs image variants
mkimg(){ # $1=name $2=version $3=k3s extra args $4=gate env
  echo "ONEMIND_VERSION=$2" > $R/etc/onemind-release
  echo "K3S_EXTRA_ARGS=$3" > $R/etc/default/k3s
  printf '%s\n' "$4" > $R/etc/default/onemind-health-gate
  rm -f "$W/stage/$1.ext4"
  mke2fs -q -t ext4 -L rootfs -d $R "$W/stage/$1.ext4" ${IMG_MB}M
}
log "ext4 images (rootfs $(du -sm $R | cut -f1) MiB)" | tee -a "$OUT/ubuntu-observations.txt"
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

# ------------------------------------------------------------- 5. bundles
# Signed with the lab VM's RAUC (Debian 1.13), exactly as in the Debian spike.
mkbundle(){ # $1=image $2=version $3=key-prefix $4=out
  local d="$W/bundles/$4.d"; rm -rf "$d"; mkdir -p "$d"
  cp "$W/stage/$1.ext4" "$d/rootfs.ext4"
  printf '[update]\ncompatible=%s\nversion=%s\n\n[bundle]\nformat=verity\n\n[image.rootfs]\nfilename=rootfs.ext4\n' "$COMPAT" "$2" > "$d/manifest.raucm"
  rm -f "$W/bundles/$4.raucb"
  rauc bundle --cert="$W/keys/$3-signer.cert.pem" --key="$W/keys/$3-signer.key.pem" "$d" "$W/bundles/$4.raucb" >/dev/null
  rm -rf "$d"
}
log "rauc bundles"
mkbundle good 2 lab good
mkbundle bad-k3s 3 lab bad-k3s
mkbundle bad-noagent 4 lab bad-noagent
mkbundle bad-boot 5 lab bad-boot
mkbundle bad-hang 6 lab bad-hang
mkbundle naive-noagent 7 lab naive-noagent
mkbundle good 2 wrong wrong-key
for b in good bad-k3s bad-noagent bad-boot bad-hang naive-noagent; do
  rauc info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/$b.raucb" 2>&1 | grep -E "^Version|Verified" | sed "s/^/[$b] /"
done
if rauc info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/wrong-key.raucb" >/dev/null 2>&1; then
  echo "ERROR: wrong-key bundle verified"; exit 1; else echo "[wrong-key] rejected by rauc info (expected)"; fi

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
mcopy -i "$W/stage/esp.img" "$W/stage/BOOTX64.EFI" "$W/stage/grub.cfg" "$W/stage/grubenv" ::/EFI/BOOT/
dd if="$W/stage/esp.img" of="$D" bs=512 seek=$(start 1) conv=notrunc,sparse status=none
dd if="$W/stage/v1.ext4" of="$D" bs=4M oflag=seek_bytes seek=$(( $(start 2) * 512 )) conv=notrunc,sparse status=none
mkdir -p "$W/datafs/bundles" "$W/datafs/rauc" "$W/datafs/onemind"
for d in $STATE; do mkdir -p "$W/datafs/state/$(echo "${d#/}" | tr / -)"; done
cp "$W"/bundles/*.raucb "$W/datafs/bundles/"
rm -f "$W/stage/data.ext4"
mke2fs -q -t ext4 -L data -d "$W/datafs" "$W/stage/data.ext4" $(( $(size 4) / 2 ))k
dd if="$W/stage/data.ext4" of="$D" bs=4M oflag=seek_bytes seek=$(( $(start 4) * 512 )) conv=notrunc,sparse status=none
sgdisk -p "$D" | tail -6

# ---------------------------------------------------------- 7. provenance
cp "$W"/bundles/*.raucb "$OUT/"
cp "$W/stage/grub.cfg" "$OUT/grub.cfg"; cp "$W/keys/lab-ca.cert.pem" "$OUT/"
( cd "$OUT" && sha256sum disk.img *.raucb grub.cfg lab-ca.cert.pem ) > "$OUT/SHA256SUMS"
ls -la "$OUT"/*.raucb | awk '{print $5, $9}'
log "kernel $KVER; done"; cat "$OUT/SHA256SUMS"
