#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# PID 1 of the spike guest (CRITERIA-RECOVERY-VAULT.md). Boot 1: RC0, RC1, RC2, RC4. Boot 2: RC0, RC3, RC5, RC6, RC7.
# Prints one "RESULT <id> <verdict> <detail>" line per check on the serial console, then powers off.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin DM_DISABLE_UDEV=1
mount -t proc proc /proc; mount -t sysfs sys /sys; mount -t devtmpfs dev /dev 2>/dev/null
mount -t tmpfs run /run; mkdir -p /dev/mapper /data /mnt/vault /mnt/fsx /mnt/rest
for m in btrfs dm_crypt dm_mod loop ext4 qemu_fw_cfg; do modprobe "$m" 2>/dev/null; done
MODE=$(sed -n 's/.*vaultmode=\([a-z]*\).*/\1/p' /proc/cmdline)
STATE=/root/vault-state
MARK=/root/marker.txt  # the pattern file: the marker text is never on a command line
res() { echo "RESULT $*" > /dev/console; }
bye() { sync; echo o > /proc/sysrq-trigger; sleep 30; }
key() { cat "/sys/firmware/qemu_fw_cfg/by_name/opt/onemind/$1/raw" > "/run/$1" && chmod 600 "/run/$1"; }
found() { grep -a -F -q -f "$MARK" "$@"; }  # is the marker text in these files?
mb_s() { sed -n 's/.* \([0-9.,]* [MG]B\/s\)$/\1/p' | tail -1; }

boot=1; [ -f "$STATE" ] && boot=2
# ---- RC0 ------------------------------------------------------------------------------------------------
kv=$(uname -r)
[ "$boot" = 1 ] && mkfs.btrfs -q -f -L data /dev/vdb >/dev/null
mount /dev/vdb /data
fs=$(stat -f -c %T /data)
if [ "${kv#6.12.}" = "$kv" ]; then res RC0 FAIL "kernel $kv"
elif [ "$fs" != btrfs ]; then res RC0 FAIL "/data is $fs"
else res RC0 PASS "boot $boot kernel $kv /data $fs"; fi

