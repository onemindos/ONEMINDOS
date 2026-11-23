#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# #718 acceptance: real Samba and NFS (NFS-Ganesha) servers in a throwaway privileged Debian 13
# container, the netmount engine mounting both from inside it, a killed and
# restarted smbd. Linux with Docker only (it loads the cifs and nfs kernel
# modules, so run it on a test machine, never on a hub).
#   sh internal/storage/netmount/testdata/acceptance.sh
set -eu
repo=$(cd "$(dirname "$0")/../../../.." && pwd)
bin=$(mktemp -d)
trap 'rm -rf "$bin"' EXIT
(cd "$repo" && CGO_ENABLED=0 go test -c -tags netmount_acceptance -o "$bin/netmount.test" ./internal/storage/netmount)
docker run --rm --privileged --tmpfs /run -v /lib/modules:/lib/modules:ro -v "$bin":/t:ro debian:trixie bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends samba cifs-utils nfs-ganesha nfs-ganesha-vfs rpcbind nfs-common e2fsprogs kmod procps >/dev/null
modprobe cifs; modprobe nfs; modprobe nfsv4
pw=$(head -c 18 /dev/urandom | od -An -tx1 | tr -d " \n")
useradd -M nasuser
printf "%s\n%s\n" "$pw" "$pw" | smbpasswd -s -a nasuser >/dev/null
mkdir -p /srv/family /srv/nfs /run/samba /var/log/samba
truncate -s 64M /tmp/nfs.img && mkfs.ext4 -q /tmp/nfs.img   # the container overlay cannot be exported
mount -o loop /tmp/nfs.img /srv/nfs
mkdir -p /srv/nfs/photos && chown nasuser /srv/family && echo hi > /srv/nfs/photos/a.txt
cat > /etc/samba/smb.conf <<CONF
[global]
  map to guest = never
  restrict anonymous = 2
[family]
  path = /srv/family
  read only = no
  valid users = nasuser
CONF
start_smbd() { smbd -D; for _ in $(seq 1 50); do (exec 3<>/dev/tcp/127.0.0.1/445) 2>/dev/null && return 0; sleep 0.2; done; echo "smbd did not start" >&2; return 1; }
start_smbd
# NFS: NFS-Ganesha (user space; the kernel server cannot see the folders of a container), v4 only.
cat > /etc/ganesha/ganesha.conf <<CONF
NFS_CORE_PARAM { Protocols = 4; }
NFSV4 { Grace_Period = 5; Lease_Lifetime = 5; }
EXPORT { Export_Id = 1; Path = /srv/nfs/photos; Pseudo = /srv/nfs/photos; Access_Type = RO;
  Squash = No_Root_Squash; Protocols = 4; Transports = TCP; SecType = sys; FSAL { Name = VFS; } }
CONF
mkdir -p /run/ganesha /var/lib/nfs/ganesha
rpcbind
ganesha.nfsd -L /tmp/ganesha.log -f /etc/ganesha/ganesha.conf
for _ in $(seq 1 50); do (exec 3<>/dev/tcp/127.0.0.1/2049) 2>/dev/null && break; sleep 0.2; done
sleep 6   # the v4 grace period of the server
ip=$(hostname -I | cut -d" " -f1)
NETMOUNT_IT_HOST=$ip NETMOUNT_IT_SMB_SHARE=family NETMOUNT_IT_SMB_USER=nasuser NETMOUNT_IT_SMB_PASSWORD=$pw \
NETMOUNT_IT_NFS_EXPORT=/srv/nfs/photos NETMOUNT_IT_STOP_SMB="pkill -x smbd; sleep 1" NETMOUNT_IT_START_SMB="smbd -D; sleep 2" \
  /t/netmount.test -test.run TestAcceptance -test.v -test.count=1
'
