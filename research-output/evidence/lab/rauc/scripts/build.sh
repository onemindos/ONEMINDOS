#!/bin/bash
# LAB-rauc build: Debian 13 amd64 RAUC A/B disk image + 4 bundles.
# Run as root INSIDE a disposable Debian 13 Lima VM (arm64 is fine: amd64 is
# bootstrapped through qemu-user binfmt). Never run on the host.
#   sudo OUT=/path/to/out ./build.sh
# Needs: mmdebstrap qemu-user-binfmt rauc gdisk dosfstools mtools e2fsprogs
#        squashfs-tools openssl grub-common
set -euo pipefail

W=${W:-/var/lab/rauc}            # VM-local work dir (fast disk, loop-free)
OUT=${OUT:?set OUT to the output dir}
SUITE=trixie
MIRROR=http://deb.debian.org/debian
COMPAT=onemind-lab-x86_64
IMG_MB=1800                      # ext4 image written into each 2 GiB slot
# Fixed GPT partition GUIDs so GRUB can name the root of each slot.
GUID_ESP=0FC63DAF-8483-4772-8E79-3D69D8477DE4
PU_A=6e0a8b0e-0000-4a00-8000-00000000000a
PU_B=6e0a8b0e-0000-4a00-8000-00000000000b
PU_ESP=6e0a8b0e-0000-4a00-8000-0000000000e5
PU_DATA=6e0a8b0e-0000-4a00-8000-0000000000da

log(){ echo "[build $(date -u +%T)] $*"; }
rm -rf "$W"; mkdir -p "$W"/{keys,bundles,stage} "$OUT"

# ---------------------------------------------------------------- 1. lab PKI
# Throwaway keys. They stay in the VM work dir; never commit private keys.
log "lab PKI"
cd "$W/keys"
for ca in lab wrong; do
  openssl req -x509 -newkey rsa:3072 -nodes -days 30 -sha256 \
    -keyout $ca-ca.key.pem -out $ca-ca.cert.pem -subj "/O=OneMind LAB/CN=$ca-ca" 2>/dev/null
  openssl req -newkey rsa:3072 -nodes -sha256 -keyout $ca-signer.key.pem \
    -out $ca-signer.csr -subj "/O=OneMind LAB/CN=$ca-signer" 2>/dev/null
  openssl x509 -req -in $ca-signer.csr -CA $ca-ca.cert.pem -CAkey $ca-ca.key.pem \
    -CAcreateserial -days 30 -sha256 -out $ca-signer.cert.pem \
    -extfile <(printf 'keyUsage=critical,digitalSignature\n') 2>/dev/null
  # NOTE: an extendedKeyUsage=codeSigning signer is refused by RAUC 1.13's
  # default purpose check ("unsuitable certificate purpose"); see README.
done

# ---------------------------------------------------------- 2. amd64 rootfs
log "mmdebstrap amd64 $SUITE"
mmdebstrap --mode=root --arch=amd64 --variant=minbase \
  --include=systemd-sysv,udev,dbus,login,linux-image-amd64,initramfs-tools,rauc,rauc-service,grub-common,grub-efi-amd64-bin,e2fsprogs,util-linux,procps,kmod,squashfs-tools \
  $SUITE "$W/rootfs" "deb $MIRROR $SUITE main" \
  "deb http://deb.debian.org/debian-security $SUITE-security main" 2>&1 | tail -3
R=$W/rootfs

log "customise rootfs"
echo onemind-lab > $R/etc/hostname
cat > $R/etc/fstab <<'EOF'
PARTLABEL=esp   /boot/efi  vfat  umask=0077  0 1
PARTLABEL=data  /data      ext4  defaults    0 2
EOF
mkdir -p $R/boot/efi $R/data $R/etc/rauc
cp "$W/keys/lab-ca.cert.pem" $R/etc/rauc/keyring.pem
cat > $R/etc/rauc/system.conf <<EOF
[system]
compatible=$COMPAT
bootloader=grub
grubenv=/boot/efi/EFI/BOOT/grubenv
data-directory=/data/rauc

[keyring]
path=/etc/rauc/keyring.pem

[slot.rootfs.0]
device=/dev/disk/by-partlabel/rootfs-A
type=ext4
bootname=A

