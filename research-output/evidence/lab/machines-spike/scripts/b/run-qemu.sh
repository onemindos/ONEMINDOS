#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike option B entrypoint: one QEMU per pod. Disk, UEFI vars and seed come from volumes;
# VNC is offered as a WebSocket (port 5700), the guest agent on a unix socket, serial to a file.
set -eu
ACCEL=${ACCEL:-kvm}; MEM=${MEM:-1024}; SMP=${SMP:-2}
if [ "$ACCEL" = kvm ]; then MACH=virt,gic-version=host; CPU=host; else MACH=virt,gic-version=max; CPU=max; fi
mkdir -p /run/vm
exec qemu-system-aarch64 -name "${VM_NAME:-vm-b}" -nodefaults -machine "$MACH" -accel "$ACCEL" -cpu "$CPU" \
  -smp "$SMP" -m "$MEM" \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/AAVMF/AAVMF_CODE.fd \
  -drive if=pflash,format=raw,file=/disk/vars.fd \
  -drive if=none,id=d0,file=/disk/disk.img,format=raw,cache=none,aio=threads \
  -device virtio-blk-pci,drive=d0,bootindex=0 \
  -drive if=none,id=ci,file=/seed/seed.iso,format=raw,readonly=on -device virtio-blk-pci,drive=ci \
  -netdev user,id=n0,hostfwd=tcp::2222-:22 -device virtio-net-pci,netdev=n0,romfile= \
  -device virtio-gpu-pci -device qemu-xhci -device usb-kbd -device usb-tablet \
  -vnc 0.0.0.0:0,websocket=on \
  -chardev socket,id=qga0,path=/run/vm/qga.sock,server=on,wait=off \
  -device virtio-serial-pci -device virtserialport,chardev=qga0,name=org.qemu.guest_agent.0 \
  -chardev file,id=ser0,path=/run/vm/serial.log -serial chardev:ser0 \
  -qmp unix:/run/vm/qmp.sock,server=on,wait=off
