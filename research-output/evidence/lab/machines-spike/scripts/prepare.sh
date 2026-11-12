#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike: guest inputs shared by A and B (SSH key, user-data, NoCloud seed), the
# pre-registered guest-agent check on the image, and the two local HTTP servers. Root, lab VM only.
set -euo pipefail; source "$(dirname "$0")/common.sh"
exec > >(tee -a "$OUT/prepare.log") 2>&1
mkdir -p $W/ssh $W/seed
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N '' -C machlab -f "$KEY"
PUB=$(cat "$KEY.pub")
sed "s|@PUBKEY@|$PUB|" "$S/user-data.yaml" > $W/user-data.yaml
echo "== guest-agent check on the image (read-only)"
qemu-img info $W/img/fedora.qcow2 | grep -E 'file format|virtual size'
qemu-img convert -O raw $W/img/fedora.qcow2 $W/probe.img
L=$(losetup -r -f -P --show $W/probe.img); sleep 1; lsblk -o NAME,SIZE,FSTYPE,LABEL "$L"
P=$(lsblk -b -rno NAME,SIZE,FSTYPE "$L" | awk '$3~/^(btrfs|ext4|xfs)$/' | sort -k2 -n | tail -1 | cut -d' ' -f1); mkdir -p $W/probe
mount -o ro "/dev/$P" $W/probe; echo "root fs $(blkid -o value -s TYPE "/dev/$P"), top level: $(ls $W/probe | tr '\n' ' ')"
QGA=$(find $W/probe -maxdepth 4 -path '*/usr/bin/qemu-ga' 2>/dev/null | head -1)
UNIT=$(find $W/probe -maxdepth 7 -name 'qemu-guest-agent.service' 2>/dev/null | head -1)
if [ -n "$QGA" ]; then echo "qemu-guest-agent PRESENT in image (${QGA#$W/probe/}, unit ${UNIT#$W/probe/})"
else echo "qemu-guest-agent ABSENT: adding packages: [qemu-guest-agent] to the user-data for both options"
  printf 'packages: [qemu-guest-agent]\nruncmd: [[systemctl, enable, --now, qemu-guest-agent]]\n' >> $W/user-data.yaml; fi
umount $W/probe 2>/dev/null || true; losetup -d "$L"; rm -f $W/probe.img
cloud-localds $W/seed/seed.iso $W/user-data.yaml
sed 's/ssh-ed25519 [A-Za-z0-9+\/=]*/ssh-ed25519 <generated-at-run-time>/' $W/user-data.yaml > "$OUT/user-data.masked.yaml"
echo "== local servers"
NODEIP=$(ip -4 -o addr show cni0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
[ -n "$NODEIP" ] || NODEIP=$(ip -4 -o route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
echo "$NODEIP" > $W/nodeip
systemctl is-active --quiet machlab-img || systemd-run --unit machlab-img python3 -m http.server 8099 --bind 0.0.0.0 --directory $W/img
systemctl is-active --quiet machlab-www || systemd-run --unit machlab-www python3 -m http.server 8080 --bind 127.0.0.1 --directory $W/www
sleep 2; curl -fsI "http://$NODEIP:8099/fedora.qcow2" | head -1; curl -fsI http://127.0.0.1:8080/console.html | head -1
