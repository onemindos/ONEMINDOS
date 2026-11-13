#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Local first-boot check (F0-F4, test/qemu/CRITERIA-FIRSTBOOT.md) on a Linux box with Docker and /dev/kvm,
# e.g. WSL2 Debian on a Windows PC. Same steps as the image workflow's smoke job: build the x86_64-efi
# rootfs and tools image, make the fixtures, run `make firstboot` under KVM. Criteria are not touched.
#
#   test/qemu/local-firstboot.sh [BOARD=x86_64-efi] [FUPTO=F4]      (run from a clone on the Linux filesystem)
#
# How-to: test/qemu/README.md "Local first boot". Logs: out/firstboot-<board>/{serial.log,results.json}.
set -euo pipefail
cd "$(dirname "$0")/../.."
BOARD=x86_64-efi; FUPTO=F4
for a in "$@"; do case "$a" in BOARD=*) BOARD=${a#BOARD=};; FUPTO=*) FUPTO=${a#FUPTO=};; *) echo "unknown argument $a" >&2; exit 2;; esac; done

die() { echo "local-firstboot: $*" >&2; exit 1; }
command -v docker >/dev/null || die "docker not found (WSL: sudo apt install docker.io, start it with 'service docker start')"
docker info >/dev/null 2>&1 || die "docker daemon not running (WSL: service docker start)"
command -v make >/dev/null || die "make not found"
[ -w /dev/kvm ] || die "/dev/kvm is not writable: without KVM the boot runs under TCG and is far too slow (WSL: enable nestedVirtualization in .wslconfig)"
case "$PWD" in /mnt/*) die "work in a clone on the Linux filesystem, not under /mnt (CRLF line endings break the scripts)";; esac
if grep -rIl $'\r' os/assemble test/qemu/*.sh >/dev/null 2>&1; then die "CRLF line endings in the checkout; clone inside WSL instead"; fi

t0=$SECONDS
rm -rf "out/fx-$BOARD" "out/firstboot-$BOARD"
make fixtures BOARD="$BOARD" UPTO=T5
echo "== fixtures ready after $((SECONDS - t0)) s; booting under KVM =="
rc=0
make firstboot BOARD="$BOARD" FUPTO="$FUPTO" || rc=$?
echo "== first boot finished rc=$rc after $((SECONDS - t0)) s =="
[ -f "out/firstboot-$BOARD/results.json" ] && python3 -I test/qemu/summary.py "out/firstboot-$BOARD/results.json" || true
echo "serial log: out/firstboot-$BOARD/serial.log"
exit "$rc"
