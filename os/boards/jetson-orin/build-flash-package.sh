#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Build a OneMind flash package for a Jetson Orin dev kit FROM THE OWNER'S OWN NVIDIA DOWNLOADS,
# on the owner's x86-64 Linux host (NVIDIA's flash tools do not run on a Mac [C-W18-021]).
#
# Why a builder and not an image: NVIDIA's BSP may be redistributed only unmodified, with its
# licence, on NVIDIA hardware [C-LIC-002, C-LIC-003], and a modified Ubuntu rootfs needs
# Canonical's approval [C-LIC-011] (Z-01 open). So OneMind publishes only its own layer
# (make jetson-layer) and this script; the owner downloads NVIDIA's files, and the combined
# rootfs never leaves the owner's machine. Read os/boards/jetson-orin/README.md first.
#
#   sudo os/boards/jetson-orin/build-flash-package.sh --layer <onemind-layer-jetson-orin-V.tar.gz> \
#        --downloads <dir> --work <empty dir> [--fetch] [--l4t 39.2.1|36.5.2] [--role hub|worker|leaf]
#        [--keyring <release-ca.pem>] [--rootfs-size <S>] [--version <V>] [--accept-nvidia-license]
#        [--break k3s] [--flash]
#
# Steps: verify NVIDIA's tarballs against pinned sha256 -> unpack the BSP and sample rootfs ->
# NVIDIA's apply_binaries.sh -> install the OneMind layer -> enable OneMind units -> OneMind A/B
# layout (NVIDIA's + onemind-data) -> layout record -> print (or, with --flash, run) NVIDIA's
# ROOTFS_AB=1 initrd flash. It never runs a fuse-burning command (SB-8).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=os/boards/jetson-orin/pins.sh
. "$HERE/pins.sh"
L4T=39.2.1; LAYER=""; DL=""; WORK=""; FETCH=0; ROLE=""; KEYRING=""; RSIZE=""; VERSION=""; ACCEPT=0; BREAK=""; FLASH=0
TARGET_BOARD=jetson-orin-nano-devkit; EXTDEV=nvme0n1; RETRY=3
die() { echo "build-flash-package: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
  --l4t) L4T=$2; shift 2 ;;            --layer) LAYER=$2; shift 2 ;;
  --downloads) DL=$2; shift 2 ;;       --work) WORK=$2; shift 2 ;;
  --fetch) FETCH=1; shift ;;           --role) ROLE=$2; shift 2 ;;
  --keyring) KEYRING=$2; shift 2 ;;    --rootfs-size) RSIZE=$2; shift 2 ;;
  --version) VERSION=$2; shift 2 ;;    --accept-nvidia-license) ACCEPT=1; shift ;;
  --break) BREAK=$2; shift 2 ;;        --flash) FLASH=1; shift ;;
  *) die "unknown option $1 (see the header of this script)" ;;
  esac
done
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || die "run on an x86-64 Linux host (NVIDIA's flash tools need one)"
[ "$(id -u)" = 0 ] || die "run with sudo (NVIDIA's apply_binaries.sh and flash need root)"
[ -n "$LAYER" ] && [ -n "$DL" ] && [ -n "$WORK" ] || die "--layer, --downloads and --work are required"
case "$ROLE" in ""|hub|worker|leaf) ;; *) die "--role must be hub, worker or leaf" ;; esac
case "$BREAK" in ""|k3s) ;; *) die "--break supports only k3s (LT-JET-01 bad update)" ;; esac
case "$VERSION" in *[!A-Za-z0-9.+_-]*) die "bad --version" ;; esac
pins_for "$L4T"
for t in sha256sum tar python3 openssl systemctl useradd; do command -v "$t" >/dev/null || die "missing host tool: $t"; done

