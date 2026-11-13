#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Board rpi5: desk pre-flight of the LT-PI5-01 test disk (brief 30 D-B2.2 "F-PI5 desk pre-flight"),
# the pipeline version of research-output/evidence/lab/rauc-1152/scripts/pi5/desk-preflight.sh.
# Run as root in a DISPOSABLE Linux VM (loop devices, chroot); never on a Pi or the Mac. It cannot
# test the Pi firmware; it checks everything around it, on a copy of the fixture disk:
#  P-c  the device's own RAUC and policy refuse wrong-key and plain-good, and accept good (verity)
#  P-d  a real `rauc install good.raucb` from slot A writes boot B (p3) + root B (p6), runs the
#       pre-install handler (trial marker) and arms the one-shot "0 tryboot"; autoboot.txt unchanged
#  P-e  the gate's commit path on the real FAT: with a faked device tree (booted p3 via tryboot)
#       `rauc status mark-good booted` swaps autoboot.txt to B, and the swap is ON THE MEDIUM when it
#       returns (an O_DIRECT copy of p1 is clean); a later mark-bad of A removes its marker
#   sudo bash desk-check.sh <fixtures-dir>        # out/fx-rpi5 from `make fixtures BOARD=rpi5 UPTO=T10 HW=1`
set -euo pipefail
FX=$(cd "${1:?usage: desk-check.sh <fixtures-dir>}" && pwd)
W=$(mktemp -d /var/tmp/rpi5-desk.XXXXXX); C=$W/root; L=""; BL=""
say() { echo "DESK $*"; }
fail() { echo "DESK FAIL: $*"; exit 1; }
inroot() { for p in /proc/[0-9]*; do [ "$(readlink "$p/root" 2>/dev/null)" = "$C" ] && echo "${p#/proc/}"; done; }
stop() { for p in $(inroot); do grep -qa -- "$1" "/proc/$p/cmdline" 2>/dev/null && kill "$p"; done; sleep 1; }   # only the chroot's
cleanup() { set +e; stop "rauc"; stop "dbus-daemon"
  for m in "$C/run/onemind-test" "$C/run" "$C/tmp" "$C/dev" "$C/sys" "$C/proc" "$C/etc/machine-id" "$C/boot/efi" "$C/data" "$C"; do umount -l "$m" 2>/dev/null; done
  [ -n "$L" ] && losetup -d "$L"; [ -n "$BL" ] && losetup -d "$BL"; rm -rf "$W"; }
trap cleanup EXIT
cp --sparse=always "$FX/disk.img" "$W/disk.img"
L=$(losetup -fP --show "$W/disk.img"); BL=$(losetup -f --show -r "$FX/bundles.img"); udevadm settle
[ -e /dev/disk/by-partuuid/4f4d5035-06 ] || fail "by-partuuid links missing (another disk with id 4f4d5035 attached?)"
mkdir -p "$C"; mount -o ro "${L}p5" "$C"                     # read-only root, as on the device
mount "${L}p7" "$C/data"; mount "${L}p1" "$C/boot/efi"
mount -t proc proc "$C/proc"; mount -t sysfs sys "$C/sys"; mount --rbind /dev "$C/dev"
mount -t tmpfs tmpfs "$C/run"; mount -t tmpfs tmpfs "$C/tmp"
tr -d '-' < /proc/sys/kernel/random/uuid > "$W/machine-id"; mount --bind "$W/machine-id" "$C/etc/machine-id"
mkdir -p "$C/run/onemind-test" "$C/run/dbus"; mount -o ro "$BL" "$C/run/onemind-test"
ch() { chroot "$C" "$@"; }
AB0=$(tr '\n' ' ' < "$C/boot/efi/autoboot.txt")
say "slot A: $(ch /usr/bin/rauc --version), $(. "$C/usr/lib/os-release"; echo "version $ONEMIND_VERSION board $ONEMIND_BOARD")"
say "autoboot.txt: $AB0 markers: $(cd "$C/boot/efi" && echo slot-*.good)"

say "P-c device policy (rauc info under the device's system.conf and keyring)"
for b in good wrong-key plain-good; do
  if out=$(ch rauc --conf=/etc/rauc/system.conf info "/run/onemind-test/bundles/$b.raucb" 2>&1); then r=ACCEPTED; else r=REFUSED; fi
  say "  $b: $r ($(echo "$out" | grep -v '^ *[0-9]*%' | tail -n1 | cut -c1-120))"
  case "$b:$r" in good:ACCEPTED|wrong-key:REFUSED|plain-good:REFUSED) ;; *) fail "P-c $b $r" ;; esac
done

