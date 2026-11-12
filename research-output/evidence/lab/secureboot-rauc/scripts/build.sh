#!/bin/bash
# LAB-secureboot-rauc (X-2R) build: Debian 13 amd64 RAUC A/B image in the
# 01-FOUNDATION-DECISION §4.3 layout, booted as signed UKIs by RAUC's `efi`
# backend under UEFI Secure Boot with lab PK/KEK/db; LUKS2 data sealed to TPM2.
# Run as root INSIDE a disposable Debian 13 Lima VM (arm64 is fine: the amd64
# rootfs is bootstrapped through qemu-user binfmt). Never run on the host.
#   sudo OUT=/var/lab/sbout bash build.sh
# Needs: mmdebstrap qemu-user-binfmt rauc gdisk dosfstools mtools e2fsprogs
#        squashfs-tools openssl sbsigntool efitools python3-virt-firmware
#        systemd-ukify ovmf tpm2-tools (libtss2 for systemd-measure) python3-pefile
set -euo pipefail

W=${W:-/var/lab/sb}
OUT=${OUT:?set OUT}
SUITE=trixie
MIRROR=http://deb.debian.org/debian
COMPAT=onemind-lab-x86_64-sb
IMG_MB=1600                       # ext4 root image; slot is 10 GiB (headroom)
EFIIMG_MB=200                     # vfat image for boot-a/b (partition 512 MiB)
OWNER=6e0a8b0e-0000-4a00-8000-0000000000aa   # EFI signature owner GUID (lab)
PU_ESP=6e0a8b0e-0000-4a00-8000-0000000000e5
PU_BA=6e0a8b0e-0000-4a00-8000-0000000000ba
PU_BB=6e0a8b0e-0000-4a00-8000-0000000000bb
PU_SA=6e0a8b0e-0000-4a00-8000-00000000005a
PU_SB=6e0a8b0e-0000-4a00-8000-00000000005b
PU_REC=6e0a8b0e-0000-4a00-8000-0000000000ec
PU_DATA=6e0a8b0e-0000-4a00-8000-0000000000da
ESP_GUID=C12A7328-F81F-11D2-BA4B-00A0C93EC93B

log(){ echo "[build $(date -u +%T)] $*"; }
rm -rf "$W"; mkdir -p "$W"/{keys,bundles,stage,uki,pcrsig} "$OUT"

# ----------------------------------------------------------- 1. lab keys
# Throwaway keys; they stay in the VM work dir and are never committed.
log "lab Secure Boot keys (PK, KEK, db) and RAUC CA"
cd "$W/keys"
for k in PK KEK db; do
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -sha256 \
    -keyout $k.key -out $k.crt -subj "/O=OneMind LAB/CN=OneMind LAB $k" 2>/dev/null
done
openssl req -x509 -newkey rsa:3072 -nodes -days 30 -sha256 -keyout rauc-ca.key \
  -out rauc-ca.crt -subj "/O=OneMind LAB/CN=rauc-lab-ca" 2>/dev/null
openssl req -newkey rsa:3072 -nodes -sha256 -keyout rauc-signer.key -out rauc-signer.csr \
  -subj "/O=OneMind LAB/CN=rauc-lab-signer" 2>/dev/null
openssl x509 -req -in rauc-signer.csr -CA rauc-ca.crt -CAkey rauc-ca.key -CAcreateserial \
  -days 30 -sha256 -out rauc-signer.crt -extfile <(printf 'keyUsage=critical,digitalSignature\n') 2>/dev/null
# Bonus T7: key for the signed PCR 11 policy.
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out pcr.key 2>/dev/null
openssl rsa -in pcr.key -pubout -out pcr.pub 2>/dev/null

log "OVMF vars: enroll lab PK/KEK/db only (no Microsoft keys), Secure Boot on"
virt-fw-vars --input /usr/share/OVMF/OVMF_VARS_4M.fd --output "$OUT/OVMF_VARS_sb.fd" \
  --set-pk $OWNER PK.crt --add-kek $OWNER KEK.crt --add-db $OWNER db.crt --secure-boot
cp /usr/share/OVMF/OVMF_VARS_4M.fd "$OUT/OVMF_VARS_nosb.fd"     # T6: setup mode, SB off
virt-fw-vars --input "$OUT/OVMF_VARS_sb.fd" --print 2>&1 | grep -E -i "PK|KEK|db|SecureBoot|subject|CN=" | head -20

