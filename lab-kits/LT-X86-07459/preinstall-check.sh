#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LT-X86-07459: read-only pre-install check for the Dell Inspiron 7459 all-in-one (the daily hub).
# Run it from any Linux live USB (a Debian 13 live stick is fine). It writes and changes nothing.
#   sh preinstall-check.sh            prints a table and ends with READY, WARN or NOT-READY
# ONEMIND_CHECK_ROOT=<dir> reads /proc and /sys from a copy (the unit tests use this).
# Prints no serial numbers, MAC addresses or IP addresses.
set -eu
R=${ONEMIND_CHECK_ROOT:-}
fails=0; warns=0
row() { printf '%-22s %-8s %s\n' "$1" "$2" "$3"; case "$2" in FAIL) fails=$((fails+1));; WARN) warns=$((warns+1));; esac; }

# 1. CPU model and x86-64 level. v2 needs: cx16 lahf_lm popcnt sse4_1 sse4_2 ssse3 (sse3 shows as pni).
cpuinfo="$R/proc/cpuinfo"
model=$(sed -n 's/^model name[^:]*: *//p' "$cpuinfo" 2>/dev/null | head -1)
flags=$(sed -n 's/^flags[^:]*: *//p' "$cpuinfo" 2>/dev/null | head -1)
has() { for f in "$@"; do case " $flags " in *" $f "*) ;; *) return 1;; esac; done; }
if [ -z "$flags" ]; then
  row "CPU" FAIL "cannot read cpu flags"
else
  if has lm cx16 lahf_lm popcnt sse4_1 sse4_2 ssse3 pni; then lvl=2
    has avx avx2 bmi1 bmi2 f16c fma abm movbe xsave && lvl=3
    row "CPU" PASS "${model:-unknown model}; x86-64-v$lvl"
  else
    row "CPU" FAIL "${model:-unknown model}; below x86-64-v2 (missing one of lm cx16 lahf_lm popcnt sse4_1 sse4_2 ssse3)"
  fi
  if has vmx || has svm; then row "Virtualization" PASS "vmx/svm present"
  else row "Virtualization" WARN "vmx/svm off: enable VT-x in the BIOS"; fi
fi

# 2. Memory
kb=$(sed -n 's/^MemTotal: *\([0-9]*\) kB.*/\1/p' "$R/proc/meminfo" 2>/dev/null | head -1)
if [ -n "$kb" ] && [ "$kb" -ge 15000000 ]; then row "Memory" PASS "$((kb/1048576)) GiB"
elif [ -n "$kb" ] && [ "$kb" -ge 7000000 ]; then row "Memory" WARN "$((kb/1048576)) GiB: the hub needs more than 8 GiB (target 32)"
else row "Memory" FAIL "${kb:-unknown} kB"; fi

# 3. Disks: SSD or spinning. Skips loop, ram, optical and the live stick (removable).
found=0
for d in "$R"/sys/block/*; do
  [ -d "$d" ] || continue
  n=${d##*/}
  case "$n" in loop*|ram*|sr*|zram*|fd*) continue;; esac
  [ "$(cat "$d/removable" 2>/dev/null || echo 0)" = 1 ] && continue
  sz=$(cat "$d/size" 2>/dev/null || echo 0); gib=$((sz/2/1024/1024))
  rot=$(cat "$d/queue/rotational" 2>/dev/null || echo 1)
  case "$n" in nvme*) kind=NVMe; rot=0;; *) [ "$rot" = 0 ] && kind=SSD || kind="HDD (spinning)";; esac
  found=1
  if [ "$gib" -lt 32 ]; then row "Disk $n" FAIL "$kind, $gib GiB: the installer needs 32 GiB or more"
  elif [ "$rot" = 1 ]; then row "Disk $n" WARN "$kind, $gib GiB: a hard disk works but is slow; fit an SSD (see README)"
  else row "Disk $n" PASS "$kind, $gib GiB"; fi
done
[ "$found" = 1 ] || row "Disk" FAIL "no internal disk found"

# 4. UEFI, Secure Boot, TPM
if [ -d "$R/sys/firmware/efi" ]; then
  row "Boot mode" PASS "UEFI"
  sb=""
  for v in "$R"/sys/firmware/efi/efivars/SecureBoot-*; do
    [ -f "$v" ] && sb=$(od -An -t u1 -j4 -N1 "$v" | tr -d ' ')
  done
  case "$sb" in 0) row "Secure Boot" PASS "off (needed for dev builds)";;
    1) row "Secure Boot" FAIL "on: turn it off in the BIOS; dev builds are not signed";;
    *) row "Secure Boot" WARN "state not readable: read it in the BIOS";; esac
else
  row "Boot mode" FAIL "Legacy/CSM: the image needs UEFI; switch the BIOS boot mode"
fi
if [ -e "$R/sys/class/tpm/tpm0" ]; then row "TPM" PASS "present (tpm0)"; else row "TPM" WARN "none seen (not needed for the dev install; note it)"; fi

# 5. Wired Ethernet: a non-wireless, non-virtual interface with carrier.
eth=0; link=0
for i in "$R"/sys/class/net/*; do
  [ -d "$i" ] || continue
  n=${i##*/}
  case "$n" in lo|docker*|veth*|br*|virbr*|tun*|tap*) continue;; esac
  [ -d "$i/wireless" ] && continue
  eth=1
  [ "$(cat "$i/carrier" 2>/dev/null || echo 0)" = 1 ] && link=1
done
if [ "$eth" = 0 ]; then row "Ethernet" FAIL "no wired interface"
elif [ "$link" = 0 ]; then row "Ethernet" WARN "wired port found, no cable link: plug in the network cable"
else row "Ethernet" PASS "wired link up"; fi

echo
if [ "$fails" -gt 0 ]; then echo "NOT-READY: $fails failure(s), $warns warning(s)"; exit 1
elif [ "$warns" -gt 0 ]; then echo "WARN: $warns warning(s); read them, then decide"; exit 0
else echo "READY"; fi
