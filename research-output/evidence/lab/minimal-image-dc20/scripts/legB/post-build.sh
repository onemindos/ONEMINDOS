#!/bin/sh
# Like board/pc/post-build.sh (EFI branch) but with a serial console.
set -e
mkdir -p "$BINARIES_DIR/efi-part/EFI/BOOT"
cat > "$BINARIES_DIR/efi-part/EFI/BOOT/grub.cfg" <<'G'
set default="0"
set timeout="1"
menuentry "OneMind DC20 Buildroot" {
 linux /bzImage root=PARTUUID=UUID_TMP rootwait console=ttyS0,115200 console=tty1
}
G