# ---------------------------------------------------------- 2. amd64 rootfs
log "mmdebstrap amd64 $SUITE"
mmdebstrap --mode=root --arch=amd64 --variant=minbase \
  --include=systemd-sysv,udev,dbus,login,linux-image-amd64,initramfs-tools,rauc,rauc-service,efibootmgr,efitools,mokutil,cryptsetup-bin,systemd-cryptsetup,tpm2-tools,systemd-boot-efi,e2fsprogs,dosfstools,util-linux,procps,kmod,squashfs-tools \
  $SUITE "$W/rootfs" "deb $MIRROR $SUITE main" \
  "deb http://deb.debian.org/debian-security $SUITE-security main" 2>&1 | tail -3
R=$W/rootfs
KVER=$(ls $R/lib/modules | head -1)
cp $R/usr/lib/systemd/boot/efi/linuxx64.efi.stub "$W/stage/"
chroot $R dpkg-query -W -f='${Package} ${Version}\n' > "$OUT/image-packages.txt"

log "customise rootfs"
echo onemind-lab > $R/etc/hostname
mkdir -p $R/data $R/mnt/bundles $R/etc/rauc
cp "$W/keys/rauc-ca.crt" $R/etc/rauc/keyring.pem
cat > $R/etc/rauc/system.conf <<EOF
[system]
compatible=$COMPAT
bootloader=efi

[keyring]
path=/etc/rauc/keyring.pem

[slot.efi.0]
device=/dev/disk/by-partlabel/onemind-boot-a
type=vfat
parent=rootfs.0

[slot.efi.1]
device=/dev/disk/by-partlabel/onemind-boot-b
type=vfat
parent=rootfs.1

[slot.rootfs.0]
device=/dev/disk/by-partlabel/onemind-system-a
type=ext4
bootname=OneMind-A

[slot.rootfs.1]
device=/dev/disk/by-partlabel/onemind-system-b
type=ext4
bootname=OneMind-B
EOF
echo 'LABEL=bundles /mnt/bundles ext4 ro,nofail,x-systemd.device-timeout=10s 0 0' > $R/etc/fstab
mkdir -p $R/etc/systemd/system/serial-getty@ttyS0.service.d
cat > $R/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --keep-baud 115200 %I linux
EOF

# Boot report: Secure Boot state, keys and EFI boot variables on every boot.
cat > $R/usr/local/bin/onemind-sb-report <<'EOF'
#!/bin/sh
V=/sys/firmware/efi/efivars
GV=8be4df61-93ca-11d2-aa0d-00e098032b8c
b(){ od -An -tu1 -j4 -N1 "$V/$1-$GV" 2>/dev/null | tr -d ' '; }
out(){ echo "SB-REPORT: $*" >/dev/console; }
. /etc/onemind-release
out "version=$ONEMIND_VERSION cmdline-slot=$(sed -n 's/.*rauc\.slot=\(\S*\).*/\1/p' /proc/cmdline) SecureBoot=$(b SecureBoot) SetupMode=$(b SetupMode)"
out "kernel: $(dmesg | grep -i -m1 -E 'secure ?boot' | sed 's/^\[[^]]*\] //')"
out "lockdown: $(cat /sys/kernel/security/lockdown 2>/dev/null)"
out "PK: $(efi-readvar -v PK 2>/dev/null | grep -m1 -o 'Subject:.*\|CN=[^,]*' )"
out "db: $(efi-readvar -v db 2>/dev/null | grep -o 'CN=[^,]*' | tr '\n' ' ')"
efibootmgr 2>/dev/null | grep -E '^Boot(Current|Next|Order)|OneMind' | while read -r l; do out "efi: $l"; done
EOF

# First boot: create the per-slot EFI boot entries (an installer would do this).
cat > $R/usr/local/bin/onemind-efi-entries <<'EOF'
#!/bin/sh
efibootmgr | grep -q 'OneMind-A' && exit 0
efibootmgr -q --create --disk /dev/vda --part 2 --label OneMind-A --loader '\EFI\Linux\onemind-A.efi'
efibootmgr -q --create --disk /dev/vda --part 3 --label OneMind-B --loader '\EFI\Linux\onemind-B.efi'
A=$(efibootmgr | sed -n 's/^Boot\([0-9A-F]\{4\}\)\* OneMind-A.*/\1/p')
B=$(efibootmgr | sed -n 's/^Boot\([0-9A-F]\{4\}\)\* OneMind-B.*/\1/p')
efibootmgr -q -o "$A,$B"
echo "EFI-ENTRIES: created OneMind-A=$A OneMind-B=$B BootOrder=$A,$B" >/dev/console
EOF

