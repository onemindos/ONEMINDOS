#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# vm-do rootfs step, run inside the Containerfile after its files are copied (BD-DO-1).
set -eu
rm -f /etc/ssh/ssh_host_*                      # never ship shared host keys
useradd --create-home --shell /bin/bash --comment "OneMind admin" onemind
passwd -l onemind >/dev/null                   # key-only login
chmod 0440 /etc/sudoers.d/onemind
mkdir -p /var/lib/cloud                       # mountpoint for var-lib-cloud.mount: the root is read-only at boot
systemctl enable ssh.service etc-systemd-network.mount var-lib-cloud.mount onemind-data-grow.service >/dev/null
echo "vm-do: cloud layer installed (cloud-init $(dpkg-query -W -f='${Version}' cloud-init))"
