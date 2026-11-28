#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# rpi5 rootfs step, run inside the Containerfile after the board's files are copied and before the
# initramfs is built. Debian 13 arm64 userspace + Raspberry Pi's kernel (brief 30 B2, rpi5 row).
set -eu
B=$(dirname "$0"); D=/tmp/onemind/rpi-debs
sh "$B/fetch-rpi.sh" "$D"
# Debian's arm64 kernel and GRUB EFI come from the common arm64 list; the Pi firmware boots neither.
old=$(dpkg-query -W -f '${Package}\n' 'linux-image-*' 'grub-efi-arm64*' 2>/dev/null | grep -E -- '-arm64$|^grub-efi-arm64' || true)
[ -z "$old" ] || apt-get purge -y $old >/dev/null
# linux-base-<ver> before linux-image-<ver>; each kernel's postinst builds its initramfs.
dpkg -i "$D"/linux-base-*.deb
dpkg -i "$D"/linux-image-*.deb
rm -rf "$D"
for k in 2712 v8; do ls /boot/vmlinuz-*-rpi-$k /boot/initrd.img-*-rpi-$k >/dev/null; done
for m in /lib/modules/*; do case ${m##*/} in *-rpi-*) ;; *) echo "ERROR: non-Raspberry-Pi kernel ${m##*/} left" >&2; exit 1 ;; esac; done
systemctl enable onemind-rpi5-grow.service onemind-rpi5-eeprom-check.service >/dev/null
# Audio and Bluetooth for the box's own screen (Step 3): bluez comes from packages-debian.txt; bluetooth.service is wanted by
# multi-user.target so bluetoothd runs before an adapter shows up (Debian only starts it when udev finds one).
test -x /usr/libexec/bluetooth/bluetoothd
test -x /usr/bin/pipewire && test -x /usr/bin/wireplumber && test -x /usr/bin/pipewire-pulse
# The kiosk (on by default): without these the box's monitor falls back to the text screen.
test -x /usr/bin/cage && test -x /usr/bin/chromium
systemctl add-wants multi-user.target bluetooth.service
echo "rpi5: kernels $(ls /lib/modules | tr '\n' ' ')"
