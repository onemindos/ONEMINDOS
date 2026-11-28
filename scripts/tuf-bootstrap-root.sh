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
#   scripts/tuf-bootstrap-root.sh token-pub <hsm:id?label=L> <out.pub>
#       A root key that lives on a hardware token (YubiKey PIV, or any PKCS#11 token; ECDSA P-256, made
#       ON the token): writes its public key. $PYKCS11LIB names the token's PKCS#11 module; the token's
#       PIN is typed at a no-echo prompt. See os/update/CEREMONY.md "Rotate the root onto hardware keys".
#   scripts/tuf-bootstrap-root.sh yubikey-key <dir> <name> [<serial>]
#       ONE holder's root key made ON their YubiKey (PIV slot 9c, ECDSA P-256, PIN policy always, touch
#       policy always; ykman asks for the management key or PIN itself). Then the device's attestation is
#       checked (the key was made on it and cannot leave it, on the YubiKey with that serial) and only then
#       is <dir>/<name>.pub written; a failed check leaves no .pub and moves the evidence to
#       <dir>/<name>-attestation-FAILED/. Needs ykman, PYKCS11LIB=<path to libykcs11> and
#       YUBICO_PIV_CA=<Yubico's PIV attestation CA file>: without the CA the attestation proves nothing, so
#       it is refused. The one exception is the spare trial: <name> "spare" with
#       ONEMIND_ATTEST_WITHOUT_CA=spare-trial, recorded in <dir>/spare-NO-CA-RECORD.txt.
#       UNVERIFIED on real hardware: try it on a spare YubiKey first (os/update/CEREMONY.md).
#   scripts/tuf-bootstrap-root.sh token-keygen <hsm:id?label=L>
#       A root key made ON any other PKCS#11 token (never extractable, PIN for every signature).
#   scripts/tuf-bootstrap-root.sh rehearse-tokens <dir>
#       The YubiKey ceremony on THROWAWAY SoftHSM tokens (software tokens that speak the same PKCS#11):
#       three token keys, the same create/check commands, 2-of-3 signing by two tokens, a signed test
#       release checked as a box would, then a renewal by the other two tokens with one token alone refused.
#       Needs softhsm2. Only the token and the key-making tool differ from the real run.
#   scripts/tuf-bootstrap-root.sh rotate-root <root.json> <dir> <channel> <threshold> <old-key>... -- <new-key-or-pub>...
#       The next root: signed by <old-key>... (private keys of the CURRENT root; enough of them to meet
#       its threshold) AND by the new private keys (file or hsm:id?label=L), while every new key ending
#       in .pub is trusted without signing. New threshold <threshold>; at least that many new keys must
#       sign. Online keys stay. Writes <dir>/<N+1>.root.json and <dir>/root.json; refuses to overwrite.
#   scripts/tuf-bootstrap-root.sh rehearse-rotate <dir>
#       The rehearsal of the whole thing on throwaway file keys: v1 root, then v2 signed by 2 old + 2
#       new keys, then a release checked by a client that trusts only v1.
#   scripts/tuf-bootstrap-root.sh check <dir> <threshold> <root-keys> [<previous-root.json>]
#       Reads <dir>/root.json as a box would and prints the sheet to read aloud and print:
#       sha256, thresholds, key ids, expiry. Exit 1 on any problem.
#
#   scripts/tuf-bootstrap-root.sh renew <current-root.json> <out-dir> <root-key>...
#       RENEW the root before it expires (365 days; os/update/CEREMONY.md "Renewing the root"): version
#       N+1 with the same keys and a new expiry, signed by the private root keys you give (at least the
#       threshold, each one a different holder; you type each passphrase). Checks that a box holding
#       version N accepts it, then prints the same sheet as check. Refuses to overwrite.
#   scripts/tuf-bootstrap-root.sh rehearse-renewal <dir>
#       The ceremony AND a renewal on throwaway keys in <dir> (networking off): a different pair of
#       holders signs the renewal, one holder alone is refused, and a box that trusts only version 1
#       follows the chain to version 2.
#
# Output of create: <dir>/1.root.json and <dir>/root.json, then run check. Then:
#   1. commit <dir>/root.json as os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json
#      (public; it is what every image trusts),
#   2. store the targets / snapshot / timestamp PRIVATE keys as secrets of the GitHub Environment tuf-signing (main only):
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
# A PIN in the environment is for SoftHSM rehearsals and tests only (rehearse-tokens sets its own throwaway
# one). A real token's PIN is typed at the no-echo prompt. tuf-repo.py refuses it too.
if [ -n "${ONEMIND_TUF_PIN:-}" ] && [ "$cmd" != rehearse-tokens ]; then
  case "$(basename "${PYKCS11LIB:-none}")" in
    libsofthsm2*) ;;
    *) echo "refusing: ONEMIND_TUF_PIN is set, but it is for SoftHSM rehearsals and tests only. Unset it; a real PIN is typed at the prompt." >&2; exit 1 ;;
  esac
