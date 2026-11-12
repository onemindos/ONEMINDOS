#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Create the TUF root of trust for one OneMind update channel. OFFLINE ONLY: run it on an
# air-gapped machine at the key ceremony (brief 30 B4.6, K-ROOT; handbook/keys/CEREMONY.md).
# Never in CI: the script refuses when it sees a CI environment.
#
#   scripts/tuf-bootstrap-root.sh rehearse <dir>
#       Throwaway keys + a root in <dir> (a dry run of the ceremony in a VM with networking off).
#   scripts/tuf-bootstrap-root.sh create <dir> <channel> <threshold> <root-key>... -- \
#       <targets.pub> <snapshot.pub> <timestamp.pub>
#       A real root signed by the given root private keys (at least <threshold> of them; with
#       hardware tokens, export-free signing needs a token-backed signer: see os/update/README.md).
#
# Output: <dir>/1.root.json and <dir>/root.json, plus their sha256 and the key ids. Then:
#   1. commit <dir>/root.json as os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json
#      (public; it is what every image trusts),
#   2. store the targets / snapshot / timestamp PRIVATE keys as the GitHub Actions secrets
#      ONEMIND_TUF_TARGETS_KEY / _SNAPSHOT_KEY / _TIMESTAMP_KEY,
#   3. keep the root private keys offline (never a secret, never in the repo).
set -eu
if [ -n "${CI:-}${GITHUB_ACTIONS:-}" ]; then echo "refusing: a TUF root is made offline, never in CI" >&2; exit 1; fi
HERE=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-python3}
"$PY" -c 'import tuf, securesystemslib' 2>/dev/null || {
  echo "needs python-tuf: python3 -m venv V && V/bin/pip install --require-hashes --only-binary :all: -r os/update/requirements-tuf.txt; PYTHON=V/bin/python $0 ..." >&2; exit 1; }
T="$PY -I $HERE/os/update/tuf-repo.py"
if ip route 2>/dev/null | grep -q '^default' || route -n get default >/dev/null 2>&1; then
  echo "WARNING: this machine has a default route; a production root belongs on an air-gapped machine" >&2
fi
cmd=${1:-}; shift || true
case "$cmd" in
rehearse)
  D=$1; umask 077
  $T keygen --out-dir "$D/keys"
  $T init-root --root-key "$D/keys/root.key" --targets-pub "$D/keys/targets.pub" \
    --snapshot-pub "$D/keys/snapshot.pub" --timestamp-pub "$D/keys/timestamp.pub" --out "$D"
  ;;
create)
  D=$1; CH=$2; TH=$3; shift 3
  rk=""; while [ $# -gt 0 ] && [ "$1" != "--" ]; do rk="$rk --root-key $1"; shift; done
  [ "${1:-}" = "--" ] || { echo "missing -- before the online public keys" >&2; exit 2; }
  shift; [ $# -eq 3 ] || { echo "need targets.pub snapshot.pub timestamp.pub" >&2; exit 2; }
  $T init-root $rk --threshold "$TH" --targets-pub "$1" --snapshot-pub "$2" --timestamp-pub "$3" --out "$D"
  echo "channel: $CH -> commit as os/rootfs/layers/base/usr/lib/onemind/tuf/$CH/root.json"
  ;;
*) sed -n '3,22p' "$0"; exit 2 ;;
esac
sha256sum "$D/root.json" 2>/dev/null || shasum -a 256 "$D/root.json"
"$PY" -I -c 'import json,sys
r=json.load(open(sys.argv[1]))["signed"]
for n,role in sorted(r["roles"].items()):
    print(n.ljust(9), "threshold", role["threshold"], "keyids", [k[:16] for k in role["keyids"]])
print("expires", r["expires"])' "$D/root.json"
