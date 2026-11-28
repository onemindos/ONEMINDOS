#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# cloud rootfs step, run inside the Containerfile after its files are copied.
# The admin user is "admin": "onemind" is already the gateway's system user (Containerfile).
set -eu
rm -f /etc/ssh/ssh_host_*                      # never ship shared host keys
useradd --create-home --shell /bin/bash --comment "OneMind admin" admin
passwd -l admin >/dev/null                     # key-only login
chmod 0440 /etc/sudoers.d/admin
mkdir -p /var/lib/cloud /var/lib/dhcpcd /var/lib/waagent   # mountpoints: the root is read-only at boot
systemctl enable ssh.service etc-systemd-network.mount var-lib-cloud.mount var-lib-dhcpcd.mount \
  var-lib-waagent.mount onemind-data-grow.service >/dev/null
# No printing on a cloud server (Step 3): the common layer enables CUPS, and host.nft opens 631 from the private ranges,
# which here are the provider's network. Mask the units (a symlink to /dev/null that no enable can undo) so nothing listens.
systemctl mask cups.service cups.socket cups.path ipp-usb.service >/dev/null
for u in cups.service cups.socket cups.path ipp-usb.service; do
  [ "$(readlink /etc/systemd/system/$u)" = /dev/null ] || { echo "ERROR: $u is not masked" >&2; exit 1; }
done
echo "cloud: cloud layer installed (cloud-init $(dpkg-query -W -f='${Version}' cloud-init))"
