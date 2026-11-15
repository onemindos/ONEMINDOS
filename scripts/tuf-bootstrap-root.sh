#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Create the TUF root of trust for one OneMind update channel. OFFLINE ONLY: run it on an
# air-gapped machine at the key ceremony (decision D-010; runbook os/update/CEREMONY.md, printed
# checklist os/update/CEREMONY-CHECKLIST.md). Never in CI: the script refuses when it sees a CI
# environment. D-010: three root keys, each on its own encrypted USB stick, any 2 of the 3 sign.
#
#   scripts/tuf-bootstrap-root.sh rehearse <dir>
#       The whole ceremony on THROWAWAY keys in <dir> (do it in a VM or container with networking
#       off): three root keys, 2-of-3 signing with one holder absent, the online keys, the
#       inspection, then a test release signed and checked as a box would. Passphrase is a fixed
#       throwaway one. Nothing in <dir> is ever used for real.
#   scripts/tuf-bootstrap-root.sh root-key <stick-dir> <name>
#       One root key, passphrase-protected (you type the passphrase twice). Run once per holder,
#       with that holder's encrypted stick mounted at <stick-dir>. Writes <name>.key (private,
#       stays on the stick) and <name>.pub (public: copy it to the signing machine).
#   scripts/tuf-bootstrap-root.sh online-keys <dir>
#       The three ONLINE keys (targets, snapshot, timestamp) the release pipeline signs with.
#       Plain PEM, because CI needs them as secrets; they are never root keys.
#   scripts/tuf-bootstrap-root.sh create <dir> <channel> <threshold> <root-key-or-pub>... -- \
#       <targets.pub> <snapshot.pub> <timestamp.pub>
#       The real root. Every root-key argument ending in .pub is a holder who is not present (their
#       key is trusted, they do not sign); every other argument is a private root key that signs
#       (you type its passphrase). At least <threshold> must sign. Refuses to overwrite a root.
#   scripts/tuf-bootstrap-root.sh check <dir> <threshold> <root-keys>
#       Reads <dir>/root.json as a box would and prints the sheet to read aloud and print:
#       sha256, thresholds, key ids, expiry. Exit 1 on any problem.
#
# Output of create: <dir>/1.root.json and <dir>/root.json, then run check. Then:
#   1. commit <dir>/root.json as os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json
#      (public; it is what every image trusts),
#   2. store the targets / snapshot / timestamp PRIVATE keys as the GitHub Actions secrets
#      ONEMIND_TUF_TARGETS_KEY / _SNAPSHOT_KEY / _TIMESTAMP_KEY (os/update/CEREMONY.md step 9),
#   3. keep the root private keys offline (never a secret, never in the repo).
# The root expires after a year (channel.json): put the renewal date in a calendar.
set -eu
if [ -n "${CI:-}${GITHUB_ACTIONS:-}" ]; then echo "refusing: a TUF root is made offline, never in CI" >&2; exit 1; fi
HERE=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-python3}
"$PY" -c 'import tuf, securesystemslib' 2>/dev/null || {
  echo "needs python-tuf: python3 -m venv V && V/bin/pip install --require-hashes --only-binary :all: -r os/update/requirements-tuf.txt; PYTHON=V/bin/python $0 ..." >&2; exit 1; }
tuf() { "$PY" -I "$HERE/os/update/tuf-repo.py" "$@"; }   # quoted: a stick mounted at a path with spaces works
if ip route 2>/dev/null | grep -q '^default' || route -n get default >/dev/null 2>&1; then
  echo "WARNING: this machine has a default route; a production root belongs on an air-gapped machine" >&2