fi
# What the pipeline will do with a new root: sign a test release with the online keys of $1/online and
# check it as a box would, against $1/out/root.json. Throwaway files only.
release_proof() {
  mkdir "$1/rel"
  printf rehearsal >"$1/rel/onemind-vm-0.0.0.raucb"; printf '{}' >"$1/rel/onemind-vm-0.0.0.spdx.json"
  printf '{}' >"$1/rel/onemind-vm-0.0.0.cve-report.json"
  printf '{"board":"vm","version":"0.0.0","compatible":"onemind-vm","snapshot":"20261115T000000Z","security":true,"dry_run":false,"files":{"bundle":"onemind-vm-0.0.0.raucb","sbom":"onemind-vm-0.0.0.spdx.json","cve_report":"onemind-vm-0.0.0.cve-report.json"}}' >"$1/rel/release-vm-0.0.0.json"
  tuf build --repo "$1/channel" --root "$1/out/root.json" --release "$1/rel/release-vm-0.0.0.json" \
    --targets-key "$1/online/targets.key" --snapshot-key "$1/online/snapshot.key" \
    --timestamp-key "$1/online/timestamp.key" >/dev/null
  tuf verify --repo "$1/channel" --root "$1/out/root.json"
}
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
  release_proof "$D"
  echo "== REHEARSAL PASSED: 2-of-3 root, online keys, a signed release verified. Throwaway keys are in $D: delete it." >&2
  D="$D/out"
  ;;
rehearse-renewal)
  D=$1
  [ ! -e "$D" ] || { echo "refusing: $D exists; rehearse into a new directory" >&2; exit 2; }
  export ONEMIND_TUF_PASSPHRASE="rehearsal-throwaway-passphrase"
  mkdir -p "$D"
  sh "$0" rehearse "$D/first" >/dev/null || { echo "the ceremony rehearsal failed" >&2; exit 1; }
  echo "== REHEARSAL (renewal): throwaway keys only" >&2
  # One holder alone must be refused, and nothing may be written.
  if tuf renew-root --current "$D/first/out/root.json" --root-key "$D/first/sticks/holder-c/root.key" --out "$D/refused" 2>/dev/null; then
    echo "FAIL: a renewal signed by one holder was accepted" >&2; exit 1
  fi
  [ ! -e "$D/refused/root.json" ] || { echo "FAIL: a refused renewal left a file" >&2; exit 1; }
  # Holders B and C renew (A is absent this time).
  tuf renew-root --current "$D/first/out/root.json" --root-key "$D/first/sticks/holder-b/root.key" \
    --root-key "$D/first/sticks/holder-c/root.key" --out "$D/renewed"
  tuf inspect --root "$D/renewed/root.json" --expect-threshold 2 --expect-root-keys 3
  # A box that trusts only version 1 refreshes against the channel plus 2.root.json.
  cp -R "$D/first/channel" "$D/channel"; cp "$D/renewed/2.root.json" "$D/channel/2.root.json"
  tuf verify --repo "$D/channel" --root "$D/first/out/root.json"
  echo "== REHEARSAL PASSED: root v2 signed by B and C, one holder refused, a box on v1 follows the chain. Throwaway keys are in $D: delete it." >&2
  exit 0
  ;;
renew)
  CUR=$1; D=$2; shift 2
  [ $# -ge 1 ] || { echo "give at least the threshold's worth of private root keys" >&2; exit 2; }
  # Each private key becomes --root-key <path>; quoted, so a stick mounted at a path with spaces works.
  i=0; n=$#; while [ "$i" -lt "$n" ]; do a=$1; shift; set -- "$@" --root-key "$a"; i=$((i + 1)); done
  tuf renew-root --current "$CUR" "$@" --out "$D"
  echo "commit $D/root.json as os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json and publish $D/*.root.json beside the older ones"
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
token-pub)
  tuf token-pub --key "$1" --out "$2"
  exit 0
  ;;
token-keygen)
  tuf token-keygen --key "$1" --pin-always
  exit 0
  ;;
