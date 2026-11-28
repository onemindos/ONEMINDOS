#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Run only in a disposable privileged Debian container on a Linux build worker.
set -eu
test -f /.dockerenv
test ! -e /data

work=$(mktemp -d)
trap 'umount /data/storage 2>/dev/null || true; umount /data 2>/dev/null || true; rm -rf "$work"' EXIT
mkdir /data
truncate -s 512M "$work/data.img"
mkfs.btrfs -q "$work/data.img"
mount -o loop "$work/data.img" /data
btrfs subvolume create /data/@
btrfs subvolume create /data/@storage
btrfs subvolume set-default /data/@
umount /data
mount -o loop "$work/data.img" /data
mkdir /data/storage
device=$(findmnt -no SOURCE /data | cut -d '[' -f 1)
mount -o subvol=@storage "$device" /data/storage
btrfs subvolume create /data/storage/.snapshots
install -D -m 0644 os/rootfs/layers/base/etc/snapper/configs/storage /etc/snapper/configs/storage
install -D -m 0755 os/rootfs/layers/base/usr/lib/snapper/plugins/50-onemind-files /usr/lib/snapper/plugins/50-onemind-files
install -m 0644 os/rootfs/layers/base/etc/default/snapper /etc/default/snapper
mkdir -p /run/dbus
dbus-uuidgen --ensure
dbus-daemon --system --fork
groupadd --gid 961 onemind
useradd --uid 961 --gid 961 --no-create-home onemind
install -d -o onemind -g onemind -m 0750 /data/onemind/files
install -o onemind -g onemind -m 0640 /dev/null /data/onemind/files/migrate.txt
printf '%s\n' 'a legacy Files entry' > /data/onemind/files/migrate.txt
ln /data/onemind/files/migrate.txt /data/onemind/files/migrate-link.txt

repo=$PWD
cd core
export UV_PROJECT_ENVIRONMENT="$work/venv"
export PYTHONPATH="$repo/os/rootfs/layers/onemind/usr/lib/onemind:$repo/core"
uv run --frozen python - <<'PY'
from onemind_firstboot import Paths, ensure_files_root

ensure_files_root(Paths())
ensure_files_root(Paths())
PY
test "$(stat -c '%a %u %g %h' /data/onemind/files/migrate.txt)" = "640 961 961 2"
test ! -e /data/onemind/files.snapshot-stage
test ! -e /data/storage/files
test -z "$(findmnt --mountpoint /data/onemind/files)"

# Only the original live path is available to the old slot. Keep both an edit
# to an existing entry and a new entry written while running its layout.
umount /data/storage
umount /data
mount -o loop "$work/data.img" /data
chmod 0750 /data/onemind/files
chown onemind:onemind /data/onemind/files
runuser -u onemind -- sh -ec '
    cd /data/onemind/files
    test "$(cat migrate.txt)" = "a legacy Files entry"
    printf "%s\n" "edited on rollback" > migrate.txt
    printf "%s\n" "created on rollback" > rollback.txt
'
umount /data
mount -o loop "$work/data.img" /data
device=$(findmnt -no SOURCE /data | cut -d '[' -f 1)
mount -o subvol=@storage "$device" /data/storage
uv run --frozen python -c 'from onemind_firstboot import Paths, ensure_files_root; ensure_files_root(Paths())'
test "$(cat /data/onemind/files/migrate-link.txt)" = "edited on rollback"
test "$(cat /data/onemind/files/rollback.txt)" = "created on rollback"
ONEMIND_TEST_SNAPPER_TIMELINE=1 uv run --frozen pytest -q -o "cache_dir=$work/pytest-cache" tests/test_files_versions.py -k household_sessions
snapper --no-dbus --utc --iso --jsonout -c storage list --columns number,type,date,cleanup,read-only
if [ -x /tmp/onemind ]; then
    /tmp/onemind snapshots --json
fi
snapper -c storage delete 1
test -z "$(ls -A /data/storage/.snapshots/.files)"
