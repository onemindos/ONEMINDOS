#!/bin/bash
# LAB-rauc-1152 build: Debian 13 amd64 RAUC A/B disk image with k3s and the
# fresh-signal health gate, plus 8 bundles, using RAUC 1.15.2 built from the
# pinned upstream tag by build-rauc.sh (not Debian's 1.13 package), and a
# verity-only bundle policy. Derived from ../../rauc-k3s-gate/scripts/build.sh.
# Run as root INSIDE a disposable Debian 13 Lima VM (amd64 is bootstrapped
# through qemu-user binfmt). Never run on the host.
#   sudo OUT=/var/lab/r1152-out DL=<dir with verified k3s files> ./build.sh
# Needs build-rauc.sh to have run with the same OUT (rauc-arm64, rauc-amd64-dest.tar).
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd); G=$S/guest
W=${W:-/var/lab/r1152}             # VM-local work dir
OUT=${OUT:?set OUT}; DL=${DL:?set DL (k3s, sha256sum-amd64.txt, k3s-airgap-images-amd64.tar.zst)}
SUITE=trixie; MIRROR=http://deb.debian.org/debian
COMPAT=onemind-lab-x86_64
IMG_MB=1700                      # ext4 image written into each 2 GiB slot
PU_A=6e0a8b0e-0000-4a00-8000-00000000000a
PU_B=6e0a8b0e-0000-4a00-8000-00000000000b
PU_ESP=6e0a8b0e-0000-4a00-8000-0000000000e5
PU_DATA=6e0a8b0e-0000-4a00-8000-0000000000da
log(){ echo "[build $(date -u +%T)] $*"; }
RAUC=$OUT/rauc-arm64            # upstream 1.15.2, used for every bundle operation here
"$RAUC" --version | grep -qxE 'rauc v?1\.15\.2' || { echo "ERROR: need rauc 1.15.2 from build-rauc.sh"; exit 1; }
rm -rf "$W"; mkdir -p "$W"/{keys,bundles,stage} "$OUT"

log "verify k3s artifacts against the release sha256sum file"
( cd "$DL" && grep -E " (k3s|k3s-airgap-images-amd64.tar.zst)\$" sha256sum-amd64.txt | sha256sum -c - )

# ---------------------------------------------------------------- 1. lab PKI
# Throwaway keys in the VM work dir only; never copied out, never committed.
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

# ---------------------------------------------------------- 2. amd64 rootfs
log "mmdebstrap amd64 $SUITE"
mmdebstrap --mode=root --arch=amd64 --variant=minbase \
  --include=systemd-sysv,udev,dbus,login,linux-image-amd64,initramfs-tools,$(paste -sd, $OUT/rauc-amd64-runtime-pkgs.txt),grub-common,grub-efi-amd64-bin,e2fsprogs,util-linux,procps,kmod,squashfs-tools,iptables,ca-certificates,curl,socat,iproute2 \
  $SUITE "$W/rootfs" "deb $MIRROR $SUITE main" \
  "deb http://deb.debian.org/debian-security $SUITE-security main" 2>&1 | tail -3
R=$W/rootfs
# Upstream RAUC 1.15.2 (amd64) with its D-Bus service, policy and systemd unit.
tar -C $R -xf "$OUT/rauc-amd64-dest.tar"
if chroot $R ldd /usr/bin/rauc | grep 'not found'; then echo "ERROR: missing RAUC runtime library"; exit 1; fi
chroot $R /usr/bin/rauc --version
if chroot $R dpkg-query -W rauc rauc-service >/dev/null 2>&1; then echo "ERROR: Debian rauc package present"; exit 1; fi
echo "Debian rauc package: not installed (expected)"

