# Changes against `../../rauc-k3s-gate/scripts/`

`guest/` is byte-identical to the earlier spike (gate, k3s check, pre-install handler, units, manifests, GRUB template, hang stand-in, API stand-in). New files: `build-rauc.sh` (RAUC 1.15.2 from the pinned tag for arm64 and amd64, plus T12), `t12-control.sh` (unfixed v1.15.1 control, added after pre-registration) and `pi5/` (founder test kit). The full unified diffs follow.

```diff
--- rauc-k3s-gate/scripts/build.sh
+++ rauc-1152/scripts/build.sh
@@ -1,12 +1,15 @@
 #!/bin/bash
-# LAB-rauc-k3s-gate build: Debian 13 amd64 RAUC A/B disk image with k3s and the
-# fresh-signal health gate, plus 7 bundles. Derived from ../../rauc/scripts/build.sh.
+# LAB-rauc-1152 build: Debian 13 amd64 RAUC A/B disk image with k3s and the
+# fresh-signal health gate, plus 8 bundles, using RAUC 1.15.2 built from the
+# pinned upstream tag by build-rauc.sh (not Debian's 1.13 package), and a
+# verity-only bundle policy. Derived from ../../rauc-k3s-gate/scripts/build.sh.
 # Run as root INSIDE a disposable Debian 13 Lima VM (amd64 is bootstrapped
 # through qemu-user binfmt). Never run on the host.
-#   sudo OUT=/var/lab/rkg-out DL=<dir with verified k3s files> ./build.sh
+#   sudo OUT=/var/lab/r1152-out DL=<dir with verified k3s files> ./build.sh
+# Needs build-rauc.sh to have run with the same OUT (rauc-arm64, rauc-amd64-dest.tar).
 set -euo pipefail
 S=$(cd "$(dirname "$0")" && pwd); G=$S/guest
-W=${W:-/var/lab/rkg}             # VM-local work dir
+W=${W:-/var/lab/r1152}             # VM-local work dir
 OUT=${OUT:?set OUT}; DL=${DL:?set DL (k3s, sha256sum-amd64.txt, k3s-airgap-images-amd64.tar.zst)}
 SUITE=trixie; MIRROR=http://deb.debian.org/debian
 COMPAT=onemind-lab-x86_64
@@ -16,6 +19,8 @@
 PU_ESP=6e0a8b0e-0000-4a00-8000-0000000000e5
 PU_DATA=6e0a8b0e-0000-4a00-8000-0000000000da
 log(){ echo "[build $(date -u +%T)] $*"; }
+RAUC=$OUT/rauc-arm64            # upstream 1.15.2, used for every bundle operation here
+"$RAUC" --version | grep -qxE 'rauc v?1\.15\.2' || { echo "ERROR: need rauc 1.15.2 from build-rauc.sh"; exit 1; }
 rm -rf "$W"; mkdir -p "$W"/{keys,bundles,stage} "$OUT"
 
 log "verify k3s artifacts against the release sha256sum file"
@@ -37,10 +42,16 @@
 # ---------------------------------------------------------- 2. amd64 rootfs
 log "mmdebstrap amd64 $SUITE"
 mmdebstrap --mode=root --arch=amd64 --variant=minbase \
-  --include=systemd-sysv,udev,dbus,login,linux-image-amd64,initramfs-tools,rauc,rauc-service,grub-common,grub-efi-amd64-bin,e2fsprogs,util-linux,procps,kmod,squashfs-tools,iptables,ca-certificates,curl,socat,iproute2 \
+  --include=systemd-sysv,udev,dbus,login,linux-image-amd64,initramfs-tools,$(paste -sd, $OUT/rauc-amd64-runtime-pkgs.txt),grub-common,grub-efi-amd64-bin,e2fsprogs,util-linux,procps,kmod,squashfs-tools,iptables,ca-certificates,curl,socat,iproute2 \
   $SUITE "$W/rootfs" "deb $MIRROR $SUITE main" \
   "deb http://deb.debian.org/debian-security $SUITE-security main" 2>&1 | tail -3
 R=$W/rootfs
+# Upstream RAUC 1.15.2 (amd64) with its D-Bus service, policy and systemd unit.
+tar -C $R -xf "$OUT/rauc-amd64-dest.tar"
+if chroot $R ldd /usr/bin/rauc | grep 'not found'; then echo "ERROR: missing RAUC runtime library"; exit 1; fi
+chroot $R /usr/bin/rauc --version
+if chroot $R dpkg-query -W rauc rauc-service >/dev/null 2>&1; then echo "ERROR: Debian rauc package present"; exit 1; fi
+echo "Debian rauc package: not installed (expected)"
 
 log "customise rootfs"
 echo onemind-lab > $R/etc/hostname
@@ -67,6 +78,7 @@
 bootloader=grub
 grubenv=/boot/efi/EFI/BOOT/grubenv
 data-directory=/data/rauc
+bundle-formats=verity
 
 [keyring]
 path=/etc/rauc/keyring.pem
@@ -146,12 +158,12 @@
 echo "K3S_EXTRA_ARGS=" > $R/etc/default/k3s; : > $R/etc/default/onemind-health-gate
 
 # ------------------------------------------------------------- 5. bundles
-mkbundle(){ # $1=image $2=version $3=key-prefix $4=out
+mkbundle(){ # $1=image $2=version $3=key-prefix $4=out [$5=format, default verity]
   local d="$W/bundles/$4.d"; rm -rf "$d"; mkdir -p "$d"
   cp "$W/stage/$1.ext4" "$d/rootfs.ext4"
-  printf '[update]\ncompatible=%s\nversion=%s\n\n[bundle]\nformat=verity\n\n[image.rootfs]\nfilename=rootfs.ext4\n' "$COMPAT" "$2" > "$d/manifest.raucm"
+  printf '[update]\ncompatible=%s\nversion=%s\n\n[bundle]\nformat=%s\n\n[image.rootfs]\nfilename=rootfs.ext4\n' "$COMPAT" "$2" "${5:-verity}" > "$d/manifest.raucm"
   rm -f "$W/bundles/$4.raucb"
-  rauc bundle --cert="$W/keys/$3-signer.cert.pem" --key="$W/keys/$3-signer.key.pem" "$d" "$W/bundles/$4.raucb" >/dev/null
+  "$RAUC" bundle --cert="$W/keys/$3-signer.cert.pem" --key="$W/keys/$3-signer.key.pem" "$d" "$W/bundles/$4.raucb" >/dev/null
   rm -rf "$d"
 }
 log "rauc bundles"
@@ -162,10 +174,11 @@
 mkbundle bad-hang 6 lab bad-hang
 mkbundle naive-noagent 7 lab naive-noagent
 mkbundle good 2 wrong wrong-key
-for b in good bad-k3s bad-noagent bad-boot bad-hang naive-noagent; do
-  rauc info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/$b.raucb" 2>&1 | grep -E "^Version|Verified" | sed "s/^/[$b] /"
+mkbundle good 2 lab plain-good plain                                  # T11: valid signature, plain format
+for b in good bad-k3s bad-noagent bad-boot bad-hang naive-noagent plain-good; do
+  "$RAUC" info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/$b.raucb" 2>&1 | grep -E "^Version|Verified|Bundle Format" | sed "s/^/[$b] /"
 done
-if rauc info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/wrong-key.raucb" >/dev/null 2>&1; then
+if "$RAUC" info --keyring="$W/keys/lab-ca.cert.pem" "$W/bundles/wrong-key.raucb" >/dev/null 2>&1; then
   echo "ERROR: wrong-key bundle verified"; exit 1; else echo "[wrong-key] rejected by rauc info (expected)"; fi
 
 # ------------------------------------------------------------ 6. disk image
--- rauc-k3s-gate/scripts/run-tests.py
+++ rauc-1152/scripts/run-tests.py
@@ -1,9 +1,9 @@
 #!/usr/bin/env python3
-"""LAB-rauc-k3s-gate test driver. Runs INSIDE the disposable Lima VM.
+"""LAB-rauc-1152 test driver (from LAB-rauc-k3s-gate; adds the RAUC version check in T1 and T11). Runs INSIDE the disposable Lima VM.
 
 Boots the x86_64 RAUC A/B image under QEMU TCG with user-mode networking
 (restrict=on: no route to the LAN or internet) and an i6300esb watchdog,
-drives the serial console, and runs T1..T10 from README section 3.
+drives the serial console, and runs T1..T11 from README section 3.
 Power cut = SIGKILL of the QEMU process.
 
   python3 -I run-tests.py --disk /var/lab/run/disk.img --log serial.log [--upto T3]
@@ -15,6 +15,12 @@
 ENV = "grub-editenv /boot/efi/EFI/BOOT/grubenv list"
 
 
+def envkv(out):
+    # Compare only grubenv KEY=VALUE lines: terminal escape fragments split across
+    # serial reads can leak into captured text (LAB-rauc-1152 deviation 4).
+    return sorted(re.findall(r"^(?:ORDER=[AB ]+|[AB]_(?:OK|TRY)=\d+)\s*$", out, re.M))
+
+
 class VM:
     def __init__(self, disk, vars_fd, log):
         self.disk, self.vars_fd, self.logf = disk, vars_fd, log
@@ -146,7 +152,7 @@
     ap.add_argument("--log", required=True)
     ap.add_argument("--upto", default="T10")
     a = ap.parse_args()
-    order = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]
+    order = ["T1", "T2", "T11", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]
     upto = order.index(a.upto)
     vars_fd = os.path.join(os.path.dirname(a.disk), "OVMF_VARS.fd")
     shutil.copy("/usr/share/OVMF/OVMF_VARS_4M.fd", vars_fd)
@@ -161,8 +167,10 @@
     f = wait_fresh(vm)
     vm.shell_ready(); env = state(vm, "T1")
     _, apps = vm.run("k3s kubectl -n apps get pods --no-headers")
-    record("T1", g == ("committed-boot", "A", 1) and f.startswith("K3S-FRESH ok") and "0/1" in apps,
-           f"gate={g} {f[:90]} apps_not_ready={'0/1' in apps} t={time.time()-t0:.0f}s")
+    _, ver = vm.run("rauc --version; grep bundle-formats /etc/rauc/system.conf; dpkg-query -W rauc 2>&1 | tail -1")
+    v1152 = re.search(r"^rauc v?1\.15\.2\s*$", ver, re.M) is not None
+    record("T1", g == ("committed-boot", "A", 1) and f.startswith("K3S-FRESH ok") and "0/1" in apps and v1152,
+           f"gate={g} {f[:90]} apps_not_ready={'0/1' in apps} rauc_1.15.2={v1152} t={time.time()-t0:.0f}s")
 
     if want("T2"):
         vm.mark("T2 wrong-key bundle")
@@ -171,9 +179,19 @@
         after = vm.run(ENV)[1]
         sig = re.search(r"(?i)signature|verif|certificate", out) is not None
         _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
-        record("T2", rc != 0 and sig and before.split() == after.split() and "none" in pend,
-               f"rc={rc} sig_error={sig} env_unchanged={before.split()==after.split()} marker_written={'none' not in pend}")
+        record("T2", rc != 0 and sig and envkv(before) == envkv(after) != [] and "none" in pend,
+               f"rc={rc} sig_error={sig} env_unchanged={envkv(before)==envkv(after)!=[]} marker_written={'none' not in pend}")
 
+    if want("T11"):
+        vm.mark("T11 plain-format bundle, valid signature, verity-only policy")
+        before = vm.run(ENV)[1]
+        rc, out = install(vm, "plain-good.raucb", 900)
+        after = vm.run(ENV)[1]
+        fmt = "Bundle format 'plain' not allowed" in out
+        _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
+        record("T11", rc != 0 and fmt and envkv(before) == envkv(after) != [] and "none" in pend,
+               f"rc={rc} format_error={fmt} env_unchanged={envkv(before)==envkv(after)!=[]} marker_written={'none' not in pend}")
+
     if want("T3"):
         vm.mark("T3 good update -> B")
         rc, seg = update_and_reboot(vm, "good.raucb")
--- rauc-k3s-gate/scripts/trim-logs.sh
+++ rauc-1152/scripts/trim-logs.sh
@@ -2,7 +2,7 @@
 # Trim a raw serial log to the lines that carry evidence, and mask VM-internal
 # addresses (QEMU user-net 10.0.2.x / fec0:: and any RFC1918) as <vm-private-ip>.
 #   trim-logs.sh <serial.log> > serial-trimmed.log
-grep -a -E '#####|GRUB-RAUC|HEALTH-GATE|BAD-BOOT|BAD-HANG|Kernel panic|watchdog|pre-install: trial|Marking target|Copying image|writing data|LastError|signature|--- state|^ONEMIND_VERSION|^ORDER=|^[AB]_(OK|TRY)=|Booted from|boot status|pending|^(apps|kube-system|onemind-system) ' "$1" \
+grep -a -E '#####|GRUB-RAUC|HEALTH-GATE|BAD-BOOT|BAD-HANG|Kernel panic|watchdog|pre-install: trial|Marking target|Copying image|writing data|LastError|signature|not allowed|rauc 1\.15|bundle-formats|--- state|^ONEMIND_VERSION|^ORDER=|^[AB]_(OK|TRY)=|Booted from|boot status|pending|^(apps|kube-system|onemind-system) ' "$1" \
  | grep -a -v -E 'echo __R|grep -E' \
  | sed -E -e 's/10\.0\.2\.[0-9]+/<vm-private-ip>/g' -e 's/fec0:[0-9a-f:]+/<vm-private-ip>/g' \
          -e 's/(192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]+\.[0-9]+/<vm-private-ip>/g' \
```