say "P-d rauc install good.raucb from slot A (RAUC D-Bus service in the chroot started as rauc.service does, booted slot forced to A)"
ch dbus-daemon --system --fork
ch sh -c 'mkdir -p /run/rauc/mnt; rauc --mount=/run/rauc/mnt service --override-boot-slot=A > /run/rauc-service.log 2>&1 &'
for _ in $(seq 20); do ch rauc status >/dev/null 2>&1 && break; sleep 1; done
ch rauc status | grep -E 'Booted from|Activated' | sed 's/^/DESK   /'
ch rauc install /run/onemind-test/bundles/good.raucb 2>&1 | grep -v '^ *[0-9]*%' | tail -4 | sed 's/^/DESK   /'
pend=$(cat "$C/data/onemind/pending" 2>/dev/null || echo none); param=$(cat "$C/run/systemd/reboot-param" 2>/dev/null || echo none)
say "  pending marker: $pend; reboot-param: $param"
[ "$pend" = "B 2" ] || fail "trial marker"; [ "$param" = "0 tryboot" ] || fail "tryboot not armed"
[ "$(tr '\n' ' ' < "$C/boot/efi/autoboot.txt")" = "$AB0" ] || fail "install changed autoboot.txt"
say "  autoboot.txt unchanged by the install: yes"
mkdir -p "$W/b"; mount -o ro "${L}p6" "$W/b"; rv=$(. "$W/b/usr/lib/os-release"; echo "$ONEMIND_VERSION"); umount "$W/b"
mount -o ro "${L}p3" "$W/b"; nb=$(ls "$W/b" | wc -l); cb=$(cat "$W/b/cmdline_b.txt"); umount "$W/b"
say "  root B: version $rv; boot B: $nb entries, cmdline_b: $cb"
[ "$rv" = 2 ] && [ "$nb" -gt 10 ] && echo "$cb" | grep -q 'root=PARTUUID=4f4d5035-06 .*rauc.slot=B' || fail "slot B content"
[ "$(ch /usr/lib/onemind/rpi-tryboot-ab.sh get-primary)" = B ] || fail "get-primary after install"

say "P-e commit on the real FAT with a faked device tree (the trial boot: tryboot=1, partition=3)"
stop "rauc"; rm -f "$C/run/systemd/reboot-param"      # /run is empty after the reboot
mkdir -p "$C/run/fakedt"; printf '\0\0\0\1' > "$C/run/fakedt/tryboot"; printf '\0\0\0\3' > "$C/run/fakedt/partition"
ch sh -c 'ONEMIND_DT=/run/fakedt rauc --mount=/run/rauc/mnt service --override-boot-slot=B > /run/rauc-service.log 2>&1 &'
for _ in $(seq 20); do ch rauc status >/dev/null 2>&1 && break; sleep 1; done
ch rauc status mark-good booted 2>&1 | tail -n1 | sed 's/^/DESK   /'
# What a power cut right now would leave: p1 as the loop device has written it to its backing file
# (the "medium"; dirty filesystem buffers not yet written are not in it). p1 = MiB 1..65 (layout.yaml).
dd if="$W/disk.img" of="$W/p1.img" bs=1M skip=1 count=64 status=none
fo=$(fsck.vfat -n "$W/p1.img" 2>&1 || true)
mkdir -p "$W/m"; mount -o ro,loop "$W/p1.img" "$W/m"; mf=$(tr '\n' ' ' < "$W/m/autoboot.txt" 2>&1 || true); umount "$W/m"
say "  on the medium after mark-good returned: autoboot.txt = $mf"
echo "$fo" | grep -E 'Truncating|chain|Reclaimed|Orphan' | sed 's/^/DESK   fsck (medium): /' || true
[ "$mf" = "[all] tryboot_a_b=1 boot_partition=3 [tryboot] boot_partition=2 " ] || fail "commit not on the medium (power cut would lose it)"
echo "$fo" | grep -qE 'Truncating|chain length|Reclaimed' && fail "autoboot partition inconsistent on the medium after commit"
ab=$(tr '\n' ' ' < "$C/boot/efi/autoboot.txt"); say "  autoboot.txt now: $ab markers: $(cd "$C/boot/efi" && echo slot-*.good)"
echo "$ab" | grep -q '\[all\] tryboot_a_b=1 boot_partition=3 \[tryboot\] boot_partition=2' || fail "commit did not swap autoboot.txt"
ch rauc status mark-bad other 2>&1 | tail -n1 | sed 's/^/DESK   /'
[ ! -e "$C/boot/efi/slot-A.good" ] && [ -e "$C/boot/efi/slot-B.good" ] || fail "markers after mark-bad other"
say "PASS (P-c, P-d, P-e)"
