#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Runs inside the debian:13 container (root there, not on the host): build the guest, boot it twice, collect.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends qemu-system-x86 debootstrap e2fsprogs ca-certificates python3 >/dev/null
root=/build/root
mkdir -p /build
debootstrap --variant=minbase \
  --include=linux-image-amd64,initramfs-tools,kmod,btrfs-progs,cryptsetup-bin,fscrypt,e2fsprogs,restic,xxd,util-linux,coreutils,procps \
  trixie "$root" http://deb.debian.org/debian >/build/debootstrap.log 2>&1 || { tail -30 /build/debootstrap.log; exit 1; }
install -m 0755 /spike/guest.sh "$root/vault-init.sh"
kver=$(ls "$root/lib/modules" | sort -V | tail -1)
echo "vaultspike: guest kernel $kver, mode $MODE"
truncate -s 3G /build/root.img
mkfs.ext4 -q -F -L vroot -d "$root" /build/root.img
truncate -s 4G /build/data.img
head -c 64 /dev/urandom > /build/vault.key
head -c 64 /dev/urandom > /build/recovery.key
boot() {  # boot <n>
  timeout 1500 qemu-system-x86_64 -machine q35,accel=kvm -cpu host -m 2048 -smp 2 -nographic -no-reboot \
    -kernel "$root/boot/vmlinuz-$kver" -initrd "$root/boot/initrd.img-$kver" \
    -append "root=/dev/vda rw console=ttyS0 panic=-1 init=/vault-init.sh vaultmode=$MODE" \
    -drive file=/build/root.img,if=virtio,format=raw -drive file=/build/data.img,if=virtio,format=raw \
    -fw_cfg name=opt/onemind/vaultkey,file=/build/vault.key -fw_cfg name=opt/onemind/recoverykey,file=/build/recovery.key \
    </dev/null >"/out/serial-$1.log" 2>&1 || true
}
boot 1
boot 2
python3 - "$MODE" <<'EOF'
import json, re, sys
results, measured = {}, {}
for n in (1, 2):
    for line in open(f"/out/serial-{n}.log", errors="replace"):
        m = re.match(r"RESULT (RC\d) (PASS|FAIL|BLOCKED|MEASURED) ?(.*)", line.strip())
        if m:
            results[m.group(1)] = {"verdict": m.group(2), "detail": m.group(3), "boot": n}
doc = {"mode": sys.argv[1], "results": dict(sorted(results.items()))}
json.dump(doc, open("/out/results.json", "w"), indent=2)
print(json.dumps(doc, indent=2))
EOF
