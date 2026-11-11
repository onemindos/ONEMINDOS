#!/bin/sh
# LAB-rauc-1152 (Pi 5 founder test): RAUC bootloader-custom-backend for the
# Raspberry Pi firmware's partition-level A/B ("tryboot_a_b", autoboot.txt).
# SPDX-License-Identifier: Apache-2.0
# Written for OneMind. The state logic follows Home Assistant OS's
# rpi-tryboot.sh (Apache-2.0, home-assistant/operating-system@fc301f55,
# buildroot-external/board/raspberrypi/rpi5-64/rootfs-overlay/usr/lib/rauc/),
# but switches whole boot partitions as the Raspberry Pi docs describe
# (raspberrypi/documentation@21d772e7, config_txt/autoboot.adoc L42-L94)
# instead of HAOS's os_prefix directories in one boot partition.
#
# Layout (MBR):  p1 FAT "autoboot" (autoboot.txt + slot-X.good markers)
#                p2 FAT boot A   p3 FAT boot B   p5 ext4 root A   p6 ext4 root B
#                p7 ext4 data
# Committed slot = [all] boot_partition in autoboot.txt. The other partition is
# always the [tryboot] partition. An update is "staged" when RAUC asked for it
# to become primary in this boot: we arm a one-shot "0 tryboot" reboot.
# The firmware clears the tryboot flag before it starts, so a crash, hang,
# watchdog reset or power cut during the trial returns to the committed slot.
set -u
AB=/mnt/autoboot
CONF=$AB/autoboot.txt
PARAM=/run/systemd/reboot-param
DT=${ONEMIND_DT:-/proc/device-tree/chosen/bootloader}   # override only for desk tests

part_of() { case "$1" in A) echo 2 ;; B) echo 3 ;; *) return 1 ;; esac; }
slot_of() { case "$1" in 2) echo A ;; 3) echo B ;; *) return 1 ;; esac; }
dtint() { [ -f "$DT/$1" ] || { echo 0; return; }; printf '%d\n' "0x$(od "$DT/$1" -v -An -t x1 | tr -d ' \n')"; }
committed() { slot_of "$(sed -n '/^\[all\]/,/^\[/s/^boot_partition=//p' "$CONF" | head -n1)"; }
armed() { [ -f "$PARAM" ] && grep -q tryboot "$PARAM"; }
write_conf() { # $1 = committed slot
  c=$(part_of "$1") || exit 1; t=2; [ "$c" = 2 ] && t=3
  printf '[all]\ntryboot_a_b=1\nboot_partition=%s\n[tryboot]\nboot_partition=%s\n' "$c" "$t" > "$CONF.new"
  sync "$CONF.new"
  # Lab only (test F-P11c): widen the commit window so a power pull can hit it.
  if [ -s /data/onemind/lab-commit-delay ]; then
    echo "COMMIT-WINDOW open for $(cat /data/onemind/lab-commit-delay)s: pull power now" > /dev/console
    sleep "$(cat /data/onemind/lab-commit-delay)"
  fi
  mv "$CONF.new" "$CONF"; sync "$AB"
}
other() { [ "$1" = A ] && echo B || echo A; }

case "${1:-}" in
get-primary)
  # An installed update is primary until its tryboot reboot has happened.
  if armed; then other "$(committed)"; else committed; fi ;;
set-primary)
  s=$2; part_of "$s" >/dev/null || exit 1
  if [ "$s" = "$(committed)" ]; then
    armed && rm -f "$PARAM"            # cancel a staged tryboot
    echo "tryboot-ab set-primary $s: committed already" >&2
  else
    # Next reboot tries the other partition once. Fail loudly if this cannot be
    # armed, so RAUC reports the activation as failed (desk pre-flight finding).
    mkdir -p "${PARAM%/*}" && echo "0 tryboot" > "$PARAM" && grep -q tryboot "$PARAM" \
      || { echo "tryboot-ab set-primary $s: FAILED to arm tryboot" >&2; exit 1; }
    echo "tryboot-ab set-primary $s: armed one-shot tryboot" >&2
  fi ;;
get-state)
  if [ -f "$AB/slot-$2.good" ]; then echo good; else echo bad; fi ;;
set-state)
  s=$2; st=$3
  if [ "$st" != good ]; then
    [ "$s" != "$(committed)" ] && armed && rm -f "$PARAM"
    rm -f "$AB/slot-$s.good"; sync "$AB"; exit 0
  fi
  # Commit: booted through tryboot, from the [tryboot] partition, for slot s.
  if [ "$(dtint tryboot)" = 1 ] && [ "$(slot_of "$(dtint partition)")" = "$s" ] \
     && [ "$s" != "$(committed)" ]; then
    echo "tryboot-ab: committing slot $s (autoboot.txt swap)" >&2
    write_conf "$s"
  elif [ "$s" != "$(committed)" ]; then
    echo "tryboot-ab: refusing to mark $s good: not booted from it via tryboot" >&2; exit 1
  fi
  : > "$AB/slot-$s.good"; sync "$AB" ;;
get-current)
  slot_of "$(dtint partition)" ;;
*) echo "unknown operation: ${1:-}" >&2; exit 1 ;;
esac
exit 0
