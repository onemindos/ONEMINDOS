#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Build the battery's fixtures for one board from a rootfs tar (brief 30 B13; port of the variant
# and bundle steps of evidence/lab/rauc-1152/scripts/build.sh). Runs as root in the tools container:
#   mkfixtures.sh <board> <rootfs.tar> <outdir> [T5|T10]
# Outputs in <outdir>: disk.img (slot A = v1 + test overlay), bundles.img (ext4 "onemind-test"
# holding bundles/*.raucb), seed.img (vm-do: NoCloud seed), t0.json (T0 checks), dev-ca.cert.pem
# (public), SHA256SUMS. Throwaway keys live only in this container's /tmp and are deleted.
set -euo pipefail
BOARD=$1; ROOTFS=$2; OUT=$3; UPTO=${4:-T5}
SRC=$(cd "$(dirname "$0")/../.." && pwd)
ASM=$(sed -n 's/^assembler: *\([^ #]*\).*/\1/p' "$SRC/os/boards/$BOARD/board.yaml")   # board-specific assembler (rpi5), same CLI
A="python3 -I $SRC/${ASM:-os/assemble/assemble.py}"
W=${WORK:-/work/fx-$BOARD}; K=$(mktemp -d /tmp/keys.XXXXXX)
trap 'rm -rf "$K"' EXIT
log() { echo "[mkfixtures $(date -u +%T)] $*"; }
rm -rf "$W"; mkdir -p "$W/bundles" "$OUT"

log "throwaway PKI (dev CA + signer, and a wrong CA); never leaves this container"
for ca in dev wrong; do
  openssl req -x509 -newkey rsa:3072 -nodes -days 7 -sha256 -keyout "$K/$ca-ca.key" -out "$K/$ca-ca.pem" \
    -subj "/O=OneMind DEV/CN=$ca-ca" 2>/dev/null
  openssl req -newkey rsa:3072 -nodes -sha256 -keyout "$K/$ca-signer.key" -out "$K/$ca-signer.csr" \
    -subj "/O=OneMind DEV/CN=$ca-signer" 2>/dev/null
  openssl x509 -req -in "$K/$ca-signer.csr" -CA "$K/$ca-ca.pem" -CAkey "$K/$ca-ca.key" -CAcreateserial \
    -days 7 -sha256 -out "$K/$ca-signer.pem" -extfile <(printf 'keyUsage=critical,digitalSignature\n') 2>/dev/null
done
cp "$K/dev-ca.pem" "$OUT/dev-ca.cert.pem"

log "tree v1 with the test overlay (HW=${HW:-0})"
OVL="--overlay $SRC/test/qemu/overlay"
[ "${HW:-0}" = 1 ] && OVL="$OVL --overlay $SRC/test/qemu/overlay-hw"   # founder kits: autologin on tty1
$A tree --board "$BOARD" --rootfs "$ROOTFS" --work "$W" --version 1 --keyring "$K/dev-ca.pem" $OVL
T=$W/tree
SIZE=$(( ( $(du -s -B1M --apparent-size "$T" | cut -f1) * 13 / 10 + 384 + 63 ) / 64 * 64 ))
setver() { sed -i "s/^ONEMIND_VERSION=.*/ONEMIND_VERSION=\"$1\"/" "$T/usr/lib/os-release"; }
k3sargs() { printf 'K3S_EXTRA_ARGS=%s\n' "$1" > "$T/etc/default/k3s"; }
ext4() { $A ext4 --work "$W" --out "$W/$1.ext4" --size-mib "$SIZE" >/dev/null; }
bundle() { # $1 ext4 name, $2 version, $3 out name, $4 key prefix, $5 format
  $A bundle --board "$BOARD" --system "$W/$1.ext4" --version "$2" --cert "$K/$4-signer.pem" \
    --key "$K/$4-signer.key" --out "$W/bundles/$3.raucb" --format "${5:-verity}" >/dev/null
  log "bundle $3 (v$2, $4 key, ${5:-verity})"
}

log "slot A image v1 and the disk"
ext4 v1
$A disk --board "$BOARD" --work "$W" --system "$W/v1.ext4" --out "$OUT/disk.img"
rm -f "$W/v1.ext4"

log "variants"
setver 2; ext4 good
bundle good 2 good dev; bundle good 2 wrong-key wrong; bundle good 2 plain-good dev plain
rm -f "$W/good.ext4"
setver 3; k3sargs "--onemind-test-unknown-flag"; ext4 v; bundle v 3 bad-k3s dev     # k3s exits at start
setver 4; k3sargs "--disable-agent";              ext4 v; bundle v 4 bad-noagent dev # API up, no kubelet
k3sargs ""
if [ "$UPTO" != T5 ]; then
  mv "$T/sbin/init" "$T/sbin/init.real"
  printf '#!/bin/sh\necho "BAD-BOOT: broken init exiting"\nexit 1\n' > "$T/sbin/init"; chmod 755 "$T/sbin/init"
  setver 5; ext4 v; bundle v 5 bad-boot dev                                          # kernel panic
  install -m 755 "$SRC/test/qemu/bad-hang-init" "$T/sbin/init"
  setver 6; ext4 v; bundle v 6 bad-hang dev                                          # hang, watchdog armed
  rm -f "$T/sbin/init"; mv "$T/sbin/init.real" "$T/sbin/init"
  cp -a "$T/usr/lib/onemind/onemind-k3s-check" "$W/k3s-check.real"
  install -m 755 "$SRC/test/qemu/overlay-naive/usr/lib/onemind/onemind-k3s-check" "$T/usr/lib/onemind/"
  setver 7; k3sargs "--disable-agent"; ext4 v; bundle v 7 naive-noagent dev          # T10 observation
  install -m 755 "$W/k3s-check.real" "$T/usr/lib/onemind/onemind-k3s-check"; k3sargs ""
