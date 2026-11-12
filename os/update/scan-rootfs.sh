#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Scan one extracted rootfs (poc-v0 §10.1, brief 30 D-B1.5): post-build security check, OpenVEX from
# the Debian tracker, SBOM (syft, SPDX JSON), CVE scan (Trivy with the VEX applied), ClamAV with
# freshly updated signatures, then scan-gate.py. Exit 1 when the gate fails.
#   TRACKER=tracker.json BIN=<dir with trivy, syft> \
#     os/update/scan-rootfs.sh <rootfs-dir> <board> <outdir> <file-prefix>
# Writes <prefix>.check.json .vex.json .spdx.json .cve-report.json (Trivy JSON) .clamav.log .gate.json
set -eu
RF=$1; BOARD=$2; OUT=$3; P=$4
: "${TRACKER:?}" "${BIN:?}"
U=$(cd "$(dirname "$0")" && pwd)
LOCK="$U/../versions.lock.yaml"
CLAMAV=$(sed -n 's/^ *clamav_image: *//p' "$LOCK")
[ -n "$CLAMAV" ] || { echo "no tools.clamav.clamav_image pin" >&2; exit 1; }
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
python3 -I "$U/check-security.py" --packages "$RF/usr/lib/onemind/packages.txt" --status "$RF/var/lib/dpkg/status" \
  --tracker "$TRACKER" --out "$OUT/$P.check.json"
python3 -I "$U/debian-vex.py" --tracker "$TRACKER" --status "$RF/var/lib/dpkg/status" --id-suffix "$BOARD" \
  --out "$OUT/$P.vex.json"
"$BIN/syft" scan "dir:$RF" --quiet --source-name "onemind-$BOARD" -o "spdx-json=$OUT/$P.spdx.json"
"$BIN/trivy" rootfs --quiet --scanners vuln --pkg-types os --vex "$OUT/$P.vex.json" --show-suppressed \
  --format json --output "$OUT/$P.cve-report.json" "$RF"
# Trivy records local paths (the rootfs dir, the VEX file); the report is published, so drop them.
sed -i -e "s#$RF#/rootfs#g" -e "s#$OUT/##g" "$OUT/$P.cve-report.json"
# ClamAV: fresh signatures in the container, the rootfs mounted read-only. Big files are scanned up
# to 1 GiB (the k3s air-gap image tarball is the largest file in the tree).
docker run --rm --user 0 --network host -v "$RF":/scan:ro --entrypoint /bin/sh "$CLAMAV" -c \
  'freshclam --stdout --quiet && clamscan --version && clamscan -r -i --stdout --max-filesize=1024M --max-scansize=2048M /scan' \
  > "$OUT/$P.clamav.log" 2>&1 || true   # clamscan exits 1 on a hit; scan-gate.py reads the summary
python3 -I "$U/scan-gate.py" --trivy "$OUT/$P.cve-report.json" --clamav "$OUT/$P.clamav.log" \
  --check "$OUT/$P.check.json" --board "$BOARD" --out "$OUT/$P.gate.json"