# Data partition: LUKS2 from first boot, TPM2-sealed (PCR 7; PCR 11 signed
# policy as a bonus), recovery key, never a blocking prompt.
cat > $R/usr/local/bin/onemind-data <<'EOF'
#!/bin/sh
DEV=/dev/disk/by-partlabel/onemind-data
out(){ echo "DATA: $*" >/dev/console; echo "DATA: $*" >>/run/onemind-data.log; }
if ! cryptsetup isLuks $DEV; then
  out "first boot: provisioning LUKS2"
  umask 077; head -c 48 /dev/urandom > /run/k
  cryptsetup luksFormat --type luks2 --batch-mode --key-file /run/k $DEV
  cryptsetup open --key-file /run/k $DEV dataprov && mkfs.ext4 -q -L data /dev/mapper/dataprov && cryptsetup close dataprov
  systemd-cryptenroll --unlock-key-file=/run/k --tpm2-device=auto --tpm2-pcrs=7 $DEV >/dev/null 2>&1 \
    && out "enrolled tpm2 pcrs=7" || out "ERROR tpm2 enroll (pcr7) failed"
  systemd-cryptenroll --unlock-key-file=/run/k --recovery-key $DEV > /run/rk 2>/dev/null \
    && out "recovery key enrolled (lab: discarded)"
  # Remove the temporary key slot (keyslot 0); unlock with the recovery key.
  tr -d '\n' < /run/rk > /run/rk1
  cryptsetup luksKillSlot --batch-mode --key-file /run/rk1 $DEV 0 && out "temporary keyslot 0 wiped"
  rm -f /run/k /run/rk /run/rk1
fi
out "tokens: $(cryptsetup luksDump $DEV | sed -n 's/^ *[0-9]*: \(systemd-[a-z0-9-]*\)$/\1/p' | tr '\n' ' ')"
if /usr/lib/systemd/systemd-cryptsetup attach data $DEV - tpm2-device=auto,headless=true >/run/attach.log 2>&1; then
  mount /dev/mapper/data /data && out "UNLOCK OK method=tpm2 (no prompt); /data mounted"
else
  out "UNLOCK FAILED (tpm2 unseal refused): $(tail -1 /run/attach.log)"
fi
# Bonus T7: separate 32 MiB LUKS2 container bound ONLY to a signed PCR 11
# policy (+PCR 7), so the main data unlock above cannot mask its result.
if mountpoint -q /data; then
  SL=$(sed -n 's/.*rauc\.slot=OneMind-\([A-Z]\).*/\1/p' /proc/cmdline)
  SIG=/etc/onemind/pcrsig-$SL.json; T=/data/pcr11-test.luks
  if [ ! -f $T ]; then
    umask 077; head -c 48 /dev/urandom > /run/k2; truncate -s 32M $T
    cryptsetup luksFormat --type luks2 --batch-mode --key-file /run/k2 $T
    systemd-cryptenroll --unlock-key-file=/run/k2 --tpm2-device=auto --tpm2-public-key=/etc/onemind/pcr.pub \
      --tpm2-public-key-pcrs=11 --tpm2-signature=$SIG --tpm2-pcrs=7 $T >/run/b.log 2>&1 \
      && cryptsetup luksKillSlot --batch-mode $T 0 && echo "BONUS-PCR11: enrolled signed-pcr11+pcr7, password slot wiped" >/dev/console \
      || echo "BONUS-PCR11: enroll failed: $(tail -1 /run/b.log)" >/dev/console
    rm -f /run/k2
  fi
  L=$(losetup -f --show $T)
  if /usr/lib/systemd/systemd-cryptsetup attach pcr11t $L - tpm2-device=auto,headless=true,tpm2-signature=$SIG >/run/b2.log 2>&1; then
    echo "BONUS-PCR11: UNLOCK OK slot=$SL (signed PCR 11 policy)" >/dev/console
    /usr/lib/systemd/systemd-cryptsetup detach pcr11t
  else echo "BONUS-PCR11: UNLOCK FAILED slot=$SL: $(tail -1 /run/b2.log)" >/dev/console; fi
  losetup -d $L