[slot.rootfs.1]
device=/dev/disk/by-partlabel/rootfs-B
type=ext4
bootname=B
EOF
# Kernel/initrd symlinks inside the slot so GRUB loads the slot's own kernel.
KVER=$(ls $R/lib/modules | head -1)
ln -sf vmlinuz-$KVER $R/boot/vmlinuz
ln -sf initrd.img-$KVER $R/boot/initrd.img
# Serial autologin (lab only: no network device, disposable guest).
mkdir -p $R/etc/systemd/system/serial-getty@ttyS0.service.d
cat > $R/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --keep-baud 115200 %I linux
EOF

# "Core platform" stand-in for k3s: a service with a heartbeat.
cat > $R/usr/local/bin/onemind-core <<'EOF'
#!/bin/sh
. /etc/onemind-release
if [ -e /etc/onemind-core-broken ]; then
  echo "onemind-core: simulated fatal startup error (version $ONEMIND_VERSION)"; exit 1
fi
while :; do touch /run/onemind-core.heartbeat; sleep 2; done
EOF
cat > $R/etc/systemd/system/onemind-core.service <<'EOF'
[Unit]
Description=OneMind core platform (lab stand-in for k3s + core pods)
[Service]
ExecStart=/usr/local/bin/onemind-core
Restart=on-failure
RestartSec=2
StartLimitBurst=3
[Install]
WantedBy=multi-user.target
EOF

# Health gate: commit the booted slot only when the core is healthy.
cat > $R/usr/local/bin/onemind-health-gate <<'EOF'
#!/bin/sh
# Every boot under RAUC's GRUB script sets <slot>_TRY=1, so every boot must
# end in mark-good (healthy) or mark-bad + reboot (unhealthy).
GRUBENV=/boot/efi/EFI/BOOT/grubenv
SOAK=${SOAK:-15}
SLOT=$(sed -n 's/.*rauc\.slot=\([A-Z]\).*/\1/p' /proc/cmdline)
. /etc/onemind-release; VER=$ONEMIND_VERSION
log(){ echo "HEALTH-GATE: $*" | tee -a /data/gate.log >/dev/console; }
log "start slot=$SLOT version=$VER soak=${SOAK}s"
sleep "$SOAK"
ok=0
for i in $(seq 1 15); do
  if systemctl is-active -q onemind-core.service && [ -f /run/onemind-core.heartbeat ] &&
     [ $(( $(date +%s) - $(stat -c %Y /run/onemind-core.heartbeat) )) -lt 10 ]; then ok=1; break; fi
  sleep 2
done
if [ $ok = 1 ]; then
  if rauc status mark-good booted >/dev/null 2>/tmp/gate.err; then
    log "RESULT mark-good slot=$SLOT version=$VER"; exit 0
  fi
  log "RESULT commit-error slot=$SLOT version=$VER: $(tail -1 /tmp/gate.err)"; exit 1
fi
OTHER=A; [ "$SLOT" = A ] && OTHER=B
if grub-editenv $GRUBENV list | grep -q "^${OTHER}_OK=1"; then
  rauc status mark-bad booted >/dev/null
  log "RESULT mark-bad slot=$SLOT version=$VER core-unhealthy -> reboot to $OTHER"
  systemctl reboot
else
  log "RESULT unhealthy slot=$SLOT version=$VER but no good fallback slot: staying"; exit 1
fi
EOF
cat > $R/etc/systemd/system/onemind-health-gate.service <<'EOF'
[Unit]
Description=OneMind health gate (commit or reject the booted RAUC slot)
After=onemind-core.service rauc.service local-fs.target
Wants=onemind-core.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/onemind-health-gate
[Install]
WantedBy=multi-user.target
EOF
chmod 755 $R/usr/local/bin/onemind-core $R/usr/local/bin/onemind-health-gate
chroot $R systemctl enable onemind-core.service onemind-health-gate.service >/dev/null 2>&1
chroot $R passwd -l root >/dev/null
# logind restart-loops in this minimal image (not needed on a serial-only lab
# guest); masked to keep logs readable. Not part of the update path.
chroot $R systemctl mask systemd-logind.service >/dev/null 2>&1

# Record exact package versions of the image (pinning evidence).
chroot $R dpkg-query -W -f='${Package} ${Version}\n' > "$OUT/image-packages.txt"

