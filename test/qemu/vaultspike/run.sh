#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Personal vault spike (gateway permissions design 25g, CRITERIA-RECOVERY-VAULT.md RC0-RC7). Not product code.
#
# usage: test/qemu/vaultspike/run.sh [--naive] <out-dir>
#
# Needs Docker and a writable /dev/kvm on a Linux host (no root on the host). Inside a debian:13 container it
# builds a minimal Debian 13 root with debootstrap (network needed once), boots it twice under QEMU/KVM on the
# Debian 13 kernel with a blank 4 GiB data disk (btrfs, the stand-in for the box's /data), and writes the
# guest's RESULT lines to <out-dir>/results.json. The vault and recovery keys are made here, outside the guest,
# and reach it only through QEMU fw_cfg.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
mode=normal
if [ "${1:-}" = "--naive" ]; then mode=naive; shift; fi
out=${1:?usage: run.sh [--naive] <out-dir>}
mkdir -p "$out"
out=$(cd "$out" && pwd)
test -w /dev/kvm || { echo "vaultspike: BLOCKED: /dev/kvm is not writable" >&2; exit 75; }
docker run --rm --device /dev/kvm -v "$here":/spike:ro -v "$out":/out -e MODE="$mode" debian:13 bash /spike/inside.sh
