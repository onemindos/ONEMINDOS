#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Run only in a disposable privileged Debian container on a Linux build worker.
set -eu
test -f /.dockerenv
test ! -e /data

work=$(mktemp -d)
trap 'umount /data/onemind/files 2>/dev/null || true; umount /data/storage 2>/dev/null || true; umount /data 2>/dev/null || true; rm -rf "$work"' EXIT
mkdir /data
truncate -s 512M "$work/data.img"
mkfs.btrfs -q "$work/data.img"
mount -o loop "$work/data.img" /data
btrfs subvolume create /data/@storage
mkdir /data/storage
mount -o subvol=@storage "$(findmnt -no SOURCE /data)" /data/storage
btrfs subvolume create /data/storage/.snapshots
install -D -m 0644 os/rootfs/layers/base/etc/snapper/configs/storage /etc/snapper/configs/storage
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
PYTHONPATH="$repo/os/rootfs/layers/onemind/usr/lib/onemind:$repo/core" uv run --frozen python - <<'PY'
from onemind_firstboot import Paths, ensure_files_root

ensure_files_root(Paths())
ensure_files_root(Paths())
PY
test "$(stat -c '%a %u %g %h' /data/storage/files/migrate.txt)" = "640 961 961 2"
cmp /data/onemind/files/migrate.txt /data/storage/files/migrate.txt
test ! -e /data/onemind/files.before-snapper
ONEMIND_TEST_SNAPPER_TIMELINE=1 uv run --frozen pytest -q -o "cache_dir=$work/pytest-cache" tests/test_files_versions.py -k household_sessions
snapper --no-dbus --utc --iso --jsonout -c storage list --columns number,type,date,cleanup,read-only
if [ -x /tmp/onemind ]; then
    /tmp/onemind snapshots --json
fi