fi
exit 0
EOF

cat > $R/usr/local/bin/onemind-core <<'EOF'
#!/bin/sh
. /etc/onemind-release
if [ -e /etc/onemind-core-broken ]; then
  echo "onemind-core: simulated fatal startup error (version $ONEMIND_VERSION)"; exit 1
fi
while :; do touch /run/onemind-core.heartbeat; sleep 2; done
EOF

# Health gate: commit only when core is healthy AND /data is unlocked.
cat > $R/usr/local/bin/onemind-health-gate <<'EOF'
#!/bin/sh
SOAK=${SOAK:-10}
SLOT=$(sed -n 's/.*rauc\.slot=OneMind-\([A-Z]\).*/\1/p' /proc/cmdline)
. /etc/onemind-release; VER=$ONEMIND_VERSION
log(){ echo "HEALTH-GATE: $*" >/dev/console; mountpoint -q /data && echo "$(date -u +%FT%TZ) $*" >>/data/gate.log; }
log "start slot=$SLOT version=$VER soak=${SOAK}s"
sleep "$SOAK"
ok=0; why=core-unhealthy
for i in $(seq 1 10); do
  if systemctl is-active -q onemind-core.service && [ -f /run/onemind-core.heartbeat ] &&
     [ $(( $(date +%s) - $(stat -c %Y /run/onemind-core.heartbeat) )) -lt 10 ]; then
    if mountpoint -q /data; then ok=1; break; else why=data-locked; fi
  fi
  sleep 2
done
if [ $ok = 1 ]; then
  if rauc status mark-good booted >/dev/null 2>/tmp/gate.err; then
    log "RESULT mark-good slot=$SLOT version=$VER"; exit 0
  fi
  log "RESULT commit-error slot=$SLOT version=$VER: $(tail -1 /tmp/gate.err)"; exit 1
fi
OTHER=A; [ "$SLOT" = A ] && OTHER=B
ON=$(efibootmgr | sed -n "s/^Boot\([0-9A-F]\{4\}\)\* OneMind-$OTHER.*/\1/p")
if [ "$why" = core-unhealthy ] && efibootmgr | grep '^BootOrder' | grep -q "$ON"; then
  rauc status mark-bad booted >/dev/null
  log "RESULT mark-bad slot=$SLOT version=$VER $why -> reboot to $OTHER"
  systemctl reboot
else
  log "RESULT no-commit slot=$SLOT version=$VER $why (no automatic rollback)"; exit 1
fi
EOF

