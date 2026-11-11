#!/bin/bash
# Boots the bootc test disk in host QEMU (aarch64, HVF, UEFI). QEMU is only the hypervisor.
# Serial console -> $LAB/vm/serial.log (appended, so reboots stay in one file).
# SSH: 127.0.0.1:2222. Registry: guest sees the host's 127.0.0.1:5000 (Lima forward) at 198.18.0.2:5000.
# Usage: run-vm.sh start|stop|pid
set -euo pipefail
LAB=${LAB:-$HOME/<lab-dir>/fedora-bootc}
DISK=$LAB/vm/test.qcow2
FW=$(brew --prefix qemu)/share/qemu/edk2-aarch64-code.fd
case "${1:-start}" in
start)
  [ -f "$DISK" ] || { cp "$LAB/vm/disk-v1.qcow2" "$DISK"; qemu-img resize "$DISK" 20G; }
  [ -f "$LAB/vm/vars.fd" ] || dd if=/dev/zero of="$LAB/vm/vars.fd" bs=1m count=64 2>/dev/null
  qemu-system-aarch64 -machine virt -accel hvf -cpu host -smp 4 -m 4096 \
    -drive if=pflash,format=raw,readonly=on,file="$FW" \
    -drive if=pflash,format=raw,file="$LAB/vm/vars.fd" \
    -drive if=virtio,format=qcow2,file="$DISK",cache=writeback \
    -netdev user,id=n0,net=198.18.0.0/24,hostfwd=tcp:127.0.0.1:2222-:22 \
    -device virtio-net-pci,netdev=n0 \
    -device virtio-rng-pci \
    -display none -serial file:"$LAB/vm/serial-$(date +%s).log" \
    -pidfile "$LAB/vm/qemu.pid" -daemonize
  echo "started pid $(cat "$LAB/vm/qemu.pid")" ;;
stop) kill "$(cat "$LAB/vm/qemu.pid")" 2>/dev/null || true ;;
pid) cat "$LAB/vm/qemu.pid" ;;
esac