# ---------------------------------------------------- 3. GRUB EFI + grub.cfg
log "grub-mkstandalone (x86_64-efi, inside amd64 chroot)"
# grub-mkstandalone does not auto-load partition/filesystem modules: without
# these insmods GRUB sees (hd0) but no (hd0,gpt1) and drops to grub>.
printf 'insmod part_gpt\ninsmod fat\ninsmod ext2\ninsmod loadenv\ninsmod test\ninsmod linux\nset root=(hd0,gpt1)\nconfigfile /EFI/BOOT/grub.cfg\n' > $R/tmp/embed.cfg
chroot $R grub-mkstandalone -O x86_64-efi -o /tmp/BOOTX64.EFI "boot/grub/grub.cfg=/tmp/embed.cfg"
cp $R/tmp/BOOTX64.EFI "$W/stage/"; rm -f $R/tmp/BOOTX64.EFI $R/tmp/embed.cfg

# Boot script: RAUC upstream contrib/grub.conf (rauc@2d17b27), adapted for
# grubenv on the ESP, GPT naming and PARTUUID roots. Entry 0 is the
# "no good slot left" fallback (slot A without gating), like upstream Rescue.
cat > "$W/stage/grub.cfg" <<EOF
default=0
timeout=1
set ORDER="A B"
set A_OK=0
set B_OK=0
set A_TRY=0
set B_TRY=0
load_env --file=(hd0,gpt1)/EFI/BOOT/grubenv

for SLOT in \$ORDER; do
    if [ "\$SLOT" == "A" ]; then
        INDEX=1
        OK=\$A_OK
        TRY=\$A_TRY
        A_TRY=1
    fi
    if [ "\$SLOT" == "B" ]; then
        INDEX=2
        OK=\$B_OK
        TRY=\$B_TRY
        B_TRY=1
    fi
    if [ "\$OK" -eq 1 -a "\$TRY" -eq 0 ]; then
        default=\$INDEX
        break
    fi
done

if [ "\$default" -eq 0 ]; then
    if [ "\$A_OK" -eq 1 -a "\$A_TRY" -eq 1 ]; then
        A_TRY=0
    fi
    if [ "\$B_OK" -eq 1 -a "\$B_TRY" -eq 1 ]; then
        B_TRY=0
    fi
fi

save_env --file=(hd0,gpt1)/EFI/BOOT/grubenv A_TRY A_OK B_TRY B_OK ORDER
echo "GRUB-RAUC: ORDER=\$ORDER A_OK=\$A_OK A_TRY=\$A_TRY B_OK=\$B_OK B_TRY=\$B_TRY default=\$default"

CMDLINE="console=ttyS0,115200 panic=5 rootwait"

menuentry "Fallback (no good slot): A" {
    linux (hd0,gpt2)/boot/vmlinuz root=PARTUUID=$PU_A \$CMDLINE rauc.slot=A
    initrd (hd0,gpt2)/boot/initrd.img
}
menuentry "Slot A" {
    linux (hd0,gpt2)/boot/vmlinuz root=PARTUUID=$PU_A \$CMDLINE rauc.slot=A
    initrd (hd0,gpt2)/boot/initrd.img
}
menuentry "Slot B" {
    linux (hd0,gpt3)/boot/vmlinuz root=PARTUUID=$PU_B \$CMDLINE rauc.slot=B
    initrd (hd0,gpt3)/boot/initrd.img
}
EOF
grub-editenv "$W/stage/grubenv" create
grub-editenv "$W/stage/grubenv" set ORDER="A B" A_OK=1 A_TRY=0 B_OK=0 B_TRY=0

# ------------------------------------------------- 4. rootfs image variants
mkimg(){ # $1=name $2=version  (tree must already be prepared)
  echo "ONEMIND_VERSION=$2" > $R/etc/onemind-release
  rm -f "$W/stage/$1.ext4"
  mke2fs -q -t ext4 -L rootfs -d $R "$W/stage/$1.ext4" ${IMG_MB}M
}
log "ext4 images"
mkimg v1 1
mkimg good 2
# bad-health: boots fine, core service dies at start.
touch $R/etc/onemind-core-broken
mkimg bad-health 3
rm -f $R/etc/onemind-core-broken
# bad-boot: init exits immediately -> kernel panic -> panic=5 reboot.
INIT=$(readlink -f $R/sbin/init); mv $R/sbin/init $R/sbin/init.real
printf '#!/bin/sh\necho "BAD-BOOT: broken init exiting"\nexit 1\n' > $R/sbin/init; chmod 755 $R/sbin/init
mkimg bad-boot 4
rm -f $R/sbin/init; mv $R/sbin/init.real $R/sbin/init

