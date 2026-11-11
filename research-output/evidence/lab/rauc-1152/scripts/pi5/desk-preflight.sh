#!/bin/bash
# LAB-rauc-1152: desk pre-flight of the Pi 5 kit, run as root INSIDE the
# disposable arm64 Lima VM (never on a Pi, never on the host). It cannot test
# the Pi firmware; it checks everything around it:
#  P-a  build-rauc-pi.sh builds 1.15.2 natively on Debian arm64
#  P-b  prepare-disk.sh, unchanged, builds the 7-partition disk from the
#       Raspberry Pi OS Lite image (loop devices stand in for the SSD)
#  P-c  the device's own RAUC (chroot into slot A) refuses plain-good and
#       wrong-key, and accepts good (verity) under its system.conf
#  P-d  a real `rauc install good.raucb` from slot A writes boot B + root B,
#       runs the pre-install handler, and arms "0 tryboot" through the backend
#  P-e  backend state machine with a faked device tree: commit from a tryboot
#       boot swaps autoboot.txt; a later bad mark and a non-tryboot boot do not
#   IMG=/var/lab/pi/img bash desk-preflight.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
IMG=${IMG:?}; P=/var/lab/pi; export RAUC_DEST=$P/rauc-dest KEYS=$P/keys DL=$P/dl
say(){ echo "PREFLIGHT $*"; }
cleanup(){ set +e; for m in "$C/run" "$C/mnt/autoboot" "$C/data" "$C/proc" "$C/sys" "$C/dev"; do umount -l "$m" 2>/dev/null; done
  umount "$C" "$P/src-root" "$P/src-boot" 2>/dev/null; losetup -d "$SL" "$TL" 2>/dev/null; }
C=$P/chroot; SL=""; TL=""; trap cleanup EXIT

if [ -z "${SKIP_PREPARE:-}" ]; then say "P-a build RAUC 1.15.2 natively"; B=$P/raucbuild bash "$HERE/build-rauc-pi.sh"; fi

SL=$(losetup -fP --show "$IMG"); mkdir -p "$P/src-root" "$P/src-boot" "$C"
mount -o ro "${SL}p2" "$P/src-root"; mount -o ro "${SL}p1" "$P/src-boot"
say "source: $(. "$P/src-root/etc/os-release"; echo "$PRETTY_NAME"), kernel files: $(ls "$P/src-boot" | grep -c kernel)"
if [ -z "${SKIP_PREPARE:-}" ]; then
  rm -f "$P/target.img"; truncate -s 64G "$P/target.img"; TL=$(losetup -fP --show "$P/target.img")
  say "P-b prepare-disk.sh on $TL"
  TARGET=$TL CONFIRM=$TL SRC_ROOT=$P/src-root SRC_BOOT=$P/src-boot bash "$HERE/prepare-disk.sh"
else TL=$(losetup -j "$P/target.img" | cut -d: -f1 | head -n1); [ -n "$TL" ] || TL=$(losetup -fP --show "$P/target.img"); say "P-b skipped (reusing prepared $TL)"; fi
udevadm settle; ls -l /dev/disk/by-partuuid | grep 4f4d4c31 | awk '{print $9, $11}' || true
findmnt -rn -o TARGET -S "${TL}p1" -S "${TL}p7" 2>/dev/null | xargs -r umount 2>/dev/null || true
for p in 1 7; do for m in $(findmnt -rn -o TARGET -S "${TL}p$p"); do umount "$m"; done; done

mount "${TL}p5" "$C"; mount "${TL}p7" "$C/data"; mount "${TL}p1" "$C/mnt/autoboot"
mount -t proc proc "$C/proc"; mount -t sysfs sys "$C/sys"; mount --rbind /dev "$C/dev"; mount -t tmpfs tmpfs "$C/run"
say "slot A: $(chroot "$C" /usr/bin/rauc --version), $(cat "$C/etc/onemind-release")"
grep -E 'tryboot|boot_partition' "$C/mnt/autoboot/autoboot.txt" | tr '\n' ' '; echo
mkdir -p "$P/bv"; mount -o ro "${TL}p2" "$P/bv"; say "boot A cmdline_a: $(cat "$P/bv/cmdline_a.txt")"; tail -8 "$P/bv/config.txt"; umount "$P/bv"

if [ -n "${SKIP_PREPARE:-}" ]; then   # reset to the state prepare-disk leaves: A committed, nothing pending
  printf '[all]\ntryboot_a_b=1\nboot_partition=2\n[tryboot]\nboot_partition=3\n' > "$C/mnt/autoboot/autoboot.txt"
  rm -f "$C/mnt/autoboot/slot-B.good" "$C/data/onemind/pending"; : > "$C/mnt/autoboot/slot-A.good"
  install -m 755 "$HERE/rpi-tryboot-ab.sh" "$C/usr/lib/onemind/rpi-tryboot-ab.sh"   # current kit version