yubikey-key)
  D=$1; N=$2; SER=${3:-}
  command -v ykman >/dev/null 2>&1 || { echo "needs ykman (YubiKey Manager), installed BEFORE going offline" >&2; exit 1; }
  [ -n "${PYKCS11LIB:-}" ] || { echo "set PYKCS11LIB to Yubico's PKCS#11 module (libykcs11.so / libykcs11.dylib)" >&2; exit 1; }
  if [ -z "$SER" ]; then
    SER=$(ykman list --serials)
    [ "$(printf '%s\n' "$SER" | grep -c .)" = 1 ] || { echo "plug in exactly ONE YubiKey (seen: $(echo "$SER" | tr "\n" " "))" >&2; exit 2; }
  fi
  case "$SER" in *[!0-9]*|"") echo "the YubiKey serial must be digits" >&2; exit 2 ;; esac
  # Yubico's CA is checked BEFORE the device is touched: without it the attestation proves nothing (any
  # software can mint an f9-style certificate for an imported key).
  CAARG="--ca"; CA=${YUBICO_PIV_CA:-}
  if [ -z "$CA" ]; then
    if [ "${ONEMIND_ATTEST_WITHOUT_CA:-}" = spare-trial ] && [ "$N" = spare ]; then
      CAARG="--no-ca-spare-trial"
    else
      echo "refusing: set YUBICO_PIV_CA to Yubico's PIV attestation CA (downloaded and compared before going offline;" >&2
      echo "  os/update/CEREMONY.md). Without it the attestation proves nothing. Only the spare trial may skip it:" >&2
      echo "  name it 'spare' and set ONEMIND_ATTEST_WITHOUT_CA=spare-trial (recorded; that key never goes into a root)." >&2
      exit 2
    fi
  elif [ ! -s "$CA" ]; then
    echo "refusing: YUBICO_PIV_CA=$CA is not a readable, non-empty file" >&2; exit 2
  fi
  for f in "$D/$N.pub" "$D/$N-attest.pem" "$D/$N-f9.pem" "$D/$N-ykman.pub" "$D/$N-attestation-FAILED"; do
    [ ! -e "$f" ] || { echo "refusing to overwrite $f (use a new folder)" >&2; exit 2; }; done
  # Slot-in-use check, fail closed: two independent questions, and any unexpected answer refuses.
  # 1) `piv keys info 9c` exits 0 when a key is there; its "no key" error is the only accepted failure.
  # 2) `piv info` must be readable, and must not list a key or certificate in slot 9C.
  KI=$(ykman --device "$SER" piv keys info 9c 2>&1); KI_RC=$?
  if [ "$KI_RC" -eq 0 ]; then
    echo "refusing: YubiKey $SER already holds a key in slot 9c. Never replace a root key by accident; reset only a spare." >&2; exit 2
  fi
  case "$KI" in
    *[Nn]o\ key*|*[Nn]o\ private\ key*|*[Nn]o\ data*|*[Nn]ot\ found*|*[Ee]mpty*) ;;
    *) echo "refusing: could not tell whether slot 9c of YubiKey $SER is empty (ykman said: $KI). Fix that and run again." >&2; exit 2 ;;
  esac
  if ! PI=$(ykman --device "$SER" piv info 2>&1); then
    echo "refusing: 'ykman piv info' failed for YubiKey $SER, so slot 9c cannot be checked: $PI" >&2; exit 2
  fi
  if printf '%s\n' "$PI" | grep -Eiq 'slot[[:space:]]+9c|\(9c\)|^[[:space:]]*9c([[:space:]]|:)'; then
    echo "refusing: 'ykman piv info' lists something in slot 9c of YubiKey $SER. Never replace a root key by accident." >&2; exit 2
  fi
  mkdir -p "$D"
  if [ "$CAARG" = --no-ca-spare-trial ]; then
    printf 'SPARE TRIAL WITHOUT YUBICO CA\ndate: %s\nYubiKey serial: %s\nThe attestation was NOT checked against Yubico'"'"'s CA. This key must never go into a real root.\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SER" >"$D/spare-NO-CA-RECORD.txt"
    echo "WARNING: spare trial WITHOUT Yubico's CA (recorded in $D/spare-NO-CA-RECORD.txt)" >&2
  fi
  echo "== YubiKey $SER: making the root key ON the device (slot 9c, P-256, PIN always, touch always)" >&2
  echo "   ykman asks for the management key (or the PIN, if the management key is PIN-protected). Touch the key when it blinks." >&2
  ykman --device "$SER" piv keys generate --algorithm ECCP256 --pin-policy ALWAYS --touch-policy ALWAYS 9c "$D/$N-ykman.pub"
  ykman --device "$SER" piv certificates generate --subject "CN=OneMind root $N" 9c "$D/$N-ykman.pub"
  ykman --device "$SER" piv keys attest 9c "$D/$N-attest.pem"
  ykman --device "$SER" piv certificates export f9 "$D/$N-f9.pem"
  # The public key is written under a temporary name and only becomes <name>.pub once the attestation
  # passed: a key that failed it must never look like a usable holder key.
  T="$D/.$N.pub.unattested"; rm -f "$T"
  tuf token-pub --key "hsm:2?yubikey=$SER" --out "$T"
  if ! "$PY" -I "$HERE/os/update/piv-attest.py" --pub "$T" --attestation "$D/$N-attest.pem" --chain "$D/$N-f9.pem" \
      --serial "$SER" $CAARG ${CA:+"$CA"}; then
    rm -f "$T"
    mkdir "$D/$N-attestation-FAILED"
    mv "$D/$N-attest.pem" "$D/$N-f9.pem" "$D/$N-ykman.pub" "$D/$N-attestation-FAILED/"
    echo "STOP: the attestation of YubiKey $SER FAILED (message above). No $D/$N.pub was written; the evidence is in" >&2
    echo "  $D/$N-attestation-FAILED/. Do not use this YubiKey for a root key; ask before doing anything else with it." >&2
    exit 1
  fi
  mv "$T" "$D/$N.pub"
  echo "wrote $D/$N.pub (public) and the attestation files; the private key exists only on YubiKey $SER: hsm:2?yubikey=$SER" >&2
  exit 0
  ;;