if [ "$boot" = 1 ]; then
  # ---- RC1: fscrypt straight on btrfs (probe) --------------------------------------------------------------
  head -c 32 /dev/urandom > /run/raw.key
  fscrypt setup --force --quiet >/dev/null 2>&1
  out=$( { fscrypt setup /data --quiet --force && mkdir -p /data/fsc && \
           fscrypt encrypt /data/fsc --source=raw_key --name=probe --key=/run/raw.key --quiet; } 2>&1 | tr '\n' ' ' )
  if fscrypt status /data/fsc 2>/dev/null | grep -qi 'is encrypted'; then res RC1 MEASURED "fscrypt works on btrfs: $out"
  else res RC1 MEASURED "fscrypt refused on btrfs ($kv): ${out:0:300}"; fi

  # ---- RC2: the vault ---------------------------------------------------------------------------------
  key vaultkey; key recoverykey
  if [ "$MODE" = naive ]; then
    mkdir -p /data/vault && xxd -p -l 32 /dev/urandom | tr -d '\n' > /data/vault/marker && cp /data/vault/marker "$MARK"
    sha256sum < /data/vault/marker > /root/marker.sha
    if found -r /data/vault; then res RC2 FAIL "marker found in plain /data/vault (naive)"; else res RC2 PASS "marker absent"; fi
    res RC4 FAIL "no keyslots (naive)"
  else
    : > /data/vault.img; chattr +C /data/vault.img; fallocate -l 512M /data/vault.img
    cryptsetup luksFormat --type luks2 --batch-mode --key-file /run/vaultkey /data/vault.img >/dev/null 2>&1
    cryptsetup open --key-file /run/vaultkey /data/vault.img vault && mkfs.ext4 -q /dev/mapper/vault && \
      mount /dev/mapper/vault /mnt/vault
    xxd -p -l 32 /dev/urandom | tr -d '\n' > /mnt/vault/marker && cp /mnt/vault/marker "$MARK"
    sha256sum < /mnt/vault/marker > /root/marker.sha
    umount /mnt/vault; cryptsetup close vault; sync; echo 3 > /proc/sys/vm/drop_caches
    if found /data/vault.img; then res RC2 FAIL "marker text found in the raw vault file"
    else
      cryptsetup open --key-file /run/vaultkey /data/vault.img vault && mount -o ro /dev/mapper/vault /mnt/vault
      if sha256sum < /mnt/vault/marker | cmp -s - /root/marker.sha; then
        res RC2 PASS "raw file ciphertext only; reopened marker unchanged; nocow=$(lsattr /data/vault.img | cut -c1-22 | grep -c C)"
      else res RC2 FAIL "reopened marker differs"; fi
      umount /mnt/vault; cryptsetup close vault
    fi
    # ---- RC4: a second way in ----------------------------------------------------------------------------
    cryptsetup luksAddKey --batch-mode --key-file /run/vaultkey /data/vault.img /run/recoverykey >/dev/null 2>&1
    head -c 64 /dev/urandom > /run/wrong.key
    # cryptsetup's own messages (an argon2 memory warning in a small guest) must not reach the verdicts.
    a=$(cryptsetup open --test-passphrase --key-file /run/vaultkey /data/vault.img >/dev/null 2>&1 && echo y)
    b=$(cryptsetup open --test-passphrase --key-file /run/recoverykey /data/vault.img >/dev/null 2>&1 && echo y)
    w=$(cryptsetup open --test-passphrase --key-file /run/wrong.key /data/vault.img >/dev/null 2>&1 && echo y)
    slots=$(cryptsetup luksDump /data/vault.img | grep -cE '^ +[0-9]+: luks2')
    if [ "$a" = y ] && [ "$b" = y ] && [ -z "$w" ] && [ "$slots" = 2 ]; then res RC4 PASS "two keyslots; each key opens; a wrong key is refused"
    else res RC4 FAIL "vault=$a recovery=$b wrong=$w slots=$slots"; fi
  fi
  rm -f /run/vaultkey /run/recoverykey
  echo 2 > "$STATE"; bye
fi

