#!/bin/bash
set -euo pipefail
GRUB_CFG="${RUGIX_LAYER_DIR}/roots/boot/grub.cfg"
case "${RUGIX_ARCH}" in
  amd64) ARGS="console=tty0 console=ttyS0,115200 panic=10" ;;
  arm64) ARGS="console=ttyAMA0,115200 panic=10" ;;
esac
sed -i "s|^linux /vmlinuz \${rugpi_bootargs}$|linux /vmlinuz \${rugpi_bootargs} ${ARGS}|" "${GRUB_CFG}"
grep '^linux ' "${GRUB_CFG}"
