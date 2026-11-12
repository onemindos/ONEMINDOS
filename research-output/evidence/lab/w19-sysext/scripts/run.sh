#!/bin/bash
# Lab W19-1: sysext/confext as the host-level plugin extension point.
# Runs INSIDE a disposable Debian 13 VM as root. See ../README.md for criteria.
set -uo pipefail
KVER=$(uname -r)
W=/root/w19; rm -rf "$W"; mkdir -p "$W"
say(){ echo; echo "=== $*"; }
listhash(){ find "$1" -xdev \( -type f -o -type l \) 2>/dev/null | grep -v -E '^/etc/(machine-id|resolv.conf|ld.so.cache|adjtime)' | sort | sha256sum | cut -d' ' -f1; }

say "0. versions"
grep -E '^(PRETTY_NAME|VERSION_ID)=' /usr/lib/os-release; systemctl --version | head -1; echo "kernel $KVER"

say "0b. setup: packages, and simulate the OneMind image declaring SYSEXT_LEVEL=1.0"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null && apt-get install -y -qq build-essential "linux-headers-$KVER" squashfs-tools kmod >/dev/null 2>&1 && echo "packages ok"
grep -q '^SYSEXT_LEVEL=' /usr/lib/os-release || echo 'SYSEXT_LEVEL=1.0' >> /usr/lib/os-release
grep SYSEXT_LEVEL /usr/lib/os-release

say "0c. build a trivial out-of-tree kernel module (stands in for a vendor driver)"
mkdir -p "$W/mod"; cat > "$W/mod/onemind_hello.c" <<'EOF'
#include <linux/module.h>
#include <linux/init.h>
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OneMind W19 lab stand-in driver");
static int __init h_init(void){ pr_info("onemind_hello: loaded\n"); return 0; }
static void __exit h_exit(void){ pr_info("onemind_hello: unloaded\n"); }
module_init(h_init); module_exit(h_exit);
EOF
echo 'obj-m += onemind_hello.o' > "$W/mod/Makefile"
make -s -C "/lib/modules/$KVER/build" M="$W/mod" modules >/dev/null 2>&1; ls -l "$W/mod/onemind_hello.ko" || echo "MODULE BUILD FAILED"

say "0d. build sysext 'onemind-hello' (binary + udev rule + module + per-kernel modules.dep)"
E="$W/sysext/onemind-hello"; mkdir -p "$E/usr/bin" "$E/usr/lib/udev/rules.d" "$E/usr/lib/extension-release.d" "$E/usr/lib/modules/$KVER/updates"
printf '#!/bin/sh\necho "onemind-hello adapter v1 running"\n' > "$E/usr/bin/onemind-hello"; chmod 755 "$E/usr/bin/onemind-hello"
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="0001", SYMLINK+="onemind-robot0", TAG+="systemd"' > "$E/usr/lib/udev/rules.d/99-onemind-hello.rules"
cp "$W/mod/onemind_hello.ko" "$E/usr/lib/modules/$KVER/updates/"
# Regenerate module indexes for THIS kernel with the extra module, in a staging copy (base untouched).
ST="$W/depstage"; mkdir -p "$ST/lib/modules"; cp -a "/usr/lib/modules/$KVER" "$ST/lib/modules/"
cp "$W/mod/onemind_hello.ko" "$ST/lib/modules/$KVER/updates/" 2>/dev/null || { mkdir -p "$ST/lib/modules/$KVER/updates"; cp "$W/mod/onemind_hello.ko" "$ST/lib/modules/$KVER/updates/"; }
depmod -b "$ST" "$KVER" && cp "$ST/lib/modules/$KVER"/modules.* "$E/usr/lib/modules/$KVER/"
printf 'ID=debian\nSYSEXT_LEVEL=1.0\n' > "$E/usr/lib/extension-release.d/extension-release.onemind-hello"
mksquashfs "$E" "$W/onemind-hello.raw" -quiet -noappend -all-root >/dev/null && ls -l "$W/onemind-hello.raw"

say "0e. build sysext 'onemind-future' declaring SYSEXT_LEVEL=2.0 (must be refused)"
F="$W/sysext/onemind-future"; mkdir -p "$F/usr/bin" "$F/usr/lib/extension-release.d"
printf '#!/bin/sh\necho future\n' > "$F/usr/bin/onemind-future"; chmod 755 "$F/usr/bin/onemind-future"
printf 'ID=debian\nSYSEXT_LEVEL=2.0\n' > "$F/usr/lib/extension-release.d/extension-release.onemind-future"
mksquashfs "$F" "$W/onemind-future.raw" -quiet -noappend -all-root >/dev/null