Pi 5 gate vs the x86 gate:

```diff
--- guest/onemind-health-gate
+++ pi5/onemind-health-gate
@@ -1,14 +1,15 @@
 #!/bin/bash
-# LAB-rauc-k3s-gate: commit or reject the booted RAUC slot.
+# LAB-rauc-1152 Pi 5 variant of the LAB-rauc-k3s-gate gate: commit or reject the booted RAUC slot.
+# Only change: slot state comes from rpi-tryboot-ab.sh marker files and autoboot.txt instead of grubenv.
 # Modes (decided from the trial marker written by RAUC's pre-install handler):
 #   trial      marker names the booted slot -> fresh checks, STABLE passes in a
 #              row -> mark-good; deadline -> mark-bad + reboot (old slot boots)
 #   fell-back  marker names the other slot -> that trial (or install) failed
 #              before a decision: mark it bad so it is never retried
-#   committed  no marker -> mark-good now (resets GRUB's try counter); check
+#   committed  no marker -> mark-good now; check
 #              k3s for the log only; never roll back a committed OS
 set -u
-GRUBENV=/boot/efi/EFI/BOOT/grubenv
+AB=/mnt/autoboot
 [ -f /etc/default/onemind-health-gate ] && . /etc/default/onemind-health-gate
 TIMEOUT=${ONEMIND_GATE_TIMEOUT:-300}; STABLE=${ONEMIND_GATE_STABLE:-3}; INTERVAL=10
 PENDING=/data/onemind/pending
@@ -16,10 +17,12 @@
 log() { local m="HEALTH-GATE: $(date -u +%T) $*"; echo "$m" >>"$LOG"; echo "$m" >/dev/console; }
 SLOT=$(sed -n 's/.*rauc\.slot=\([A-Z]\).*/\1/p' /proc/cmdline); OTHER=A; [ "$SLOT" = A ] && OTHER=B
 . /etc/onemind-release; VER=$ONEMIND_VERSION
-envget() { grub-editenv "$GRUBENV" list | sed -n "s/^$1=//p"; }
+envget() { case $1 in *_OK) [ -f "$AB/slot-${1%_OK}.good" ] && echo 1 || echo 0 ;; *) echo n/a ;; esac; }
+dtint() { [ -f "/proc/device-tree/chosen/bootloader/$1" ] && printf '%d' "0x$(od "/proc/device-tree/chosen/bootloader/$1" -v -An -t x1 | tr -d ' \n')" || echo "?"; }
+envdump() { echo "$(tr '\n' ' ' < "$AB/autoboot.txt") good=[$(cd "$AB" && ls slot-*.good 2>/dev/null | tr '\n' ' ')] dt_tryboot=$(dtint tryboot) dt_partition=$(dtint partition)"; }
 P=""; PV=""; [ -s "$PENDING" ] && read -r P PV < "$PENDING"
 if [ -z "$P" ]; then MODE=committed; elif [ "$P" = "$SLOT" ]; then MODE=trial; else MODE=fell-back; fi
-log "start slot=$SLOT version=$VER mode=$MODE env=[$(grub-editenv "$GRUBENV" list | tr '\n' ' ')]"
+log "start slot=$SLOT version=$VER mode=$MODE env=[$(envdump)]"
 
 commit() { # mark-good booted; never fail silently (LAB-rauc finding 4)
   local e; if e=$(rauc status mark-good booted 2>&1); then return 0; fi
@@ -39,8 +42,7 @@
   commit && log "RESULT committed-boot slot=$SLOT version=$VER"
   watch_only ;;
 fell-back)
-  why="gate rejected it or install was interrupted"
-  [ "$(envget "${P}_OK")" = 1 ] && why="trial boots used up (crash/hang/power cut) with ${P}_TRY=$(envget "${P}_TRY")"
+  why="install interrupted, gate rejected it, or its one tryboot attempt ended without a decision (crash, hang, watchdog, power cut)"
   rauc status mark-bad other >/dev/null 2>&1
   rm -f "$PENDING"; sync
   commit && log "RESULT fell-back slot=$SLOT version=$VER; slot $P (v$PV) marked bad, never retried ($why)"
```