rehearse-tokens)
  D=$1
  [ ! -e "$D" ] || { echo "refusing: $D exists; rehearse into a new directory" >&2; exit 2; }
  U=$(command -v softhsm2-util || true)
  [ -n "$U" ] || { echo "needs SoftHSM (apt-get install softhsm2 / brew install softhsm)" >&2; exit 1; }
  L=${SOFTHSM2_LIB:-}
  for c in /usr/lib/softhsm/libsofthsm2.so /usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so \
           /usr/lib/aarch64-linux-gnu/softhsm/libsofthsm2.so /usr/local/lib/softhsm/libsofthsm2.so \
           /opt/homebrew/lib/softhsm/libsofthsm2.so; do [ -n "$L" ] || { [ -e "$c" ] && L=$c; }; done
  [ -n "$L" ] || { echo "cannot find libsofthsm2.so; set SOFTHSM2_LIB" >&2; exit 1; }
  echo "== REHEARSAL WITH TOKENS: three throwaway SoftHSM tokens; nothing here is ever used for real" >&2
  mkdir -p "$D/softhsm/tokens" "$D/pubs"
  printf 'directories.tokendir = %s\nobjectstore.backend = file\nlog.level = ERROR\n' "$D/softhsm/tokens" >"$D/softhsm/softhsm2.conf"
  export SOFTHSM2_CONF="$D/softhsm/softhsm2.conf" PYKCS11LIB="$L" ONEMIND_TUF_PIN=123456   # throwaway PIN, rehearsal only
  for h in a b c; do "$U" --init-token --free --label "onemind-rehearsal-$h" --so-pin 87654321 --pin 123456 >/dev/null; done
  for h in a b c; do
    sh "$0" token-keygen "hsm:2?label=onemind-rehearsal-$h"           # the YubiKey run: yubikey-key (ykman)
    sh "$0" token-pub "hsm:2?label=onemind-rehearsal-$h" "$D/pubs/$h.pub"
  done
  tuf keygen --out-dir "$D/online" --roles targets,snapshot,timestamp
  # From here on, the same commands as the real ceremony: two tokens sign, holder C is trusted by public key.
  sh "$0" create "$D/out" security 2 "hsm:2?label=onemind-rehearsal-a" "hsm:2?label=onemind-rehearsal-b" "$D/pubs/c.pub" -- \
    "$D/online/targets.pub" "$D/online/snapshot.pub" "$D/online/timestamp.pub" >/dev/null
  sh "$0" check "$D/out" 2 3 >/dev/null
  release_proof "$D"
  if sh "$0" renew "$D/out/root.json" "$D/refused" "hsm:2?label=onemind-rehearsal-c" >/dev/null 2>&1; then
    echo "FAIL: a renewal signed by one token was accepted" >&2; exit 1
  fi
  [ ! -e "$D/refused/root.json" ] || { echo "FAIL: a refused renewal left a file" >&2; exit 1; }
  sh "$0" renew "$D/out/root.json" "$D/renewed" "hsm:2?label=onemind-rehearsal-b" "hsm:2?label=onemind-rehearsal-c" >/dev/null
  cp -R "$D/channel" "$D/channel2"; cp "$D/renewed/2.root.json" "$D/channel2/2.root.json"
  tuf verify --repo "$D/channel2" --root "$D/out/root.json" >/dev/null
  echo "== REHEARSAL PASSED: keys made on 3 tokens, a 2-of-3 root signed by two of them, a signed release verified, a renewal by the other two (one alone refused) followed by a box on v1. Delete $D." >&2
  exit 0
  ;;