# 1. NVIDIA's files, checked against the pins (os/versions.lock.yaml `jetson:`).
mkdir -p "$DL"
for f in "$L4T_BSP:$L4T_BSP_SHA256" "$L4T_ROOTFS:$L4T_ROOTFS_SHA256" "$L4T_OTA_TOOLS:$L4T_OTA_TOOLS_SHA256"; do
  name=${f%%:*}; sum=${f#*:}
  if [ ! -f "$DL/$name" ]; then
    [ "$FETCH" = 1 ] || die "$DL/$name missing: download it from NVIDIA (README.md) or pass --fetch"
    curl -fL --retry 3 -o "$DL/$name.part" "$L4T_URL/$name" && mv "$DL/$name.part" "$DL/$name"
  fi
  echo "$sum  $DL/$name" | sha256sum -c - || die "$name does not match the pinned sha256"
done
[ -f "$LAYER" ] || die "no layer at $LAYER (make jetson-layer)"
if [ -f "$LAYER.sha256" ]; then (cd "$(dirname "$LAYER")" && sha256sum -c "$(basename "$LAYER").sha256") || die "layer sha256 mismatch"; fi

# 2. A fresh tree: NVIDIA's BSP and sample rootfs, then NVIDIA's own apply_binaries.sh.
[ -e "$WORK" ] && [ -n "$(ls -A "$WORK" 2>/dev/null)" ] && die "--work $WORK is not empty"
mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd)
tar -xpf "$DL/$L4T_BSP" -C "$WORK"
LT="$WORK/Linux_for_Tegra"; R="$LT/rootfs"
tar -xpf "$DL/$L4T_ROOTFS" -C "$R"
(cd "$LT" && ./apply_binaries.sh)

# 3. NVIDIA's hook contract, read from the rootfs we just made (not assumed).
grep -rqs 'user_rootfs_validation.sh' "$R/opt/nvidia/l4t-rootfs-validation-config/" \
  || die "this L4T has no /usr/sbin/user_rootfs_validation.sh hook; the OneMind gate cannot plug in"
VUNIT=$(find "$R/opt/nvidia/l4t-rootfs-validation-config" -maxdepth 1 -name '*validation-config.service' -printf '%f\n')
[ -f "$R/opt/nvidia/l4t-bootloader-config/nv-l4t-bootloader-config.service" ] || die "nv-l4t-bootloader-config.service not found"
[ -e "$R/usr/sbin/user_rootfs_validation.sh" ] && die "the rootfs already has a user_rootfs_validation.sh; refusing to replace it"
missing=""; for c in usr/bin/python3 usr/bin/openssl usr/bin/curl usr/bin/findmnt sbin/blkid sbin/mkfs.ext4 usr/sbin/avahi-daemon; do
  [ -e "$R/$c" ] || [ -e "$R/usr/$c" ] || missing="$missing /$c"
done
[ -z "$missing" ] || die "NVIDIA's rootfs lacks:$missing (OneMind installs no unpinned packages)"

# 4. The OneMind layer.
tar -xzpf "$LAYER" -C "$R" --no-overwrite-dir   # keep NVIDIA's /usr, /etc, ... modes as they are
(cd "$R" && sha256sum --quiet -c usr/lib/onemind/jetson/layer-manifest.txt) || die "layer files do not match its manifest"
[ -n "$VERSION" ] && printf 'ONEMIND_VERSION=%s\n' "$VERSION" > "$R/etc/onemind/release"
VERSION=$(sed -n 's/^ONEMIND_VERSION=//p' "$R/etc/onemind/release")
grep -q '^onemind:' "$R/etc/group"  || groupadd --root "$R" --system --gid 961 onemind
grep -q '^onemind:' "$R/etc/passwd" || useradd --root "$R" --system --uid 961 --gid onemind \
  --home-dir /data/onemind/gateway --no-create-home --shell /usr/sbin/nologin onemind
# onemind-jetson-data and onemind-data-layout have no [Install]: the fstab lines below pull them in.
systemctl --root="$R" enable onemind-firstboot.service k3s.service onemind-local-api.service avahi-daemon.service
grep -q 'OneMind (os/boards/jetson-orin)' "$R/etc/fstab" || cat "$R/etc/onemind/jetson-fstab" >> "$R/etc/fstab"
mkdir -p "$R/data" "$R/etc/rancher/node" "$R/var/lib/rancher" "$R/var/lib/kubelet" "$R/var/lib/cni" "$R/boot/efi"
if [ "$BREAK" = k3s ]; then   # LT-JET-01 step 2: a bad update the gate must reject
  chmod 000 "$R/usr/local/bin/k3s"; echo "WARNING: --break k3s: this rootfs is deliberately broken (test only)"
fi

# 5. Trust root: the OneMind release CA (same root as RAUC). Without --keyring, a throwaway dev CA
#    is made here; its key stays in $WORK/dev-ca on this host and is never published (SB-10).
if [ -z "$KEYRING" ]; then
  mkdir -p "$WORK/dev-ca"; chmod 700 "$WORK/dev-ca"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 365 -subj "/CN=OneMind Jetson dev CA" \
    -keyout "$WORK/dev-ca/ca.key" -out "$WORK/dev-ca/ca.pem" 2>/dev/null
  KEYRING="$WORK/dev-ca/ca.pem"; echo "dev CA: $WORK/dev-ca (sign OTA bundles with it; never publish it)"