for u in efi-entries:"Create OneMind EFI boot entries (first boot)":"local-fs.target":"" \
         data:"Unlock OneMind data partition (LUKS2 + TPM2)":"onemind-efi-entries.service":"" \
         sb-report:"Report Secure Boot state":"onemind-data.service":"" ; do
  n=${u%%:*}; rest=${u#*:}; d=${rest%%:*}; rest=${rest#*:}; a=${rest%%:*}
  cat > $R/etc/systemd/system/onemind-$n.service <<EOF
[Unit]
Description=$d
After=$a
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/onemind-$n
[Install]
WantedBy=multi-user.target
EOF
done
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
cat > $R/etc/systemd/system/onemind-health-gate.service <<'EOF'
[Unit]
Description=OneMind health gate (commit or reject the booted RAUC slot)
After=onemind-core.service onemind-data.service onemind-sb-report.service
Wants=onemind-core.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/onemind-health-gate
[Install]
WantedBy=multi-user.target
EOF
chmod 755 $R/usr/local/bin/onemind-*
mkdir -p $R/etc/onemind; cp "$W/keys/pcr.pub" $R/etc/onemind/pcr.pub
chroot $R systemctl enable onemind-efi-entries onemind-data onemind-sb-report onemind-core onemind-health-gate >/dev/null 2>&1
chroot $R passwd -l root >/dev/null
chroot $R systemctl mask systemd-logind.service >/dev/null 2>&1

# --------------------------------------------------------------- 3. UKIs
# One signed UKI per slot; the kernel command line is inside the signature.
mkuki(){ # $1=slot(A|B) $2=version $3=out $4=sign(yes|no)
  local pu=$PU_SA; [ "$1" = B ] && pu=$PU_SB
  local args=(build --linux="$R/boot/vmlinuz-$KVER" --initrd="$R/boot/initrd.img-$KVER"
    --stub="$W/stage/linuxx64.efi.stub" --uname="$KVER" --os-release=@"$R/etc/os-release"
    --cmdline="root=PARTUUID=$pu ro rootwait console=ttyS0,115200 panic=5 rauc.slot=OneMind-$1 onemind.version=$2"
    --pcr-private-key="$W/keys/pcr.key" --pcr-public-key="$W/keys/pcr.pub"
    --phases="sysinit sysinit:ready enter-initrd enter-initrd:leave-initrd enter-initrd:leave-initrd:sysinit enter-initrd:leave-initrd:sysinit:ready"
    --output="$3")
  [ "$4" = yes ] && args+=(--signtool=sbsign --secureboot-private-key="$W/keys/db.key" --secureboot-certificate="$W/keys/db.crt")
  ukify "${args[@]}" >/dev/null
}
mkefi(){ # $1=version $2=mode(signed|tampered|unsigned) -> $W/stage/efi-$1.vfat
  local s=yes; [ "$2" = unsigned ] && s=no
  for sl in A B; do mkuki $sl $1 "$W/uki/onemind-$sl-v$1.efi" $s
    # Keep the signed PCR 11 policy (.pcrsig) for the rootfs (bonus T7; the
    # initramfs-tools initrd does not pass systemd-stub's /.extra on).
    python3 -I -c "import pefile,sys; pe=pefile.PE(sys.argv[1]); print(next(x.get_data().rstrip(b'\\0').decode() for x in pe.sections if x.Name.rstrip(b'\\0')==b'.pcrsig'))" \
      "$W/uki/onemind-$sl-v$1.efi" > "$W/pcrsig/v$1-$sl.json"
  done
  if [ "$2" = tampered ]; then
    # Change one byte of the embedded command line AFTER signing.
    for sl in A B; do
      python3 -I - "$W/uki/onemind-$sl-v$1.efi" <<'PY'
import sys; p=sys.argv[1]; b=open(p,'rb').read()
assert b.count(b'panic=5')==1; open(p,'wb').write(b.replace(b'panic=5',b'panic=6'))
PY
    done
  fi
  for sl in A B; do
    echo "[uki v$1 $2 $sl] sha256 $(sha256sum < "$W/uki/onemind-$sl-v$1.efi" | cut -c1-16)… sbverify: $(sbverify --cert "$W/keys/db.crt" "$W/uki/onemind-$sl-v$1.efi" 2>&1 | tail -1)"
  done
  local f="$W/stage/efi-$1.vfat"; rm -f "$f"
  mkfs.fat -F32 -n ONEMINDBOOT -C "$f" $((EFIIMG_MB*1024)) >/dev/null
  mmd -i "$f" ::/EFI ::/EFI/Linux
  mcopy -i "$f" "$W/uki/onemind-A-v$1.efi" ::/EFI/Linux/onemind-A.efi
  mcopy -i "$f" "$W/uki/onemind-B-v$1.efi" ::/EFI/Linux/onemind-B.efi
}
log "UKIs (ukify + sbsign with lab db key)"
mkefi 1 signed; mkefi 2 signed; mkefi 3 signed; mkefi 4 tampered; mkefi 5 unsigned

# --------------------------------------------------- 4. rootfs image variants
mkimg(){ echo "ONEMIND_VERSION=$2" > $R/etc/onemind-release; rm -f "$W/stage/$1.ext4"
  cp "$W/pcrsig/v$2-A.json" $R/etc/onemind/pcrsig-A.json; cp "$W/pcrsig/v$2-B.json" $R/etc/onemind/pcrsig-B.json
  mke2fs -q -t ext4 -L rootfs -d $R "$W/stage/$1.ext4" ${IMG_MB}M; }
log "ext4 images"
mkimg v1 1; mkimg good 2
touch $R/etc/onemind-core-broken; mkimg bad-health 3; rm -f $R/etc/onemind-core-broken
mkimg tampered 4; mkimg unsigned 5

# ------------------------------------------------------------- 5. bundles
mkbundle(){ # $1=rootfs-image $2=version $3=out
  local d="$W/bundles/$3.d"; rm -rf "$d"; mkdir -p "$d"
  cp "$W/stage/$1.ext4" "$d/rootfs.ext4"; cp "$W/stage/efi-$2.vfat" "$d/efi.vfat"
  cat > "$d/manifest.raucm" <<EOF
[update]
compatible=$COMPAT
version=$2

[bundle]
format=verity

[image.rootfs]
filename=rootfs.ext4

[image.efi]
filename=efi.vfat
EOF
  rauc bundle --cert="$W/keys/rauc-signer.crt" --key="$W/keys/rauc-signer.key" "$d" "$W/bundles/$3.raucb" >/dev/null
  rm -rf "$d"
  echo "[$3] $(rauc info --keyring="$W/keys/rauc-ca.crt" "$W/bundles/$3.raucb" 2>&1 | grep -E -i 'Verified|version' | tr '\n' ' ')"
}
log "rauc bundles"
mkbundle good 2 good; mkbundle bad-health 3 bad-health; mkbundle tampered 4 tampered; mkbundle unsigned 5 unsigned

# ------------------------------------------------------------ 6. disk images
log "disk image (01 §4.3 layout)"
D=$OUT/disk.img; rm -f "$D"; truncate -s 26G "$D"
sgdisk -Z "$D" >/dev/null
sgdisk -n1:2048:+1G   -t1:$ESP_GUID -c1:onemind-esp      -u1:$PU_ESP \
       -n2:0:+512M    -t2:$ESP_GUID -c2:onemind-boot-a   -u2:$PU_BA \
       -n3:0:+512M    -t3:$ESP_GUID -c3:onemind-boot-b   -u3:$PU_BB \
       -n4:0:+10G     -t4:8304      -c4:onemind-system-a -u4:$PU_SA \
       -n5:0:+10G     -t5:8304      -c5:onemind-system-b -u5:$PU_SB \
       -n6:0:+1G      -t6:8300      -c6:onemind-recovery -u6:$PU_REC \
       -n7:0:+2G      -t7:8309      -c7:onemind-data     -u7:$PU_DATA "$D" >/dev/null
st(){ sgdisk -i "$1" "$D" | awk '/First sector/{print $3}'; }
sz(){ sgdisk -i "$1" "$D" | awk '/Partition size/{print $3}'; }
put(){ dd if="$1" of="$D" bs=4M oflag=seek_bytes seek=$(( $(st $2) * 512 )) conv=notrunc,sparse status=none; }
# ESP: factory first-boot loader = signed UKI for slot A (v1).
rm -f "$W/stage/esp.img"; mkfs.fat -F32 -n ONEMINDESP -C "$W/stage/esp.img" $(( $(sz 1) / 2 )) >/dev/null
mmd -i "$W/stage/esp.img" ::/EFI ::/EFI/BOOT
mcopy -i "$W/stage/esp.img" "$W/uki/onemind-A-v1.efi" ::/EFI/BOOT/BOOTX64.EFI
put "$W/stage/esp.img" 1
put "$W/stage/efi-1.vfat" 2
rm -f "$W/stage/empty.vfat"; mkfs.fat -F32 -n ONEMINDBOOT -C "$W/stage/empty.vfat" $((EFIIMG_MB*1024)) >/dev/null
put "$W/stage/empty.vfat" 3
put "$W/stage/v1.ext4" 4
sgdisk -p "$D" | tail -8
# Bundles travel on a second, read-only disk (the guest has no network).
mkdir -p "$W/bfs"; cp "$W"/bundles/*.raucb "$W/bfs/"
rm -f "$OUT/bundles.img"; mke2fs -q -t ext4 -L bundles -d "$W/bfs" "$OUT/bundles.img" 1500M

# ---------------------------------------------------------- 7. provenance
cp "$W/keys/PK.crt" "$W/keys/KEK.crt" "$W/keys/db.crt" "$W/keys/rauc-ca.crt" "$OUT/"   # public certs only
( cd "$W/bundles" && sha256sum *.raucb ) > "$OUT/SHA256SUMS"
( cd "$W/uki" && sha256sum *.efi ) >> "$OUT/SHA256SUMS"
( cd "$OUT" && sha256sum disk.img bundles.img OVMF_VARS_sb.fd OVMF_VARS_nosb.fd PK.crt KEK.crt db.crt rauc-ca.crt ) >> "$OUT/SHA256SUMS"
sha256sum /usr/share/OVMF/OVMF_CODE_4M.secboot.fd /usr/share/OVMF/OVMF_VARS_4M.fd >> "$OUT/SHA256SUMS"
log "kernel $KVER; done"
