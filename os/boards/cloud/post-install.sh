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
echo "cloud: cloud layer installed (cloud-init $(dpkg-query -W -f='${Version}' cloud-init))"
