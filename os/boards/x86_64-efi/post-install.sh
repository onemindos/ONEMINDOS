#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# x86_64-efi rootfs step, run inside the Containerfile after the board's files are copied (Step 3, audio and
# Bluetooth for the box's own screen; rpi5 does the same in its post-install.sh). bluez itself comes from
# packages-debian.txt. bluetooth.service is wanted by multi-user.target here, so bluetoothd runs even before an
# adapter shows up (Debian only starts it when udev finds one). Cloud boards have no such step: no bluez, no unit.
set -eu
# Only the Debian leg installs these packages (packages-debian.txt). The Ubuntu hedge builds this same board with
# packages-ubuntu.txt, which carries only the VA-API drivers, so it gets no audio or Bluetooth and must not fail below.
[ "${LEG:-debian}" = debian ] || { echo "x86_64-efi: leg ${LEG} has no audio or Bluetooth packages, skipped"; exit 0; }
test -x /usr/libexec/bluetooth/bluetoothd
test -x /usr/bin/pipewire && test -x /usr/bin/wireplumber && test -x /usr/bin/pipewire-pulse
test -f /usr/share/pipewire/pipewire.conf.d/50-onemind-stream-sink.conf
systemctl add-wants multi-user.target bluetooth.service
test -L /etc/systemd/system/multi-user.target.wants/bluetooth.service