fi
rm -f "$W/v.ext4"

log "T0 checks"
python3 -I - "$T" "$W/bundles" "$K/dev-ca.pem" "$SRC/os/versions.lock.yaml" "$OUT/t0.json" "$BOARD" <<'PY'
import hashlib, json, re, subprocess, sys, yaml
tree, bdir, ca, lock, out, board = sys.argv[1:]
lk = yaml.safe_load(open(lock)); checks = {}
def sh(*c, root=None):
    r = subprocess.run((["chroot", root] if root else []) + list(c), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr
_, v = sh("/usr/bin/rauc", "--version", root=tree)
checks["rauc_in_image_1.15.2"] = bool(re.fullmatch(r"rauc v?1\.15\.2", v.strip()))
rc, _ = sh("dpkg-query", "-W", "rauc", root=tree); rc2, _ = sh("dpkg-query", "-W", "rauc-service", root=tree)
checks["distro_rauc_absent"] = rc != 0 and rc2 != 0
arch = yaml.safe_load(open(f"{lock.rsplit('/', 1)[0]}/boards/{board}/board.yaml"))["arch"]
want = lk["k3s"][arch]
binsha = hashlib.sha256(open(f"{tree}/usr/local/bin/k3s", "rb").read()).hexdigest()
imgsha = hashlib.sha256(open(f"{tree}/usr/lib/onemind/k3s-airgap-images.tar.zst", "rb").read()).hexdigest()
checks["k3s_sha256_pinned"] = binsha in want.values() and imgsha in want.values()
info = {}
import os
for f in sorted(os.listdir(bdir)):
    rc, o = sh("rauc", "info", f"--keyring={ca}", os.path.join(bdir, f))
    fmt = re.search(r"Bundle Format:\s+(\S+)", o)
    info[f] = {"rc": rc, "format": fmt.group(1) if fmt else None, "verified": "Verified" in o and rc == 0}
checks["wrong_key_rejected"] = info.get("wrong-key.raucb", {}).get("rc", 0) != 0
checks["verity_bundles_verity"] = all(v["format"] == "verity" and v["verified"] for k, v in info.items()
                                      if k not in ("wrong-key.raucb", "plain-good.raucb"))
checks["plain_good_is_plain_and_signed"] = info.get("plain-good.raucb", {}).get("format") == "plain" and info["plain-good.raucb"]["verified"]
checks["no_naive_gate_in_v1"] = "NAIVE" not in open(f"{tree}/usr/lib/onemind/onemind-k3s-check").read()
res = {"test": "T0", "board": board, "pass": all(checks.values()), "checks": checks, "bundles": info,
       "rauc_version": v.strip(), "k3s_sha256": {"binary": binsha, "airgap": imgsha}}
json.dump(res, open(out, "w"), indent=2); print(json.dumps(res["checks"], indent=1)); print("T0", "PASS" if res["pass"] else "FAIL")
PY

log "bundles disk (label onemind-test)"
BSIZE=$(( $(du -s -B1M "$W/bundles" | cut -f1) + 256 ))
mkdir -p "$W/bdisk"; mv "$W/bundles" "$W/bdisk/bundles"
mke2fs -q -t ext4 -L onemind-test -d "$W/bdisk" "$OUT/bundles.img" "${BSIZE}M"

if grep -q '^cloud: true' "$SRC/os/boards/$BOARD/board.yaml"; then
  log "NoCloud seed (TC1): a throwaway SSH public key; the private key is discarded"
  ssh-keygen -q -t ed25519 -N "" -C onemind-tc1 -f "$K/tc1"
  printf 'instance-id: onemind-tc1\nlocal-hostname: onemind\n' > "$W/meta-data"
  printf '#cloud-config\nssh_authorized_keys:\n  - %s\n' "$(cat "$K/tc1.pub")" > "$W/user-data"
  rm -f "$OUT/seed.img"; mkfs.fat -n CIDATA -C "$OUT/seed.img" 2048 >/dev/null
  mcopy -i "$OUT/seed.img" "$W/meta-data" "$W/user-data" ::/
fi
rm -rf "$W"
( cd "$OUT" && sha256sum disk.img bundles.img dev-ca.cert.pem $(ls seed.img 2>/dev/null) > SHA256SUMS )
log "done: $(ls "$OUT" | tr '\n' ' ')"