log "customise rootfs"
echo onemind-lab > $R/etc/hostname
# Lab-only fixed machine-id (same in every slot). A product should keep it on
# the data partition or in grubenv, as HAOS does with MACHINE_ID.
echo 0123456789abcdef0123456789abcdef > $R/etc/machine-id
cat > $R/etc/fstab <<'EOF'
PARTLABEL=esp   /boot/efi  vfat  umask=0077  0 1
PARTLABEL=data  /data      ext4  defaults    0 2
EOF
# The slot root is mounted read-only (no "rw" on the kernel command line).
# k3s writes outside --data-dir by default, so its writable state is
# bind-mounted from the data partition; the kubeconfig goes to /run (per boot).
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
bundle-formats=verity

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
# Watchdog: load the (QEMU i6300esb) driver in the initramfs; systemd pets it.
echo i6300esb >> $R/etc/initramfs-tools/modules
chroot $R update-initramfs -u -k "$KVER" >/dev/null 2>&1
mkdir -p $R/etc/systemd/system.conf.d
printf '[Manager]\nRuntimeWatchdogSec=30s\n' > $R/etc/systemd/system.conf.d/watchdog.conf
# Network: k3s needs an interface with a default route (QEMU user net, restrict=on).
mkdir -p $R/etc/systemd/network
printf '[Match]\nName=en* eth*\n[Network]\nDHCP=ipv4\n' > $R/etc/systemd/network/50-dhcp.network
# Serial autologin (lab only: disposable guest, no route out).
mkdir -p $R/etc/systemd/system/serial-getty@ttyS0.service.d
cat > $R/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --keep-baud 115200 %I linux
EOF
# k3s + air-gap images (verified above) + OneMind gate files.
install -m 755 "$DL/k3s" $R/usr/local/bin/k3s
install -m 644 "$DL/k3s-airgap-images-amd64.tar.zst" $R/usr/lib/onemind/k3s-airgap-images.tar.zst
install -m 755 "$G/onemind-k3s-check" "$G/onemind-health-gate" "$G/rauc-pre-install" "$G/onemind-api-respond" $R/usr/lib/onemind/
install -m 644 "$G"/manifests/*.yaml $R/usr/lib/onemind/manifests/
install -m 644 "$G/k3s.service" "$G/onemind-health-gate.service" "$G/onemind-api.service" $R/etc/systemd/system/
: > $R/etc/default/k3s
chroot $R systemctl enable systemd-networkd.service systemd-networkd-wait-online.service \
  k3s.service onemind-api.service onemind-health-gate.service >/dev/null 2>&1
chroot $R passwd -l root >/dev/null
chroot $R systemctl mask systemd-logind.service >/dev/null 2>&1   # restart-loops in this minimal image (LAB-rauc §9.6)
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
log "ext4 images (rootfs $(du -sm $R | cut -f1) MiB)"
mkimg v1 1 "" ""
mkimg good 2 "" ""
mkimg bad-k3s 3 "--onemind-lab-unknown-flag" ""                      # k3s exits at start
mkimg bad-noagent 4 "--disable-agent" ""                              # API up, kubelet never runs
INIT=$(readlink -f $R/sbin/init); mv $R/sbin/init $R/sbin/init.real
printf '#!/bin/sh\necho "BAD-BOOT: broken init exiting"\nexit 1\n' > $R/sbin/init; chmod 755 $R/sbin/init
mkimg bad-boot 5 "" ""                                                # kernel panic
install -m 755 "$G/bad-hang-init" $R/sbin/init
mkimg bad-hang 6 "" ""                                                # freezes with watchdog armed
rm -f $R/sbin/init; mv $R/sbin/init.real $R/sbin/init
mkimg naive-noagent 7 "--disable-agent" "ONEMIND_GATE_FRESHNESS=0"    # T10 observation only
echo "K3S_EXTRA_ARGS=" > $R/etc/default/k3s; : > $R/etc/default/onemind-health-gate

# ------------------------------------------------------------- 5. bundles
mkbundle(){ # $1=image $2=version $3=key-prefix $4=out [$5=format, default verity]
  local d="$W/bundles/$4.d"; rm -rf "$d"; mkdir -p "$d"
  cp "$W/stage/$1.ext4" "$d/rootfs.ext4"
  printf '[update]\ncompatible=%s\nversion=%s\n\n[bundle]\nformat=%s\n\n[image.rootfs]\nfilename=rootfs.ext4\n' "$COMPAT" "$2" "${5:-verity}" > "$d/manifest.raucm"
  rm -f "$W/bundles/$4.raucb"
  "$RAUC" bundle --cert="$W/keys/$3-signer.cert.pem" --key="$W/keys/$3-signer.key.pem" "$d" "$W/bundles/$4.raucb" >/dev/null
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
mkbundle good 2 lab plain-good plain                                  # T11: valid signature, plain format
for b in good bad-k3s bad-noagent bad-boot bad-hang naive-noagent plain-good; do
  "$RAUC" info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/$b.raucb" 2>&1 | grep -E "^Version|Verified|Bundle Format" | sed "s/^/[$b] /"
done
if "$RAUC" info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/wrong-key.raucb" >/dev/null 2>&1; then
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
cp "$W/stage/grub.cfg" "$OUT/grub.cfg"; cp "$W/keys/lab-ca.cert.pem" "$OUT/"   # public cert only
( cd "$OUT" && sha256sum disk.img *.raucb grub.cfg lab-ca.cert.pem ) > "$OUT/SHA256SUMS"
ls -la "$OUT"/*.raucb | awk '{print $5, $9}'
log "kernel $KVER; done"; cat "$OUT/SHA256SUMS"
