#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs on the Proxmox host as root (CI-14): build the job VM template from the pinned Ubuntu 24.04
# cloud image. Boot it once on vmbr1, install the guest agent with cloud-init, push the kit in through
# the agent, run provision.sh, power off, and turn it into a template. Every job is a linked clone.
#   template.sh            uses /etc/onemind-ci-kvm.env (TEMPLATE_ID, STORAGE, SNIPPETS, CI_NET, CI_BRIDGE)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
. "$here/runner.pin"
[ -f /etc/onemind-ci-kvm.env ] && . /etc/onemind-ci-kvm.env
TID=${TEMPLATE_ID:-9100}; ST=${STORAGE:-local-lvm}; SN=${SNIPPETS:-local}
BR=${CI_BRIDGE:-vmbr1}; NET=${CI_NET:-10.10.0}; DISK=${DISK_GB:-150}
for c in qm pvesm curl sha256sum tar; do command -v "$c" >/dev/null || { echo "missing: $c" >&2; exit 2; }; done
if qm status "$TID" >/dev/null 2>&1; then echo "VM $TID exists; remove it first (down --wipe)" >&2; exit 1; fi

img=/var/tmp/onemind-ci-kvm/$(basename "$UBUNTU_IMAGE_URL")
mkdir -p "$(dirname "$img")"
if ! echo "$UBUNTU_IMAGE_SHA256  $img" | sha256sum -c - >/dev/null 2>&1; then
  curl -fsSL -o "$img" "$UBUNTU_IMAGE_URL"
  echo "$UBUNTU_IMAGE_SHA256  $img" | sha256sum -c -
fi

# First boot only: install and start the guest agent (the host talks to the VM through it, never SSH).
snip_dir=$(pvesm path "$SN:snippets/x" | sed 's|/x$||')
mkdir -p "$snip_dir"
cat > "$snip_dir/onemind-ci-template.yaml" <<'YAML'
#cloud-config
package_update: true
packages: [qemu-guest-agent]
runcmd:
  - [systemctl, start, qemu-guest-agent]
YAML

qm create "$TID" --name onemind-kvm-template --ostype l26 --machine q35 --cpu host --cores 4 --memory 8192 \
  --scsihw virtio-scsi-single --scsi0 "$ST:0,import-from=$img,discard=on" --boot order=scsi0 \
  --ide2 "$ST:cloudinit" --net0 "virtio,bridge=$BR" --serial0 socket --vga serial0 --agent 1 \
  --ipconfig0 "ip=$NET.9/24,gw=$NET.1" --nameserver "1.1.1.1 9.9.9.9" \
  --cicustom "user=$SN:snippets/onemind-ci-template.yaml" \
  --description "OneMind CI x86/KVM job template (scripts/ci-runner-kvm, CI-14). Clones only; never started by hand."
qm resize "$TID" scsi0 "${DISK}G"
qm start "$TID"

echo "waiting for the guest agent (cloud-init installs it; a few minutes)"
i=0; until qm agent "$TID" ping >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -le 90 ] || { echo "no guest agent after 15 min" >&2; qm stop "$TID"; exit 1; }; sleep 10
done
qm guest exec "$TID" --timeout 900 -- cloud-init status --wait >/dev/null || true
tar -C "$here" -cf - provision.sh run-one.sh runner.pin |
  qm guest exec "$TID" --pass-stdin 1 -- sh -c 'mkdir -p /opt/onemind-ci && tar -xf - -C /opt/onemind-ci' >/dev/null
out=$(qm guest exec "$TID" --timeout 0 -- sh /opt/onemind-ci/provision.sh)
echo "$out" | grep -q '"exitcode" : 0' || { echo "$out" >&2; echo "provision failed" >&2; exit 1; }
echo "$out" | sed -n 's/.*"out-data" : "\(provisioned[^"\\]*\).*/\1/p'

qm shutdown "$TID" --timeout 120 || qm stop "$TID"
qm set "$TID" --delete cicustom --ipconfig0 "ip=$NET.9/24,gw=$NET.1" >/dev/null
rm -f "$snip_dir/onemind-ci-template.yaml"
qm template "$TID"
echo "template $TID ready"