# ------------------------------------------------------------- 5. bundles
mkbundle(){ # $1=image $2=version $3=key-prefix $4=out
  local d="$W/bundles/$4.d"; rm -rf "$d"; mkdir -p "$d"
  cp "$W/stage/$1.ext4" "$d/rootfs.ext4"
  cat > "$d/manifest.raucm" <<EOF
[update]
compatible=$COMPAT
version=$2

[bundle]
format=verity

[image.rootfs]
filename=rootfs.ext4
EOF
  rm -f "$W/bundles/$4.raucb"
  rauc bundle --cert="$W/keys/$3-signer.cert.pem" --key="$W/keys/$3-signer.key.pem" \
    "$d" "$W/bundles/$4.raucb" >/dev/null
  rm -rf "$d"
}
log "rauc bundles"
mkbundle good 2 lab good
mkbundle bad-health 3 lab bad-health
mkbundle bad-boot 4 lab bad-boot
mkbundle good 2 wrong wrong-key
for b in good bad-health bad-boot; do
  rauc info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/$b.raucb" 2>&1 | grep -E -i "compatible|version|verif|format" | sed "s/^/[$b] /" || true
done
if rauc info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/wrong-key.raucb" >/dev/null 2>&1; then
  echo "ERROR: wrong-key bundle verified"; exit 1
else echo "[wrong-key] rejected by rauc info (expected)"; fi

# ------------------------------------------------------------ 6. disk image
log "disk image"
D=$OUT/disk.img; rm -f "$D"; truncate -s 8G "$D"
sgdisk -Z "$D" >/dev/null
sgdisk -n1:2048:+128M -t1:EF00 -c1:esp -u1:$PU_ESP \
       -n2:0:+2G -t2:8300 -c2:rootfs-A -u2:$PU_A \
       -n3:0:+2G -t3:8300 -c3:rootfs-B -u3:$PU_B \
       -n4:0:0 -t4:8300 -c4:data -u4:$PU_DATA "$D" >/dev/null
start(){ sgdisk -i "$1" "$D" | awk '/First sector/{print $3}'; }
size(){ sgdisk -i "$1" "$D" | awk '/Partition size/{print $3}'; }
# ESP
rm -f "$W/stage/esp.img"; mkfs.fat -F32 -n ESP -C "$W/stage/esp.img" $(( $(size 1) / 2 )) >/dev/null
mmd -i "$W/stage/esp.img" ::/EFI ::/EFI/BOOT
mcopy -i "$W/stage/esp.img" "$W/stage/BOOTX64.EFI" "$W/stage/grub.cfg" "$W/stage/grubenv" ::/EFI/BOOT/
dd if="$W/stage/esp.img" of="$D" bs=512 seek=$(start 1) conv=notrunc,sparse status=none
# Slot A = v1. Slot B left empty.
dd if="$W/stage/v1.ext4" of="$D" bs=4M oflag=seek_bytes seek=$(( $(start 2) * 512 )) conv=notrunc,sparse status=none
# Data partition carries the bundles (no network in the guest).
mkdir -p "$W/datafs/bundles" "$W/datafs/rauc"
cp "$W"/bundles/*.raucb "$W/datafs/bundles/"
rm -f "$W/stage/data.ext4"
mke2fs -q -t ext4 -L data -d "$W/datafs" "$W/stage/data.ext4" $(( $(size 4) / 2 ))k
dd if="$W/stage/data.ext4" of="$D" bs=4M oflag=seek_bytes seek=$(( $(start 4) * 512 )) conv=notrunc,sparse status=none
sgdisk -p "$D" | tail -6

# ---------------------------------------------------------- 7. provenance
cp "$W"/bundles/*.raucb "$OUT/"
cp "$W/stage/grub.cfg" "$OUT/grub.cfg"
cp "$W/keys/lab-ca.cert.pem" "$OUT/lab-ca.cert.pem"     # public cert only
( cd "$OUT" && sha256sum disk.img *.raucb grub.cfg lab-ca.cert.pem ) > "$OUT/SHA256SUMS"
log "kernel $KVER; done"
cat "$OUT/SHA256SUMS"