rotate-root)
  OLD=$1; D=$2; CH=$3; TH=$4; shift 4
  n=0; for a in "$@"; do [ "$a" = "--" ] && break; n=$((n + 1)); done
  [ "$n" -lt $# ] || { echo "missing -- between the old keys and the new keys" >&2; exit 2; }
  # Old keys sign (--old-key). New keys: a .pub is trusted without signing (--new-pub), anything else
  # (a file or an hsm: reference) signs (--new-key). Quoted, so paths with spaces survive.
  i=0; while [ "$i" -lt "$n" ]; do a=$1; shift; set -- "$@" --old-key "$a"; i=$((i + 1)); done
  shift   # the --
  i=$(($# - 2 * n)); while [ "$i" -gt 0 ]; do
    a=$1; shift
    case "$a" in hsm:*) set -- "$@" --new-key "$a" ;; *.pub) set -- "$@" --new-pub "$a" ;; *) set -- "$@" --new-key "$a" ;; esac
    i=$((i - 1)); done
  tuf rotate-root --root "$OLD" "$@" --threshold "$TH" --out "$D"
  echo "channel: $CH -> commit as os/rootfs/layers/base/usr/lib/onemind/tuf/$CH/root.json; the channel also needs the numbered <N+1>.root.json from $D"
  ;;
rehearse-rotate)
  D=$1
  [ ! -e "$D" ] || { echo "refusing: $D exists; rehearse into a new directory" >&2; exit 2; }
  sh "$0" rehearse "$D" >/dev/null
  export ONEMIND_TUF_PASSPHRASE="rehearsal-throwaway-passphrase"
  echo "== REHEARSAL OF THE ROTATION: throwaway keys only" >&2
  for h in new-a new-b new-c; do tuf keygen --out-dir "$D/sticks/$h" --roles root --encrypt; done
  tuf rotate-root --root "$D/out/root.json" --old-key "$D/sticks/holder-a/root.key" --old-key "$D/sticks/holder-b/root.key"     --new-key "$D/sticks/new-a/root.key" --new-key "$D/sticks/new-b/root.key" --new-pub "$D/sticks/new-c/root.pub"     --threshold 2 --out "$D/rotated"
  tuf inspect --root "$D/rotated/root.json" --expect-threshold 2 --expect-root-keys 3 --prev "$D/out/root.json"
  printf rehearsal2 >"$D/rel/onemind-vm-0.0.1.raucb"; printf '{}' >"$D/rel/onemind-vm-0.0.1.spdx.json"
  printf '{}' >"$D/rel/onemind-vm-0.0.1.cve-report.json"
  sed 's/0\.0\.0/0.0.1/g' "$D/rel/release-vm-0.0.0.json" >"$D/rel/release-vm-0.0.1.json"
  tuf build --repo "$D/channel2" --root "$D/rotated/root.json" --prev "$D/channel" --release "$D/rel/release-vm-0.0.1.json" \
    --targets-key "$D/online/targets.key" --snapshot-key "$D/online/snapshot.key" \
    --timestamp-key "$D/online/timestamp.key" >/dev/null
  tuf verify --repo "$D/channel2" --root "$D/out/root.json" --allow-absent   # a box that still trusts only version 1
  echo "== REHEARSAL PASSED: v1 -> v2 rotation signed by 2 old + 2 new keys, followed by a client that trusts only v1. Delete $D." >&2
  exit 0
  ;;
check)
  D=$1; TH=$2; NK=$3
  # After a rotation, name the previous root too: the check then also proves its keys signed this one.
  tuf inspect --root "$D/root.json" --expect-threshold "$TH" --expect-root-keys "$NK" ${4:+--prev "$4"}
  exit 0
  ;;
*) sed -n '3,/^set -eu/p' "$0" | sed '$d'; exit 2 ;;
esac
sha256sum "$D/root.json" 2>/dev/null || shasum -a 256 "$D/root.json"
"$PY" -I -c 'import json,sys
r=json.load(open(sys.argv[1]))["signed"]
for n,role in sorted(r["roles"].items()):
    print(n.ljust(9), "threshold", role["threshold"], "keyids", [k[:16] for k in role["keyids"]])
print("expires", r["expires"])' "$D/root.json"
