#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# hw-check.sh: read-only hardware report for an installed OneMind box (the Dell all-in-one, #234, lab-kits/LT-X86-07459).
# Run it on the box as the owner, for example:   ssh <owner>@<box> 'sh -s' < scripts/hw-check.sh
# It only LOOKS: it reads /sys, /proc and the output of list/status commands. It never changes, mounts, installs,
# starts, pairs, scans or writes anything, never opens /dev/watchdog (opening it would start the timer that reboots
# the box), and masks serial numbers, MAC and IP addresses, network names and keys in everything it prints.
#   HW_CHECK_SUDO=1   read root-only items (SMART, btrfs) with `sudo -n` (it never asks for a password, never edits)
#   HW_CHECK_ROOT=dir read /sys, /proc and /dev from a copy of the tree (the unit tests use this)
# Output: one line per check (PASS, WARN, FAIL or SKIP), then a plain-language summary. Exit 1 only if a check FAILed.
# SKIP means "could not look" (a tool is missing on this image or needs root), which is a finding, not a fault.
set -u
R=${HW_CHECK_ROOT:-}
pass=0; warn=0; fail=0; skip=0

have() { command -v "$1" >/dev/null 2>&1; }
# ro: run one read-only command with a time limit when `timeout` exists (stderr is merged so errors become evidence).
# stdin is /dev/null so that no tool can swallow the rest of this script when it is piped in with `sh -s` over SSH.
ro() { if have timeout; then timeout 30 "$@" 2>&1 </dev/null; else "$@" 2>&1 </dev/null; fi; }
# rro: like ro, but through `sudo -n` when the owner asked for it.
rro() { if [ "${HW_CHECK_SUDO:-0}" = 1 ] && have sudo; then ro sudo -n "$@"; else ro "$@"; fi; }
# first_line: the first non-empty line, cut to 100 characters so no long dump or key can land in the report.
# unit_state: `systemctl is-active` for one unit (read-only), or 'unknown' without systemd.
unit_state() { if have systemctl; then ro systemctl is-active "$1" | first_line; else echo unknown; fi; }
first_line() { sed -n '/[^[:space:]]/{p;q;}' | cut -c1-100; }

row() {
  printf '%-5s %-22s %s\n' "$1" "$2" "$3"
  case "$1" in PASS) pass=$((pass+1));; WARN) warn=$((warn+1));; FAIL) fail=$((fail+1));; *) skip=$((skip+1));; esac
}

section() { printf '\n== %s\n' "$1"; }