fi
cmd=${1:-}; shift || true
umask 077
case "$cmd" in
rehearse)
  D=$1
  [ ! -e "$D" ] || { echo "refusing: $D exists; rehearse into a new directory" >&2; exit 2; }
  export ONEMIND_TUF_PASSPHRASE="rehearsal-throwaway-passphrase"
  echo "== REHEARSAL: throwaway keys only; nothing here is ever used for real" >&2
  for h in holder-a holder-b holder-c; do tuf keygen --out-dir "$D/sticks/$h" --roles root --encrypt; done
  tuf keygen --out-dir "$D/online" --roles targets,snapshot,timestamp
  # Holder C is not at the ceremony: only their PUBLIC key is trusted. Two holders sign (2-of-3).
  tuf init-root --root-key "$D/sticks/holder-a/root.key" --root-key "$D/sticks/holder-b/root.key" \
    --root-pub "$D/sticks/holder-c/root.pub" --threshold 2 --targets-pub "$D/online/targets.pub" \
    --snapshot-pub "$D/online/snapshot.pub" --timestamp-pub "$D/online/timestamp.pub" --out "$D/out"
  tuf inspect --root "$D/out/root.json" --expect-threshold 2 --expect-root-keys 3
  # What the pipeline will do with it: sign a test release with the online keys, check it as a box would.
  mkdir "$D/rel"
  printf rehearsal >"$D/rel/onemind-vm-0.0.0.raucb"; printf '{}' >"$D/rel/onemind-vm-0.0.0.spdx.json"
  printf '{}' >"$D/rel/onemind-vm-0.0.0.cve-report.json"
  printf '{"board":"vm","version":"0.0.0","compatible":"onemind-vm","snapshot":"20261115T000000Z","security":true,"dry_run":false,"files":{"bundle":"onemind-vm-0.0.0.raucb","sbom":"onemind-vm-0.0.0.spdx.json","cve_report":"onemind-vm-0.0.0.cve-report.json"}}' >"$D/rel/release-vm-0.0.0.json"
  tuf build --repo "$D/channel" --root "$D/out/root.json" --release "$D/rel/release-vm-0.0.0.json" \
    --targets-key "$D/online/targets.key" --snapshot-key "$D/online/snapshot.key" \
    --timestamp-key "$D/online/timestamp.key" >/dev/null
  tuf verify --repo "$D/channel" --root "$D/out/root.json"
  echo "== REHEARSAL PASSED: 2-of-3 root, online keys, a signed release verified. Throwaway keys are in $D: delete it." >&2
  D="$D/out"
  ;;
root-key)
  D=$1; N=$2
  tuf keygen --out-dir "$D" --roles "$N" --encrypt
  echo "wrote $D/$N.key (private, stays on this stick) and $D/$N.pub (public: copy to the signing machine)" >&2
  exit 0
  ;;
online-keys)
  D=$1
  tuf keygen --out-dir "$D" --roles targets,snapshot,timestamp
  echo "wrote targets/snapshot/timestamp .key (private: GitHub secrets, then delete) and .pub (for create)" >&2
  exit 0
  ;;
create)
  D=$1; CH=$2; TH=$3; shift 3
  n=0; for a in "$@"; do [ "$a" = "--" ] && break; n=$((n + 1)); done
  [ "$n" -lt $# ] || { echo "missing -- before the online public keys" >&2; exit 2; }
  # Each root-key argument moves to the end of the list as --root-pub (a .pub: a holder not
  # present) or --root-key (a private key that signs). Quoted, so paths with spaces survive.
  i=0; while [ "$i" -lt "$n" ]; do
    a=$1; shift
    case "$a" in *.pub) set -- "$@" --root-pub "$a" ;; *) set -- "$@" --root-key "$a" ;; esac
    i=$((i + 1)); done
  shift   # the --
  [ $# -ge 3 ] || { echo "need targets.pub snapshot.pub timestamp.pub" >&2; exit 2; }
  tp=$1; sp=$2; mp=$3; shift 3
  tuf init-root "$@" --threshold "$TH" --targets-pub "$tp" --snapshot-pub "$sp" --timestamp-pub "$mp" --out "$D"
  echo "channel: $CH -> commit as os/rootfs/layers/base/usr/lib/onemind/tuf/$CH/root.json"
  ;;
check)
  D=$1; TH=$2; NK=$3
  tuf inspect --root "$D/root.json" --expect-threshold "$TH" --expect-root-keys "$NK"
  exit 0
  ;;
*) sed -n '3,34p' "$0"; exit 2 ;;
esac
sha256sum "$D/root.json" 2>/dev/null || shasum -a 256 "$D/root.json"
"$PY" -I -c 'import json,sys
r=json.load(open(sys.argv[1]))["signed"]
for n,role in sorted(r["roles"].items()):
    print(n.ljust(9), "threshold", role["threshold"], "keyids", [k[:16] for k in role["keyids"]])
print("expires", r["expires"])' "$D/root.json"