fi
say "P-c device policy (rauc info under the device's system.conf)"
for b in good plain-good wrong-key; do
  if out=$(chroot "$C" /usr/bin/rauc --conf=/etc/rauc/system.conf info "/data/bundles/$b.raucb" 2>&1); then
    say "  $b: ACCEPTED ($(echo "$out" | grep -m1 -o 'Bundle Format:.*'))"
  else say "  $b: REFUSED ($(echo "$out" | grep -v '^ *[0-9]*%' | tail -n1))"; fi
done

say "P-d rauc install good.raucb from slot A"
# Desk-only substitution: the kit's RAUC is a D-Bus service build, which cannot
# run in a chroot without a system bus. Build the SAME pinned commit with
# -Dservice=false (CLI-only install path, accepts --override-boot-slot) and run
# it from tmpfs; slot A's own files are not changed.
NS=$P/rauc-noservice; rm -rf "$NS"
git clone -q -c advice.detachedHead=false --depth 1 --branch v1.15.2 https://github.com/rauc/rauc.git "$NS/src"
[ "$(git -C "$NS/src" rev-parse HEAD)" = 4fb7c798d6ae412344fb8f8d310d773046af3441 ]
meson setup --buildtype=release -Dtests=false -Dservice=false "$NS/build" "$NS/src" >/dev/null && ninja -C "$NS/build" >/dev/null
install -m 755 "$NS/build/rauc" "$C/run/rauc-noservice"; mkdir -p "$C/run/rauc-mnt"
say "  desk binary: $(chroot "$C" /run/rauc-noservice --version) (service=false, same commit)"
B4=$(cat "$C/mnt/autoboot/autoboot.txt" | tr '\n' ' ')
chroot "$C" /run/rauc-noservice --conf=/etc/rauc/system.conf --mount=/run/rauc-mnt install --override-boot-slot=A /data/bundles/good.raucb 2>&1 | grep -v '^ *[0-9]*%' | tail -14
say "  pending marker: $(cat "$C/data/onemind/pending" 2>/dev/null || echo none); reboot-param: $(cat "$C/run/systemd/reboot-param" 2>/dev/null || echo none)"
say "  autoboot.txt unchanged by install: $([ "$B4" = "$(tr '\n' ' ' < "$C/mnt/autoboot/autoboot.txt")" ] && echo yes || echo NO)"
mkdir -p "$P/rb"; mount -o ro "${TL}p6" "$P/rb"; say "  root B now: $(cat "$P/rb/etc/onemind-release")"; umount "$P/rb"
mount -o ro "${TL}p3" "$P/rb"; say "  boot B now: $(ls "$P/rb" | grep -c .) files, cmdline_b: $(cat "$P/rb/cmdline_b.txt")"; umount "$P/rb"
say "  backend get-primary: $(chroot "$C" /usr/lib/onemind/rpi-tryboot-ab.sh get-primary)  get-state B: $(chroot "$C" /usr/lib/onemind/rpi-tryboot-ab.sh get-state B)"

say "P-e backend state machine with a faked device tree"
DT=$C/run/fakedt; mkdir -p "$DT"; be(){ chroot "$C" env ONEMIND_DT=/run/fakedt /usr/lib/onemind/rpi-tryboot-ab.sh "$@" 2>&1; }
dt(){ printf "\\x00\\x00\\x00\\x0$1" > "$DT/tryboot"; printf "\\x00\\x00\\x00\\x0$2" > "$DT/partition"; }
rm -f "$C/run/systemd/reboot-param"                       # = the tryboot reboot happened (/run is volatile)
dt 1 3; say "  tryboot boot from p3: get-current=$(be get-current); set-state B good -> $(be set-state B good | tr '\n' ' ')"
say "  autoboot.txt now: $(tr '\n' ' ' < "$C/mnt/autoboot/autoboot.txt") good: $(ls "$C/mnt/autoboot" | grep good | tr '\n' ' ')"
dt 0 3; say "  normal boot from p3: get-primary=$(be get-primary); set-state B good -> rc=$(be set-state B good >/dev/null; echo $?)"
dt 0 3; say "  set-primary A (rollback path): $(be set-primary A | tr '\n' ' ') param=$(cat "$C/run/systemd/reboot-param" 2>/dev/null || echo none)"
rm -f "$C/run/systemd/reboot-param"; dt 0 3
o=$(be set-state A good) && rc=0 || rc=$?; say "  refuse commit without tryboot: set-state A good from a normal p3 boot -> $o rc=$rc"
o=$(be set-state A bad) && rc=0 || rc=$?; say "  set-state A bad -> rc=$rc; good files: $(ls "$C/mnt/autoboot" | grep good | tr '\n' ' ')"
say "done"