report() {
  printf 'OneMind hardware check (read-only), %s\n' "$(date -u '+%Y-%m-%d %H:%M UTC' 2>/dev/null || echo 'time unknown')"
  printf 'Nothing is changed by this check. Serial numbers, addresses and network names are masked.\n'

  section "This machine"
  osname=$(sed -n 's/^PRETTY_NAME="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' /etc/os-release 2>/dev/null | head -1)
  printf '%-22s %s\n' "System" "${osname:-unknown}"
  printf '%-22s %s\n' "Kernel" "$(uname -sr 2>/dev/null || echo unknown)"
  model=$(sed -n 's/^model name[^:]*: *//p' "$R/proc/cpuinfo" 2>/dev/null | head -1)
  printf '%-22s %s\n' "CPU" "${model:-unknown}"
  kb=$(sed -n 's/^MemTotal: *\([0-9]*\) kB.*/\1/p' "$R/proc/meminfo" 2>/dev/null | head -1)
  if [ -n "$kb" ]; then printf '%-22s %s GiB\n' "Memory" "$((kb/1048576))"; else printf '%-22s unknown\n' "Memory"; fi

  section "Checks"

  # 1. Wi-Fi through NetworkManager. Names of networks are never printed.
  if have nmcli; then
    wl=$(ro nmcli -t -f DEVICE,TYPE,STATE device | awk -F: '$2=="wifi"{print $3}' | head -1)
    radio=$(ro nmcli radio wifi | first_line)
    if [ -z "$wl" ]; then row WARN "Wi-Fi" "NetworkManager lists no Wi-Fi adapter (a wired-only setup is fine; if the Dell has Wi-Fi, its driver or firmware is missing)"
    elif [ "$radio" = disabled ]; then row WARN "Wi-Fi" "adapter found, radio is switched off"
    else row PASS "Wi-Fi" "adapter found, state: $wl"; fi
  else row SKIP "Wi-Fi" "nmcli (NetworkManager) is not installed"; fi

  # 2. Firmware devices. get-devices only lists; it never updates or downloads.
  if have fwupdmgr; then
    out=$(ro fwupdmgr get-devices --no-unreported-check)
    n=$(printf '%s\n' "$out" | grep -c 'Device ID:')
    if [ "$n" -gt 0 ]; then row PASS "Firmware devices" "$n device(s) known to fwupd (update status is not checked here)"
    else row WARN "Firmware devices" "fwupd lists no devices: $(printf '%s\n' "$out" | first_line)"; fi
  else row SKIP "Firmware devices" "fwupdmgr (fwupd) is not installed"; fi

  # 3. Sensors: temperature chips the kernel exposes in sysfs.
  chips=0; hot=0; names=""
  for h in "$R"/sys/class/hwmon/hwmon*; do
    [ -d "$h" ] || continue
    chips=$((chips+1)); nm=$(cat "$h/name" 2>/dev/null || echo chip); names="$names $nm"
    for t in "$h"/temp*_input; do
      [ -f "$t" ] || continue
      v=$(cat "$t" 2>/dev/null || echo 0); v=$((v/1000)); [ "$v" -gt "$hot" ] && hot=$v
    done
  done
  if [ "$chips" -eq 0 ]; then row WARN "Sensors" "no hardware monitor chips found"
  elif [ "$hot" -ge 90 ]; then row WARN "Sensors" "$chips chip(s) (${names# }); hottest reading ${hot} C is high"
  else row PASS "Sensors" "$chips chip(s) (${names# }); hottest reading ${hot} C"; fi

  # 4. A USB stick that is seen but not mounted (OneMind must not auto-mount strangers' drives).
  if have lsblk; then
    usb=$(ro lsblk -P -o NAME,TRAN,TYPE,MOUNTPOINTS | grep 'TRAN="usb"' | grep -c 'TYPE="disk"')
    mounted=$(ro lsblk -P -o NAME,TRAN,TYPE,MOUNTPOINTS | grep 'TRAN="usb"' | grep -c 'MOUNTPOINTS="/')
    # a partition of a USB disk has an empty TRAN on some kernels, so also look at partitions of removable disks
    for d in "$R"/sys/block/*; do
      [ -d "$d" ] || continue
      [ "$(cat "$d/removable" 2>/dev/null || echo 0)" = 1 ] || continue
      case "${d##*/}" in loop*|ram*|sr*) continue;; esac
      m=$(ro lsblk -n -o MOUNTPOINTS "/dev/${d##*/}" | grep -c '/')
      [ "$m" -gt "$mounted" ] && mounted=$m
    done
    if [ "$usb" -eq 0 ]; then row WARN "USB stick" "none seen: plug one in and run this again to test it"
    elif [ "$mounted" -gt 0 ]; then row WARN "USB stick" "seen, but it is MOUNTED (expected: seen and not mounted)"
    else row PASS "USB stick" "$usb seen and not mounted"; fi
  else row SKIP "USB stick" "lsblk is not installed"; fi

  # 5. Watchdog device. Only its existence is checked: opening /dev/watchdog would arm it.
  if [ -c "$R/dev/watchdog" ] || [ -e "$R/dev/watchdog" ]; then
    row PASS "Watchdog" "/dev/watchdog present (not opened)"
  elif [ -d "$R/sys/class/watchdog" ] && [ -n "$(ls "$R/sys/class/watchdog" 2>/dev/null)" ]; then
    row WARN "Watchdog" "a watchdog is registered in sysfs but /dev/watchdog is missing"
  else row WARN "Watchdog" "no /dev/watchdog (the box cannot reboot itself if it hangs hard)"; fi

  # 6. Sound: PipeWire (or Pulse-compatible) output devices.
  uid=$(id -u 2>/dev/null || echo 0)
  if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "$R/run/user/$uid" ]; then XDG_RUNTIME_DIR="$R/run/user/$uid"; export XDG_RUNTIME_DIR; fi
  if have wpctl; then
    sinks=$(ro wpctl status | sed -n '/^Audio/,/^Video/p' | sed -n '/Sinks:/,/Sources:/p' | grep -cE '[0-9]+\. ')
    if [ "$sinks" -gt 0 ]; then row PASS "Sound" "$sinks PipeWire output device(s)"
    else row WARN "Sound" "PipeWire answers but lists no output device (or no audio session for this user)"; fi
  elif have pactl; then
    sinks=$(ro pactl list short sinks | grep -c '[[:alnum:]]')
    if [ "$sinks" -gt 0 ]; then row PASS "Sound" "$sinks output device(s)"; else row WARN "Sound" "no output device"; fi
  elif [ -r "$R/proc/asound/cards" ] && grep -q '[[:alnum:]]' "$R/proc/asound/cards"; then
    row WARN "Sound" "the kernel sees a sound card but no PipeWire or Pulse tool is installed"
  else row SKIP "Sound" "no PipeWire tools installed and no sound card listed"; fi

  # 7. Bluetooth controller. Addresses are masked; nothing is scanned or paired.
  bt=0
  for b in "$R"/sys/class/bluetooth/hci*; do [ -e "$b" ] && bt=$((bt+1)); done
  if [ "$bt" -gt 0 ]; then
    blk=""; have rfkill && blk=$(ro rfkill list bluetooth | grep -c 'blocked: yes')
    if [ "${blk:-0}" -gt 0 ]; then row WARN "Bluetooth" "$bt controller(s), but blocked (radio switch or rfkill)"
    else row PASS "Bluetooth" "$bt controller(s) present"; fi
  elif have bluetoothctl && [ "$(ro bluetoothctl list | grep -c '^Controller')" -gt 0 ]; then
    row PASS "Bluetooth" "controller present"
  else row WARN "Bluetooth" "no controller found"; fi

  # 8. Printers through CUPS. Lists what already exists; adds nothing.
  if have lpstat; then
    act=$(unit_state cups)
    uris=$(ro lpstat -v)
    np=$(printf '%s\n' "$uris" | grep -c '^device for ')
    ipp=$(printf '%s\n' "$uris" | grep -cE 'ipp|dnssd')
    if [ "$np" -gt 0 ]; then row PASS "Printers" "$np printer(s), $ipp driverless (IPP); CUPS is ${act:-unknown}"
    else row WARN "Printers" "no printer set up (CUPS is ${act:-unknown}); fine if you have none, otherwise add one driverless"; fi
  else row SKIP "Printers" "CUPS (lpstat) is not installed"; fi

  # 9. VA-API video acceleration.
  if have vainfo; then
    out=$(ro vainfo)
    prof=$(printf '%s\n' "$out" | grep -c 'VAProfile')
    if printf '%s\n' "$out" | grep -q 'VAProfileH264'; then row PASS "Video (VA-API)" "$prof profile(s), H.264 supported"
    elif [ "$prof" -gt 0 ]; then row WARN "Video (VA-API)" "$prof profile(s) but no H.264"
    else row WARN "Video (VA-API)" "no VA-API driver answered: $(printf '%s\n' "$out" | first_line)"; fi
  else row SKIP "Video (VA-API)" "vainfo is not installed"; fi

  # 10. Console keyboard: a keyboard device with the console handler, and the console keymap.
  kbd=$(grep -c 'Handlers=.*kbd' "$R/proc/bus/input/devices" 2>/dev/null)
  km=""; have localectl && km=$(ro localectl status | sed -n 's/^ *VC Keymap: *//p' | head -1)
  if [ "${kbd:-0}" -gt 0 ]; then row PASS "Console keyboard" "$kbd keyboard device(s); console keymap: ${km:-not reported}"
  else row WARN "Console keyboard" "no keyboard device with a console handler (plug in a USB keyboard)"; fi

  # 11. TPM 2.0 (it seals the /data key, D-020).
  if [ -d "$R/sys/class/tpm/tpm0" ]; then
    maj=$(cat "$R/sys/class/tpm/tpm0/tpm_version_major" 2>/dev/null || echo "")
    if [ "$maj" = 2 ] || [ -e "$R/dev/tpmrm0" ]; then row PASS "TPM 2.0" "present"
    else row WARN "TPM 2.0" "a TPM is present but not reported as version 2"; fi
  else row WARN "TPM 2.0" "no TPM: turn it on in the BIOS (D-020: without one /data is not encrypted)"; fi

  # 12. Disk health (SMART overall verdict only; serial numbers are never printed).
  if have smartctl; then
    any=0
    for d in "$R"/sys/block/*; do
      [ -d "$d" ] || continue
      n=${d##*/}
      case "$n" in loop*|ram*|sr*|zram*|fd*|dm-*) continue;; esac
      [ "$(cat "$d/removable" 2>/dev/null || echo 0)" = 1 ] && continue
      any=1
      out=$(rro smartctl -H "/dev/$n")
      if printf '%s\n' "$out" | grep -qE 'overall-health.*: *(PASSED|OK)|SMART Health Status: *OK'; then row PASS "Disk health $n" "SMART says healthy"
      elif printf '%s\n' "$out" | grep -qi 'FAILED'; then row FAIL "Disk health $n" "SMART reports the disk is failing: back up and replace it"
      elif printf '%s\n' "$out" | grep -qiE 'permission|denied|root|sudo'; then row SKIP "Disk health $n" "needs root: run again with HW_CHECK_SUDO=1 (passwordless sudo)"
      else row WARN "Disk health $n" "no SMART verdict ($(printf '%s\n' "$out" | first_line))"; fi
    done
    [ "$any" = 1 ] || row WARN "Disk health" "no internal disk listed"
  else row SKIP "Disk health" "smartctl (smartmontools) is not installed"; fi

  # 13. btrfs /data and snapper (the owner's files are snapshotted in /data/storage, config "storage").
  if have findmnt; then
    fs=$(ro findmnt -no FSTYPE /data | first_line)
    src=$(ro findmnt -no SOURCE /data | first_line)
    case "$fs" in
      btrfs)
        enc="not encrypted"; case "$src" in /dev/mapper/*) enc="encrypted (LUKS2)";; esac
        row PASS "/data filesystem" "btrfs, $enc"
        if have snapper; then
          cfg=$(ro snapper --no-dbus list-configs | grep -c '^storage')
          if [ "$cfg" -gt 0 ]; then
            tl=$(unit_state snapper-timeline.timer)
            row PASS "Snapshots (snapper)" "config 'storage' exists; timeline timer: ${tl:-unknown}"
          else row WARN "Snapshots (snapper)" "no 'storage' config (or root is needed to list it: HW_CHECK_SUDO=1)"; fi
        else row SKIP "Snapshots (snapper)" "snapper is not installed"; fi
        if have btrfs; then
          st=$(rro btrfs device stats /data)
          if printf '%s\n' "$st" | grep -qiE 'must be run as root|permission|denied'; then row SKIP "btrfs error counters" "needs root: HW_CHECK_SUDO=1"
          # Real lines look like '[/dev/mapper/onemind-data].write_io_errs    3': a '.' sits between ']' and the name.
          elif printf '%s\n' "$st" | grep -E '\]\.[a-z_]+_errs[[:space:]]+[1-9]' >/dev/null; then row FAIL "btrfs error counters" "the filesystem recorded read, write or corruption errors"
          elif [ -n "$st" ]; then row PASS "btrfs error counters" "all zero"
          else row WARN "btrfs error counters" "no answer"; fi
        fi;;
      "") row WARN "/data filesystem" "/data is not mounted";;
      *) row WARN "/data filesystem" "$fs (expected btrfs on a new install; an older install may be ext4)";;
    esac
  else row SKIP "/data filesystem" "findmnt is not installed"; fi

  # 14. Boot slot status (RAUC A/B). Reading the status never marks or switches a slot.
  if have rauc; then
    out=$(rro rauc status)
    booted=$(printf '%s\n' "$out" | sed -n 's/^Booted from: *//p' | head -1)
    # rauc lists slots in no fixed order, so take 'boot status' from the slot block whose header says 'booted',
    # e.g. 'o [rootfs.0] (/dev/sda4, ext4, booted)'. A new '[...]' header line starts the next block.
    bstat=$(printf '%s\n' "$out" | awk '/^[[:space:]]*[^[:space:]]*[[:space:]]*\[[^]]+\][[:space:]]*\(/ { inb = ($0 ~ /booted/) ; next }
      inb && /^[[:space:]]*boot status:/ { sub(/^[[:space:]]*boot status:[[:space:]]*/, ""); print; exit }')
    if [ -n "$booted" ] && [ "$bstat" = good ]; then row PASS "Boot slot" "booted from ${booted%% *}, status good"
    elif [ -n "$booted" ]; then row WARN "Boot slot" "booted from ${booted%% *}, status ${bstat:-unknown} (a new update stays 'bad' or unmarked until the health gate commits it)"
    else row SKIP "Boot slot" "rauc gave no slot answer (it may need root: HW_CHECK_SUDO=1)"; fi
  else row SKIP "Boot slot" "rauc is not installed"; fi

  section "In plain words"
  total=$((pass+warn+fail+skip))
  printf '%s checks: %s passed, %s need a look (WARN), %s failed, %s could not be checked (SKIP).\n' "$total" "$pass" "$warn" "$fail" "$skip"
  if [ "$fail" -gt 0 ]; then printf 'Something is wrong that you should fix before putting real files here. Start with the FAIL lines.\n'
  elif [ "$warn" -gt 0 ] || [ "$skip" -gt 0 ]; then printf 'Nothing is broken, but write down every WARN and SKIP in the results file: each is either a part this box does not have, a tool the image does not ship yet, or a setting to fix.\n'
  else printf 'Every item answered and looks healthy.\n'; fi
  printf 'This report changed nothing on the box.\n'
}

# Everything printed goes through one scrub: MAC addresses, IPv4 and IPv6 addresses (full and '::' compressed), e-mail addresses, long hex strings
# (keys, tokens, serials) and home paths are replaced before they reach the screen or a file. The report runs in a
# subshell, so its text is captured first and the exit code is read back from the printed FAIL lines.
out=$(report)
printf '%s\n' "$out" | sed -E \
  -e 's/([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}/<mac>/g' \
  -e 's/\b([0-9]{1,3}\.){3}[0-9]{1,3}\b/<ip>/g' \
  -e 's/\b([0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}\b/<ip6>/g' \
  -e 's/(^|[^[:alnum:]_:.])([0-9A-Fa-f]{1,4}(:[0-9A-Fa-f]{1,4})*)?::([0-9A-Fa-f]{1,4}(:[0-9A-Fa-f]{1,4})*)?([^[:alnum:]_:]|$)/\1<ip6>\6/g' \
  -e 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/<email>/g' \
  -e 's/\b[0-9A-Fa-f]{24,}\b/<hex>/g' \
  -e 's#/(home|Users)/[A-Za-z0-9._-]+#/<home>#g'
if printf '%s\n' "$out" | grep -q '^FAIL '; then exit 1; fi
exit 0
