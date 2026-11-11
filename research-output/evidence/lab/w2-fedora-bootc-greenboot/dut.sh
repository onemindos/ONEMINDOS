#!/bin/bash
# Device-under-test helpers (run as root in the lab VM). usage: dut.sh boot|kill|ssh <cmd>|wait
W=/root/w2; cd $W
case "$1" in
 boot)
  [ -f vars.fd ] || cp /usr/share/edk2/aarch64/QEMU_EFI-qemuvars-pflash.raw vars.fd 2>/dev/null || truncate -s 64M vars.fd
  [ -f dut.qcow2 ] || { cp out/qcow2/disk.qcow2 dut.qcow2; qemu-img resize dut.qcow2 20G; }
  qemu-system-aarch64 -M virt -accel kvm -cpu host -smp 4 -m 4096 \
   -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/aarch64/QEMU_EFI-pflash.raw \
   -drive if=pflash,format=raw,file=vars.fd \
   -drive file=dut.qcow2,if=virtio,format=qcow2,cache=writeback \
   -netdev user,id=n0,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-net-pci,netdev=n0 \
   -display none -serial file:serial-$(date +%s).log -monitor none -pidfile dut.pid -daemonize ;;
 kill) kill -9 $(cat dut.pid) ;;
 ssh) shift; ssh -q -i labkey -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 lab@127.0.0.1 "$@" ;;
 wait) for i in $(seq 1 ${2:-120}); do $0 ssh true && exit 0; sleep 5; done; exit 1 ;;
esac