say "0f. build confext 'onemind-greenhouse' (profile-style /etc drop-ins)"
C="$W/confext/onemind-greenhouse"; mkdir -p "$C/etc/modules-load.d" "$C/etc/systemd/system/ssh.service.d" "$C/etc/extension-release.d"
echo onemind_hello > "$C/etc/modules-load.d/onemind-greenhouse.conf"
printf '[Service]\nEnvironment=ONEMIND_PROFILE=greenhouse\n' > "$C/etc/systemd/system/ssh.service.d/onemind-greenhouse.conf"
printf 'ID=debian\nVERSION_ID=13\n' > "$C/etc/extension-release.d/extension-release.onemind-greenhouse"
mksquashfs "$C" "$W/onemind-greenhouse.raw" -quiet -noappend -all-root >/dev/null

say "BASELINE hashes (nothing merged)"
systemd-sysext unmerge >/dev/null 2>&1; systemd-confext unmerge >/dev/null 2>&1
U0=$(listhash /usr); E0=$(listhash /etc); echo "usr=$U0"; echo "etc=$E0"

say "H1 + H3 + H4: install both sysexts into /var/lib/extensions and merge"
mkdir -p /var/lib/extensions /var/lib/confexts
cp "$W/onemind-hello.raw" "$W/onemind-future.raw" /var/lib/extensions/
systemd-sysext merge 2>&1 | sed 's/^/  /'
systemd-sysext status 2>&1 | sed 's/^/  /'
echo "-- H1 binary:"; /usr/bin/onemind-hello && echo "H1-binary PASS" || echo "H1-binary FAIL"
echo "-- H1 udev rule:"; udevadm control --reload && udevadm cat /usr/lib/udev/rules.d/99-onemind-hello.rules 2>&1 | tail -2; [ -f /usr/lib/udev/rules.d/99-onemind-hello.rules ] && echo "H1-udev PASS" || echo "H1-udev FAIL"
echo "-- /usr writable while merged? (expected: read-only)"; touch /usr/bin/w19-probe 2>&1 | sed 's/^/  /'; rm -f /usr/bin/w19-probe
echo "-- H4 future extension:"; [ -e /usr/bin/onemind-future ] && echo "H4 FAIL (merged)" || echo "H4 PASS (not merged)"
journalctl -b --no-pager -o cat -u systemd-sysext 2>/dev/null | tail -3
echo "-- H3 kernel module:"; modinfo onemind_hello 2>&1 | head -3
if modprobe onemind_hello 2>&1; then lsmod | grep onemind_hello && echo "H3 modprobe PASS"; else echo "H3 modprobe FAIL"; insmod "/usr/lib/modules/$KVER/updates/onemind_hello.ko" && lsmod | grep onemind_hello && echo "H3 insmod PASS"; fi
dmesg | grep -E 'onemind_hello|taint' | tail -3
modprobe -r onemind_hello 2>/dev/null || rmmod onemind_hello 2>/dev/null

say "H2: confext"
cp "$W/onemind-greenhouse.raw" /var/lib/confexts/
systemd-confext merge 2>&1 | sed 's/^/  /'
cat /etc/modules-load.d/onemind-greenhouse.conf && systemctl daemon-reload && systemctl show ssh -p Environment
[ -f /etc/modules-load.d/onemind-greenhouse.conf ] && echo "H2-merge PASS" || echo "H2-merge FAIL"
systemd-confext unmerge >/dev/null 2>&1; systemctl daemon-reload
[ -e /etc/modules-load.d/onemind-greenhouse.conf ] && echo "H2-unmerge FAIL" || echo "H2-unmerge PASS"
E1=$(listhash /etc); [ "$E0" = "$E1" ] && echo "H2-base-etc PASS (unchanged)" || echo "H2-base-etc FAIL ($E1)"

say "H5: uninstall"
rm -f /var/lib/extensions/onemind-hello.raw /var/lib/extensions/onemind-future.raw /var/lib/confexts/onemind-greenhouse.raw
systemd-sysext refresh 2>&1 | sed 's/^/  /'; systemd-sysext unmerge >/dev/null 2>&1
LEFT=$(ls /usr/bin/onemind-hello /usr/lib/udev/rules.d/99-onemind-hello.rules "/usr/lib/modules/$KVER/updates/onemind_hello.ko" 2>/dev/null)
[ -z "$LEFT" ] && echo "H5 PASS (no leftovers)" || echo "H5 FAIL: $LEFT"
U1=$(listhash /usr); [ "$U0" = "$U1" ] && echo "H1-base-usr PASS (unchanged)" || echo "H1-base-usr FAIL ($U1)"
modprobe -n onemind_hello 2>&1 | sed 's/^/  after uninstall modprobe -n: /'
echo DONE