# ---- boot 2. RC3: locked after a restart (before any key is read) ---------------------------------------------
active=0
for m in /dev/mapper/*; do [ "$m" = /dev/mapper/control ] || [ ! -e "$m" ] || active=$((active + 1)); done
if [ "$MODE" = naive ]; then
  if [ -r /data/vault/marker ]; then res RC3 FAIL "marker readable at /data/vault/marker with no key (naive)"; else res RC3 PASS "not readable"; fi
else
  readable=$(grep -rlsa -F -f "$MARK" /data 2>/dev/null | head -1)
  key vaultkey; key recoverykey
  cryptsetup open --key-file /run/vaultkey /data/vault.img vault && mount -o ro /dev/mapper/vault /mnt/vault
  ok=$(sha256sum < /mnt/vault/marker | cmp -s - /root/marker.sha && echo y)
  umount /mnt/vault; cryptsetup close vault
  if [ "$active" = 0 ] && [ -z "$readable" ] && [ "$ok" = y ]; then res RC3 PASS "no mapping and no readable marker after reboot; the key opens it"
  else res RC3 FAIL "mappings=$active readable=$readable reopened=$ok"; fi
fi

# ---- RC5: ciphertext-only backup -------------------------------------------------------------------------------
export RESTIC_PASSWORD_FILE=/run/kit.pw RESTIC_REPOSITORY=/data/restic
head -c 24 /dev/urandom | xxd -p > /run/kit.pw
restic init --quiet >/dev/null 2>&1
if [ "$MODE" = naive ]; then
  restic backup --quiet /data/vault >/dev/null 2>&1
  restic dump latest /data/vault/marker 2>/dev/null > /run/dump.bin
  if found /run/dump.bin; then res RC5 FAIL "the kit's restic key reveals the marker (naive)"; else res RC5 PASS "absent"; fi
else
  restic backup --quiet /data/vault.img >/dev/null 2>&1
  in_repo=$(grep -rlsa -F -f "$MARK" /data/restic | head -1)
  restic dump latest /data/vault.img 2>/dev/null > /run/dump.bin
  in_dump=$(found /run/dump.bin && echo y); rm -f /run/dump.bin
  before=$(du -sb /data/restic | cut -f1)
  cryptsetup open --key-file /run/vaultkey /data/vault.img vault && mount /dev/mapper/vault /mnt/vault
  head -c 1M /dev/urandom > /mnt/vault/change.bin; sha256sum < /mnt/vault/change.bin > /root/change.sha
  umount /mnt/vault; cryptsetup close vault; sync
  restic backup --quiet /data/vault.img >/dev/null 2>&1
  after=$(du -sb /data/restic | cut -f1); added=$(( (after - before) / 1048576 ))
  mkdir -p /data/restore; restic restore --quiet latest --target /data/restore >/dev/null 2>&1
  cryptsetup open --key-file /run/vaultkey /data/restore/data/vault.img rvault && mount -o ro /dev/mapper/rvault /mnt/rest
  rok=$(sha256sum < /mnt/rest/change.bin | cmp -s - /root/change.sha && echo y)
  umount /mnt/rest; cryptsetup close rvault
  if [ -z "$in_repo" ] && [ -z "$in_dump" ] && [ "$added" -lt 64 ] && [ "$rok" = y ]; then
    res RC5 PASS "repo and kit-key dump hold no marker; second backup added ${added} MiB (vault 512 MiB); restored vault opens"
  else res RC5 FAIL "in_repo=$in_repo in_dump=$in_dump added=${added}MiB restored_ok=$rok"; fi
fi

# ---- RC6: fscrypt on an ext4 loop file -------------------------------------------------------------------------
head -c 32 /dev/urandom > /run/raw.key
truncate -s 256M /data/fsx.img && mkfs.ext4 -q -F -O encrypt /data/fsx.img && mount -o loop /data/fsx.img /mnt/fsx
fscrypt setup --force --quiet >/dev/null 2>&1; fscrypt setup /mnt/fsx --quiet --force >/dev/null 2>&1
mkdir -p /mnt/fsx/vault
if fscrypt encrypt /mnt/fsx/vault --source=raw_key --name=fsx --key=/run/raw.key --quiet >/dev/null 2>&1; then
  cp "$MARK" /mnt/fsx/vault/marker-file; sync
  fscrypt lock /mnt/fsx/vault >/dev/null 2>&1
  names=$(find /mnt/fsx/vault -mindepth 1 -maxdepth 1 -printf '%f\n' | head -1); readable=$(cat /mnt/fsx/vault/marker-file 2>/dev/null | head -c 8)
  umount /mnt/fsx; inraw=$(found /data/fsx.img && echo y)
  res RC6 MEASURED "fscrypt on ext4 works on $kv; locked name shown as '${names:0:24}...', content readable='${readable:+y}', marker in raw file='${inraw:-n}'; needs its own ext4 file system (a loop file) on btrfs /data"
  mount -o loop /data/fsx.img /mnt/fsx && fscrypt unlock /mnt/fsx/vault --key=/run/raw.key --quiet >/dev/null 2>&1
else res RC6 MEASURED "fscrypt on ext4 failed on $kv"; fi

# ---- RC7: throughput -----------------------------------------------------------------------------------------
speed() {  # speed <dir>
  w=$(dd if=/dev/zero of="$1/speed.bin" bs=1M count=256 conv=fsync 2>&1 | mb_s)
  sync; echo 3 > /proc/sys/vm/drop_caches
  r=$(dd if="$1/speed.bin" of=/dev/null bs=1M 2>&1 | mb_s); rm -f "$1/speed.bin"
  echo "write $w read $r"
}
p=$(speed /data)
if [ "$MODE" != naive ]; then
  cryptsetup open --key-file /run/vaultkey /data/vault.img vault && mount /dev/mapper/vault /mnt/vault
  v=$(speed /mnt/vault); umount /mnt/vault; cryptsetup close vault
else v="n/a"; fi
f=$(mountpoint -q /mnt/fsx && speed /mnt/fsx/vault || echo n/a)
res RC7 MEASURED "plain btrfs: $p | LUKS2 vault file: $v | fscrypt ext4 loop: $f"
bye