fi
install -D -m 644 "$KEYRING" "$R/etc/onemind/keyring.pem"

# 6. First-boot role (docs/leap/core/IMAGES.md §3): the template every image carries; role set if given.
if grep -qE '^[^#]*[[:space:]]/boot/efi[[:space:]]' "$R/etc/fstab"; then
  echo "NOTE: L4T mounts /boot/efi; onemind.conf goes on that partition at first boot via the wizard instead"
else
  install -m 600 "$R/usr/lib/onemind/jetson/onemind.conf.template" "$R/boot/efi/onemind.conf"
  [ -n "$ROLE" ] && printf 'role = %s\n' "$ROLE" >> "$R/boot/efi/onemind.conf"
fi

# 7. Layout: NVIDIA's rootfs A/B file + onemind-data, and the record OTA payloads are checked against.
if [ "$L4T_AB_XML" = UNVERIFIED ]; then
  L4T_AB_XML=""
  for x in "$LT"/tools/kernel_flash/*t234*nvme*rootfs_ab.xml; do
    case "$x" in *enc*) ;; *) [ -f "$x" ] && L4T_AB_XML=tools/kernel_flash/${x##*/} && break ;; esac
  done
  [ -n "$L4T_AB_XML" ] || die "no t234 NVMe rootfs A/B layout in this BSP"
fi
XML=tools/kernel_flash/onemind_t234_nvme_rootfs_ab.xml
python3 -I "$HERE/jetson_layout.py" add-data "$LT/$L4T_AB_XML" "$LT/$XML"
python3 -I "$HERE/jetson_layout.py" record --out "$WORK/jetson-layout.json" --layout-xml "$LT/$XML" \
  --layout-xml-name "$XML" --l4t "$L4T" --target-board "$TARGET_BOARD" --external-device "$EXTDEV" \
  --rootfs-size "${RSIZE:-nvidia-default}" --retry "$RETRY"
install -m 644 "$WORK/jetson-layout.json" "$R/etc/onemind/jetson-layout.json"

# 8. Optional default user (NVIDIA's tool; it needs the owner to accept NVIDIA's EULA, so only on
#    --accept-nvidia-license). Without it, NVIDIA's oem-config asks on the first boot's console.
if [ "$ACCEPT" = 1 ]; then
  PW=$(openssl rand -base64 18)
  (cd "$LT" && ./tools/l4t_create_default_user.sh -u onemind-admin -p "$PW" -n onemind --accept-license)
  umask 077; printf 'user=onemind-admin\npassword=%s\n' "$PW" > "$WORK/default-user.txt"
  echo "default user onemind-admin; password saved once in $WORK/default-user.txt (change it after first login)"
fi

# 9. Flash command (README_initrd_flash.txt "Workflow 4: ROOTFS_AB support and boot from external device").
SOPT=(); [ -n "$RSIZE" ] && SOPT=(-S "$RSIZE")
CMD=(env ROOTFS_AB=1 "ROOTFS_RETRY_COUNT_MAX=$RETRY" ./tools/kernel_flash/l4t_initrd_flash.sh
     --external-device "$EXTDEV" -c "$XML" "${SOPT[@]}" --showlogs "$TARGET_BOARD" external)
python3 -I - "$WORK" "$L4T" "$VERSION" "$LAYER" "$XML" "${CMD[*]}" <<'PY'
import hashlib, json, os, sys
work, l4t, ver, layer, xml, cmd = sys.argv[1:]
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
rec = {"schema": "onemind.io/jetson-flash-package/v1", "l4t": l4t, "onemind_version": ver,
       "layer": os.path.basename(layer), "layer_sha256": h(layer), "layout_xml": xml,
       "layout_record": json.load(open(os.path.join(work, "jetson-layout.json"))), "flash_command": cmd,
       "published": False}
json.dump(rec, open(os.path.join(work, "onemind-jetson-release.json"), "w"), indent=2, sort_keys=True)
PY
echo
echo "OneMind $VERSION on L4T $L4T is ready in $LT (rootfs: $R)."
echo "Validation unit in this L4T: $VUNIT. Record: $WORK/onemind-jetson-release.json"
echo "Put the Jetson in recovery mode (USB-C to this host), then from $LT run:"
echo "  sudo ${CMD[*]}"
if [ "$FLASH" = 1 ]; then (cd "$LT" && "${CMD[@]}"); fi
